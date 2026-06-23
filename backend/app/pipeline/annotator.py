"""Bounding-box drawing for tracked vehicle detections."""

from __future__ import annotations

import cv2
import numpy as np

# Per-class BGR colours (vivid, distinct, on-brand with the frontend palette).
CLASS_COLORS: dict[str, tuple[int, int, int]] = {
    "car": (246, 130, 59),       # primary blue (#3B82F6) in BGR
    "truck": (182, 182, 6),      # cyan/teal (#06B6D4)
    "bus": (129, 185, 16),       # success green (#10B981)
    "motorcycle": (68, 68, 239),  # red accent
}
_DEFAULT_COLOR = (200, 200, 200)


# Risk-level colours (BGR).
RISK_COLORS: dict[str, tuple[int, int, int]] = {
    "danger": (60, 60, 239),    # red (#ef4444)
    "caution": (0, 170, 245),   # amber/orange
}
DANGER_LABEL = {"danger": "TOO CLOSE", "caution": "CLOSE"}

# Collision severity colours (BGR): scaled by time-to-collision.
_COLLISION_RED = (0, 0, 255)
_COLLISION_ORANGE = (0, 140, 255)
_COLLISION_YELLOW = (0, 230, 255)
_COLLISION_BANNER_RED = (0, 0, 230)


class Detection:
    """A single drawable detection."""

    __slots__ = (
        "x1",
        "y1",
        "x2",
        "y2",
        "label",
        "conf",
        "track_id",
        "risk",
        "proximity",
        "collision_risk",
        "collision_eta",
    )

    def __init__(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        label: str,
        conf: float,
        track_id: int,
        risk: str = "safe",
        proximity: float = 0.0,
        collision_risk: bool = False,
        collision_eta: float = float("inf"),
    ):
        self.x1, self.y1, self.x2, self.y2 = x1, y1, x2, y2
        self.label = label
        self.conf = conf
        self.track_id = track_id
        self.risk = risk            # "safe" | "caution" | "danger"
        self.proximity = proximity  # box-height / frame-height, 0..1
        self.collision_risk = collision_risk
        self.collision_eta = collision_eta  # seconds; inf when no collision predicted


def classify_risk(box_height: int, frame_height: int, danger_ratio: float, caution_ratio: float):
    """Return (risk_level, proximity_ratio) from bounding-box height vs frame."""
    ratio = box_height / frame_height if frame_height else 0.0
    if ratio >= danger_ratio:
        return "danger", ratio
    if ratio >= caution_ratio:
        return "caution", ratio
    return "safe", ratio


def _collision_severity_color(ttc: float) -> tuple[int, int, int]:
    """Map ETA to alert colour: <1s red, 1–2s orange, >2s yellow."""
    if ttc < 1.0:
        return _COLLISION_RED
    if ttc <= 2.0:
        return _COLLISION_ORANGE
    return _COLLISION_YELLOW


def _collision_box_thickness(ttc: float) -> int:
    if ttc < 1.0:
        return 5
    if ttc <= 2.0:
        return 4
    return 3


def _draw_collision_box_ttc(
    frame: np.ndarray,
    det: Detection,
    color: tuple[int, int, int],
    ttc: float,
) -> None:
    """Draw a large TTC label centred on the vehicle bounding box."""
    text = f"TTC {ttc:.1f}s"
    box_w = max(det.x2 - det.x1, 1)
    box_h = max(det.y2 - det.y1, 1)
    scale = max(0.55, min(box_w, box_h) / 90.0)
    thickness = 2 if ttc >= 1.0 else 3
    font = cv2.FONT_HERSHEY_DUPLEX
    (tw, th), baseline = cv2.getTextSize(text, font, scale, thickness)
    cx = (det.x1 + det.x2) // 2
    cy = (det.y1 + det.y2) // 2
    pad = 8
    x1 = cx - tw // 2 - pad
    y1 = cy - th // 2 - pad
    x2 = cx + tw // 2 + pad
    y2 = cy + th // 2 + baseline + pad
    cv2.rectangle(frame, (x1, y1), (x2, y2), (20, 20, 20), -1)
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
    cv2.putText(
        frame,
        text,
        (cx - tw // 2, cy + th // 2),
        font,
        scale,
        color,
        thickness,
        cv2.LINE_AA,
    )


def draw_detections(frame: np.ndarray, detections: list[Detection]) -> np.ndarray:
    """Draw bounding boxes + labels, colouring close vehicles by risk level.

    Collision-predicted vehicles take visual priority: severity-scaled boxes,
    on-box TTC labels, and a bright red top banner. Proximity styling applies
    only when ``collision_risk`` is false.
    """
    out = frame
    danger_count = 0
    earliest_collision_ttc: float | None = None

    for det in detections:
        if det.collision_risk:
            color = _collision_severity_color(det.collision_eta)
            thickness = _collision_box_thickness(det.collision_eta)
            caption = f"COLLISION RISK | TTC: {det.collision_eta:.1f}s"
            text_color = (255, 255, 255)
            if earliest_collision_ttc is None or det.collision_eta < earliest_collision_ttc:
                earliest_collision_ttc = det.collision_eta
        elif det.risk in RISK_COLORS:
            color = RISK_COLORS[det.risk]
            thickness = 3 if det.risk == "danger" else 2
            caption = f"{det.label} #{det.track_id} {det.conf:.2f}"
            if det.risk in DANGER_LABEL:
                caption += f"  {DANGER_LABEL[det.risk]}"
            text_color = (255, 255, 255) if det.risk == "danger" else (10, 10, 20)
            if det.risk == "danger":
                danger_count += 1
        else:
            color = CLASS_COLORS.get(det.label, _DEFAULT_COLOR)
            thickness = 2
            caption = f"{det.label} #{det.track_id} {det.conf:.2f}"
            text_color = (10, 10, 20)

        cv2.rectangle(out, (det.x1, det.y1), (det.x2, det.y2), color, thickness)

        (tw, th), baseline = cv2.getTextSize(caption, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        chip_y2 = det.y1
        chip_y1 = max(0, det.y1 - th - baseline - 6)
        cv2.rectangle(out, (det.x1, chip_y1), (det.x1 + tw + 8, chip_y2), color, -1)
        cv2.putText(
            out,
            caption,
            (det.x1 + 4, chip_y2 - baseline - 2),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            text_color,
            1,
            cv2.LINE_AA,
        )
        if det.collision_risk:
            _draw_collision_box_ttc(out, det, color, det.collision_eta)

    if earliest_collision_ttc is not None:
        _draw_collision_banner(out, earliest_collision_ttc)
    elif danger_count:
        _draw_danger_banner(out, danger_count)
    return out


def _draw_collision_banner(frame: np.ndarray, earliest_ttc: float) -> None:
    """Overlay a bright red collision-warning banner at the top of the frame."""
    h, w = frame.shape[:2]
    bar_h = max(72, h // 7)
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (w, bar_h), _COLLISION_BANNER_RED, -1)
    cv2.addWeighted(overlay, 0.75, frame, 0.25, 0, frame)

    line1 = "COLLISION RISK DETECTED"
    line2 = f"Earliest TTC: {earliest_ttc:.1f}s"
    scale = max(0.65, bar_h / 56)
    thickness = 3
    font = cv2.FONT_HERSHEY_DUPLEX
    ttc_color = _collision_severity_color(earliest_ttc)
    (tw1, th1), _ = cv2.getTextSize(line1, font, scale, thickness)
    (tw2, th2), baseline2 = cv2.getTextSize(line2, font, scale * 0.9, thickness)
    gap = 6
    block_h = th1 + gap + th2 + baseline2
    y1 = max(th1 + 6, (bar_h - block_h) // 2 + th1)
    y2 = y1 + gap + th2

    cv2.putText(
        frame,
        line1,
        ((w - tw1) // 2, y1),
        font,
        scale,
        (255, 255, 255),
        thickness,
        cv2.LINE_AA,
    )
    cv2.putText(
        frame,
        line2,
        ((w - tw2) // 2, y2),
        font,
        scale * 0.9,
        ttc_color,
        thickness,
        cv2.LINE_AA,
    )


def _draw_danger_banner(frame: np.ndarray, count: int) -> None:
    """Overlay a red warning banner at the top of the frame."""
    h, w = frame.shape[:2]
    bar_h = max(28, h // 16)
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (w, bar_h), (40, 40, 220), -1)
    cv2.addWeighted(overlay, 0.55, frame, 0.45, 0, frame)
    text = f"! DANGER - VEHICLE TOO CLOSE ({count})" if count > 1 else "! DANGER - VEHICLE TOO CLOSE"
    scale = max(0.5, bar_h / 44)
    (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, 2)
    cv2.putText(
        frame,
        text,
        ((w - tw) // 2, (bar_h + th) // 2),
        cv2.FONT_HERSHEY_SIMPLEX,
        scale,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )
