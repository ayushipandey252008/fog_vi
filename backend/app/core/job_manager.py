"""Job lifecycle management with file-based JSON persistence.

Jobs are processed on a background :class:`ThreadPoolExecutor` so HTTP requests
never block. Each job is persisted as ``data/jobs/<job_id>.json`` which doubles
as the local "processing history" store (survives restarts).
"""

from __future__ import annotations

import base64
import json
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import cv2

from app.config import get_settings
from app.core.logging import get_logger
from app.models.schemas import (
    Analytics,
    BeforeAfter,
    ConfidenceBucket,
    EnhancementSettings,
    JobStatus,
    ProcessRequest,
    TimelinePoint,
)
from app.pipeline.processor import VideoProcessingError, run_pipeline

logger = get_logger(__name__)

ALLOWED_EXTENSIONS = {".mp4", ".mov", ".avi"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobManager:
    """Creates, runs and persists video-processing jobs."""

    def __init__(self, max_workers: int = 2):
        self.settings = get_settings()
        self.settings.ensure_dirs()
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._lock = threading.Lock()

    # --- persistence ------------------------------------------------------
    def _job_path(self, job_id: str) -> Path:
        return self.settings.jobs_dir / f"{job_id}.json"

    def _read(self, job_id: str) -> dict | None:
        path = self._job_path(job_id)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("Failed to read job %s: %s", job_id, exc)
            return None

    def _write(self, record: dict) -> None:
        path = self._job_path(record["job_id"])
        with self._lock:
            path.write_text(json.dumps(record, indent=2))

    def _patch(self, job_id: str, **fields) -> None:
        record = self._read(job_id)
        if record is None:
            return
        record.update(fields)
        self._write(record)

    # --- creation ---------------------------------------------------------
    def create_job(self, original_filename: str, raw: bytes) -> dict:
        """Validate, store the upload, probe metadata and create a job record."""
        ext = Path(original_filename).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise ValueError(
                f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
            )

        max_bytes = self.settings.max_upload_mb * 1024 * 1024
        if len(raw) > max_bytes:
            raise ValueError(f"File too large (>{self.settings.max_upload_mb} MB).")

        job_id = uuid.uuid4().hex[:12]
        input_path = self.settings.uploads_dir / f"{job_id}{ext}"
        input_path.write_bytes(raw)

        meta = self._probe_video(str(input_path))
        if meta is None:
            input_path.unlink(missing_ok=True)
            raise ValueError("Could not read the video. It may be corrupt or an unsupported codec.")

        record = {
            "job_id": job_id,
            "filename": original_filename,
            "input_path": str(input_path),
            "output_path": str(self.settings.outputs_dir / f"{job_id}.mp4"),
            "status": JobStatus.queued.value,
            "progress": 0.0,
            "current_frame": 0,
            "total_frames": meta["frame_count"],
            "eta_seconds": 0.0,
            "error": None,
            "created_at": _now_iso(),
            "size_bytes": len(raw),
            "duration_s": meta["duration_s"],
            "fps": meta["fps"],
            "frame_count": meta["frame_count"],
            "width": meta["width"],
            "height": meta["height"],
            "thumbnail": meta["thumbnail"],
            "analytics": None,
            "timeline": [],
            "confidence_hist": [],
            "before_after": None,
        }
        self._write(record)
        logger.info("Created job %s (%s, %.1fs, %d frames)", job_id, original_filename,
                    meta["duration_s"], meta["frame_count"])
        return record

    @staticmethod
    def _probe_video(path: str) -> dict | None:
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            cap.release()
            return None
        fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        duration = (frame_count / fps) if fps else 0.0

        ok, frame = cap.read()
        cap.release()
        if not ok or width == 0 or height == 0:
            return None

        thumb = JobManager._make_thumbnail(frame)
        return {
            "fps": round(fps, 2),
            "frame_count": frame_count,
            "width": width,
            "height": height,
            "duration_s": round(duration, 2),
            "thumbnail": thumb,
        }

    @staticmethod
    def _make_thumbnail(frame, max_w: int = 480) -> str:
        h, w = frame.shape[:2]
        if w > max_w:
            scale = max_w / w
            frame = cv2.resize(frame, (max_w, int(h * scale)))
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if not ok:
            return ""
        return "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode("ascii")

    # --- processing -------------------------------------------------------
    def start(self, job_id: str, request: ProcessRequest | None) -> bool:
        record = self._read(job_id)
        if record is None:
            return False
        if record["status"] == JobStatus.processing.value:
            return True  # idempotent

        self._patch(job_id, status=JobStatus.queued.value, error=None, progress=0.0,
                    current_frame=0)
        self._executor.submit(self._run, job_id, request)
        return True

    def _run(self, job_id: str, request: ProcessRequest | None) -> None:
        record = self._read(job_id)
        if record is None:
            return

        self._patch(job_id, status=JobStatus.processing.value)

        s = self.settings
        if request and request.enhancement:
            enhancement = request.enhancement
        else:
            enhancement = EnhancementSettings(
                clahe=s.enable_clahe,
                gamma=s.gamma_value if s.enable_gamma else 1.0,
                hist_eq=s.enable_hist_eq,
                sharpen=s.enable_sharpen,
            )
        model_name = (request.model_name if request and request.model_name else None)
        conf = (request.conf if request and request.conf is not None else None)

        def on_progress(current: int, total: int, eta: float) -> None:
            progress = (current / total) if total else 0.0
            self._patch(
                job_id,
                current_frame=current,
                total_frames=total,
                progress=round(progress, 4),
                eta_seconds=round(eta, 1),
            )

        try:
            result = run_pipeline(
                input_path=record["input_path"],
                output_path=record["output_path"],
                enhancement=enhancement,
                model_name=model_name,
                conf=conf,
                device=s.device,
                max_frames=s.max_frames,
                progress_cb=on_progress,
            )
            self._patch(
                job_id,
                status=JobStatus.completed.value,
                progress=1.0,
                eta_seconds=0.0,
                analytics=result.analytics.model_dump(),
                timeline=[p.model_dump() for p in result.timeline],
                confidence_hist=[c.model_dump() for c in result.confidence_hist],
                before_after=result.before_after.model_dump(),
            )
        except VideoProcessingError as exc:
            logger.error("Job %s failed (video): %s", job_id, exc)
            self._patch(job_id, status=JobStatus.failed.value, error=str(exc))
        except Exception as exc:  # noqa: BLE001 - capture any pipeline failure
            logger.exception("Job %s failed (unexpected)", job_id)
            self._patch(job_id, status=JobStatus.failed.value, error=str(exc))

    # --- queries ----------------------------------------------------------
    def get(self, job_id: str) -> dict | None:
        return self._read(job_id)

    def status(self, job_id: str) -> dict | None:
        record = self._read(job_id)
        if record is None:
            return None
        preview_url = None
        stem = Path(record["output_path"]).with_suffix("").name
        preview_file = self.settings.outputs_dir / f"{stem}_preview.jpg"
        if preview_file.exists():
            preview_url = f"/media/outputs/{preview_file.name}"
        return {
            "job_id": record["job_id"],
            "status": record["status"],
            "progress": record.get("progress", 0.0),
            "current_frame": record.get("current_frame", 0),
            "total_frames": record.get("total_frames", 0),
            "eta_seconds": record.get("eta_seconds", 0.0),
            "error": record.get("error"),
            "preview_url": preview_url,
        }

    def results(self, job_id: str) -> dict | None:
        record = self._read(job_id)
        if record is None:
            return None
        return {
            "job_id": record["job_id"],
            "status": record["status"],
            "analytics": record.get("analytics"),
            "timeline": record.get("timeline", []),
            "confidence_hist": record.get("confidence_hist", []),
            "before_after": record.get("before_after"),
            "original_url": f"/media/uploads/{Path(record['input_path']).name}",
            "processed_url": f"/media/outputs/{Path(record['output_path']).name}",
            "error": record.get("error"),
        }

    def history(self) -> list[dict]:
        items: list[dict] = []
        for path in self.settings.jobs_dir.glob("*.json"):
            try:
                rec = json.loads(path.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            analytics = rec.get("analytics") or {}
            items.append(
                {
                    "job_id": rec["job_id"],
                    "filename": rec.get("filename", "video"),
                    "created_at": rec.get("created_at", ""),
                    "status": rec.get("status", JobStatus.queued.value),
                    "total_vehicles": analytics.get("total_vehicles", 0),
                    "cars": analytics.get("cars", 0),
                    "trucks": analytics.get("trucks", 0),
                    "buses": analytics.get("buses", 0),
                    "motorcycles": analytics.get("motorcycles", 0),
                    "average_confidence": analytics.get("average_confidence", 0.0),
                    "processing_time_s": analytics.get("processing_time_s", 0.0),
                    "fps_processed": analytics.get("fps_processed", 0.0),
                    "fog_density": analytics.get("fog_density", 0.0),
                    "risk_score": analytics.get("risk_score", 0.0),
                }
            )
        items.sort(key=lambda x: x["created_at"], reverse=True)
        return items


# Module-level singleton used by the API layer.
_manager: JobManager | None = None


def get_job_manager() -> JobManager:
    global _manager
    if _manager is None:
        _manager = JobManager()
    return _manager
