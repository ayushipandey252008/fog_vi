"""End-to-end video processing orchestration.

Pipeline per frame:  read -> enhance -> detect+track -> annotate -> write.
After processing, analytics are aggregated and a before/after enhancement sample
is captured. Progress is reported through a callback so the job manager can
persist it for polling.
"""

from __future__ import annotations

import base64
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import cv2
import numpy as np

from app.config import get_settings
from app.core.logging import get_logger
from app.models.schemas import (
    Analytics,
    BeforeAfter,
    ConfidenceBucket,
    EnhancementSettings,
    TimelinePoint,
)
from app.pipeline.annotator import draw_detections
from app.pipeline.collision import CollisionPredictor
from app.pipeline.detector import VehicleDetector
from app.pipeline.enhancement import FogEnhancer
from app.pipeline.fog_density import (
    classify_fog_level,
    compute_risk_score,
    estimate_fog_density,
    estimate_visibility_range_m,
    recommended_speed_kmh,
)

logger = get_logger(__name__)

# Browser-friendly codecs first; OpenCV falls back along the list.
_FOURCC_CANDIDATES = ["avc1", "mp4v", "H264", "XVID"]

ProgressCallback = Callable[[int, int, float], None]


class VideoProcessingError(RuntimeError):
    """Raised on unreadable/corrupt video or writer failure."""


@dataclass
class PipelineResult:
    analytics: Analytics
    timeline: list[TimelinePoint]
    confidence_hist: list[ConfidenceBucket]
    before_after: BeforeAfter
    output_path: str


@dataclass
class _Accumulator:
    """Running aggregation of detections across frames."""

    counts_by_class: dict[str, set[int]] = field(default_factory=dict)
    confidences: list[float] = field(default_factory=list)
    timeline: list[TimelinePoint] = field(default_factory=list)
    danger_frames: int = 0
    danger_track_ids: set[int] = field(default_factory=set)
    collision_frames: int = 0
    fog_density_samples: list[float] = field(default_factory=list)
    max_proximity: float = 0.0

    def add_frame(self, frame_idx: int, t: float, detections) -> None:
        per_class = {"car": 0, "truck": 0, "bus": 0, "motorcycle": 0}
        danger_in_frame = 0
        collision_in_frame = False
        for det in detections:
            per_class[det.label] = per_class.get(det.label, 0) + 1
            self.confidences.append(det.conf)
            if det.track_id >= 0:
                self.counts_by_class.setdefault(det.label, set()).add(det.track_id)
            self.max_proximity = max(self.max_proximity, det.proximity)
            if det.collision_risk:
                collision_in_frame = True
            if det.risk == "danger":
                danger_in_frame += 1
                if det.track_id >= 0:
                    self.danger_track_ids.add(det.track_id)
        if collision_in_frame:
            self.collision_frames += 1
        if danger_in_frame:
            self.danger_frames += 1
        self.timeline.append(
            TimelinePoint(
                frame=frame_idx,
                t=round(t, 2),
                cars=per_class["car"],
                trucks=per_class["truck"],
                buses=per_class["bus"],
                motorcycles=per_class["motorcycle"],
                total=sum(per_class.values()),
                danger=danger_in_frame,
            )
        )

    def unique_count(self, label: str) -> int:
        return len(self.counts_by_class.get(label, set()))


def _open_capture(path: str) -> cv2.VideoCapture:
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise VideoProcessingError(f"Could not open video file: {path}")
    return cap


def _open_writer(path: str, fps: float, width: int, height: int) -> cv2.VideoWriter:
    for codec in _FOURCC_CANDIDATES:
        fourcc = cv2.VideoWriter_fourcc(*codec)
        writer = cv2.VideoWriter(path, fourcc, fps, (width, height))
        if writer.isOpened():
            logger.info("Using video codec '%s' for output", codec)
            return writer
        writer.release()
    raise VideoProcessingError(
        "No working video codec found (tried avc1/mp4v/H264/XVID). "
        "Install ffmpeg or an OpenCV build with codec support."
    )


def _write_preview(frame: np.ndarray, preview_path: str, max_w: int = 720) -> None:
    """Write a downscaled JPEG preview atomically (tmp + rename).

    Writing to a temp file and renaming avoids the frontend ever fetching a
    half-written image while polling during processing.
    """
    h, w = frame.shape[:2]
    if w > max_w:
        scale = max_w / w
        frame = cv2.resize(frame, (max_w, int(h * scale)))
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
    if not ok:
        return
    tmp = f"{preview_path}.tmp"
    try:
        with open(tmp, "wb") as f:
            f.write(buf.tobytes())
        os.replace(tmp, preview_path)
    except OSError:
        pass


def _to_data_url(frame: np.ndarray) -> str:
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    if not ok:
        return ""
    b64 = base64.b64encode(buf.tobytes()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


def _build_confidence_hist(confidences: list[float]) -> list[ConfidenceBucket]:
    edges = [0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.01]
    labels = ["40-50%", "50-60%", "60-70%", "70-80%", "80-90%", "90-100%"]
    counts = [0] * len(labels)
    for c in confidences:
        for i in range(len(labels)):
            if edges[i] <= c < edges[i + 1]:
                counts[i] += 1
                break
    return [ConfidenceBucket(bucket=lbl, count=counts[i]) for i, lbl in enumerate(labels)]


def run_pipeline(
    input_path: str,
    output_path: str,
    enhancement: EnhancementSettings,
    model_name: str | None,
    conf: float | None,
    device: str | None,
    max_frames: int = 0,
    progress_cb: ProgressCallback | None = None,
) -> PipelineResult:
    """Process ``input_path`` and write the annotated video to ``output_path``."""
    settings = get_settings()
    cap = _open_capture(input_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
    if max_frames and total_frames:
        total_frames = min(total_frames, max_frames)

    if width == 0 or height == 0:
        cap.release()
        raise VideoProcessingError("Video has invalid dimensions (corrupt file?).")

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    writer = _open_writer(output_path, fps, width, height)
    preview_path = str(Path(output_path).with_suffix("")) + "_preview.jpg"
    # Clear any stale preview from a previous run of this job.
    Path(preview_path).unlink(missing_ok=True)

    enhancer = FogEnhancer(enhancement)
    detector = VehicleDetector(model_name=model_name, conf=conf, device=device)
    collision = CollisionPredictor(fps=fps)
    acc = _Accumulator()
    fog_sample_interval = max(1, settings.fog_sample_interval)

    before_sample: np.ndarray | None = None
    after_sample: np.ndarray | None = None
    sample_target = max(0, (total_frames // 3) if total_frames else 0)

    start = time.perf_counter()
    frame_idx = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break

            if frame_idx % fog_sample_interval == 0:
                fog_sample = estimate_fog_density(frame)
                acc.fog_density_samples.append(fog_sample["fog_density"])

            enhanced = enhancer.enhance(frame)

            # Capture a representative before/after pair once.
            if before_sample is None and frame_idx >= sample_target:
                before_sample = frame.copy()
                after_sample = enhanced.copy()

            detections = detector.detect(enhanced)
            t = frame_idx / fps if fps else 0.0
            collision.enrich(detections, t, frame_idx)
            annotated = draw_detections(enhanced, detections)
            writer.write(annotated)

            acc.add_frame(frame_idx, t, detections)

            frame_idx += 1
            # Emit a live preview of every annotated frame so the UI's MJPEG
            # stream plays real-time detection while the job runs.
            _write_preview(annotated, preview_path)
            if progress_cb and (frame_idx % 5 == 0 or frame_idx == total_frames):
                elapsed = time.perf_counter() - start
                processed_fps = frame_idx / elapsed if elapsed > 0 else 0.0
                remaining = (total_frames - frame_idx) / processed_fps if processed_fps > 0 else 0.0
                progress_cb(frame_idx, total_frames or frame_idx, max(0.0, remaining))

            if max_frames and frame_idx >= max_frames:
                break
    finally:
        cap.release()
        writer.release()

    if frame_idx == 0:
        raise VideoProcessingError("No frames could be read from the video (corrupt file?).")

    elapsed = time.perf_counter() - start
    if before_sample is None:  # very short clips
        before_sample = np.zeros((height, width, 3), dtype=np.uint8)
        after_sample = before_sample

    cars = acc.unique_count("car")
    trucks = acc.unique_count("truck")
    buses = acc.unique_count("bus")
    motorcycles = acc.unique_count("motorcycle")
    avg_conf = float(np.mean(acc.confidences)) if acc.confidences else 0.0
    total_vehicles = cars + trucks + buses + motorcycles

    avg_fog_density = (
        float(np.mean(acc.fog_density_samples)) if acc.fog_density_samples else 0.0
    )
    fog_level = classify_fog_level(avg_fog_density)
    visibility_range_m = estimate_visibility_range_m(fog_level)
    risk = compute_risk_score(
        avg_fog_density,
        total_vehicles,
        acc.danger_frames,
        acc.collision_frames,
        total_frames=frame_idx,
    )
    safe_speed = recommended_speed_kmh(fog_level, risk["risk_score"])

    analytics = Analytics(
        total_vehicles=total_vehicles,
        cars=cars,
        trucks=trucks,
        buses=buses,
        motorcycles=motorcycles,
        average_confidence=round(avg_conf, 4),
        processing_time_s=round(elapsed, 2),
        fps_processed=round(frame_idx / elapsed, 2) if elapsed > 0 else 0.0,
        danger_alerts=acc.danger_frames,
        danger_vehicles=len(acc.danger_track_ids),
        max_proximity=round(acc.max_proximity, 3),
        fog_density=round(avg_fog_density, 1),
        fog_level=fog_level,
        visibility_range_m=visibility_range_m,
        risk_score=risk["risk_score"],
        risk_level=risk["risk_level"],
        recommended_speed_kmh=safe_speed,
    )

    logger.info(
        "Job complete: %d frames in %.1fs (%.1f fps) | vehicles=%d",
        frame_idx,
        elapsed,
        analytics.fps_processed,
        analytics.total_vehicles,
    )

    return PipelineResult(
        analytics=analytics,
        timeline=acc.timeline,
        confidence_hist=_build_confidence_hist(acc.confidences),
        before_after=BeforeAfter(
            original=_to_data_url(before_sample),
            enhanced=_to_data_url(after_sample),
        ),
        output_path=output_path,
    )
