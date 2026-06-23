"""Trajectory-based collision prediction for tracked vehicles.

Maintains per-track position history keyed by ByteTrack IDs, estimates velocity
from recent samples, predicts future positions, and flags detections whose
predicted paths intersect within a distance threshold.
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from collections.abc import Sequence

import numpy as np

from app.config import get_settings
from app.pipeline.annotator import Detection


@dataclass(frozen=True, slots=True)
class TrackSample:
    """A single position sample for one tracked vehicle."""

    t: float
    cx: float
    cy: float
    w: float
    h: float


@dataclass(slots=True)
class TrackState:
    """Rolling position history and last-seen frame for one track."""

    samples: deque[TrackSample]
    last_frame: int = 0


class TrackHistory:
    """Position history storage keyed by ByteTrack ``track_id``."""

    def __init__(
        self,
        max_samples: int = 30,
        stale_frames: int = 15,
    ) -> None:
        self.max_samples = max_samples
        self.stale_frames = stale_frames
        self._tracks: dict[int, TrackState] = {}

    def update(
        self,
        track_id: int,
        t: float,
        cx: float,
        cy: float,
        w: float,
        h: float,
        frame_idx: int,
    ) -> None:
        """Append a sample for ``track_id``."""
        if track_id < 0:
            return
        state = self._tracks.get(track_id)
        if state is None:
            state = TrackState(samples=deque(maxlen=self.max_samples))
            self._tracks[track_id] = state
        state.samples.append(TrackSample(t=t, cx=cx, cy=cy, w=w, h=h))
        state.last_frame = frame_idx

    def samples(self, track_id: int) -> tuple[TrackSample, ...]:
        """Return immutable history for a track (empty if unknown)."""
        state = self._tracks.get(track_id)
        if state is None:
            return ()
        return tuple(state.samples)

    def prune(self, frame_idx: int) -> None:
        """Drop tracks that have not been seen recently."""
        stale = [
            track_id
            for track_id, state in self._tracks.items()
            if frame_idx - state.last_frame > self.stale_frames
        ]
        for track_id in stale:
            del self._tracks[track_id]


def bbox_center_and_size(det: Detection) -> tuple[float, float, float, float]:
    """Return ``(cx, cy, width, height)`` from a detection bounding box."""
    w = float(det.x2 - det.x1)
    h = float(det.y2 - det.y1)
    cx = det.x1 + w / 2.0
    cy = det.y1 + h / 2.0
    return cx, cy, w, h


def compute_velocity(samples: Sequence[TrackSample]) -> tuple[float, float] | None:
    """Estimate ``(vx, vy)`` in pixels/second via linear regression on history.

    Returns ``None`` when there are fewer than two samples or timestamps do not
    advance.
    """
    if len(samples) < 2:
        return None

    ts = np.array([s.t for s in samples], dtype=np.float64)
    if ts[-1] - ts[0] < 1e-6:
        return None

    cx = np.array([s.cx for s in samples], dtype=np.float64)
    cy = np.array([s.cy for s in samples], dtype=np.float64)
    vx = float(np.polyfit(ts, cx, 1)[0])
    vy = float(np.polyfit(ts, cy, 1)[0])
    return vx, vy


def predict_position(
    cx: float,
    cy: float,
    vx: float,
    vy: float,
    dt: float,
) -> tuple[float, float]:
    """Constant-velocity position ``dt`` seconds into the future."""
    return cx + vx * dt, cy + vy * dt


def predict_positions(
    cx: float,
    cy: float,
    vx: float,
    vy: float,
    horizons_s: tuple[float, ...],
) -> list[tuple[float, float, float]]:
    """Return ``(dt, px, py)`` for each horizon in ``horizons_s``."""
    return [(dt, *predict_position(cx, cy, vx, vy, dt)) for dt in horizons_s]


def distance(p1: tuple[float, float], p2: tuple[float, float]) -> float:
    """Euclidean distance between two ``(x, y)`` points."""
    return math.hypot(p1[0] - p2[0], p1[1] - p2[1])


def find_collision_eta(
    cx_a: float,
    cy_a: float,
    vx_a: float,
    vy_a: float,
    cx_b: float,
    cy_b: float,
    vx_b: float,
    vy_b: float,
    *,
    threshold: float,
    horizon_s: float,
    time_step_s: float,
) -> float | None:
    """Return time-to-collision in seconds, or ``None`` if paths stay apart.

    Walks forward from ``time_step_s`` to ``horizon_s`` in fixed steps and
    returns the first time at which predicted centers are within ``threshold``
    pixels of each other.
    """
    if time_step_s <= 0 or horizon_s <= 0:
        return None

    t = time_step_s
    while t <= horizon_s + 1e-9:
        ax, ay = predict_position(cx_a, cy_a, vx_a, vy_a, t)
        bx, by = predict_position(cx_b, cy_b, vx_b, vy_b, t)
        if distance((ax, ay), (bx, by)) <= threshold:
            return t
        t += time_step_s
    return None


class CollisionPredictor:
    """Stateful per-job collision predictor using ByteTrack IDs."""

    _NO_COLLISION_ETA = float("inf")

    def __init__(
        self,
        fps: float,
        *,
        distance_threshold: float | None = None,
        horizon_s: float | None = None,
        min_history: int | None = None,
        history_max: int | None = None,
        stale_frames: int | None = None,
        time_step_s: float | None = None,
    ) -> None:
        settings = get_settings()
        self.fps = fps if fps > 0 else 25.0
        self.distance_threshold = (
            distance_threshold
            if distance_threshold is not None
            else settings.collision_distance_threshold
        )
        self.horizon_s = horizon_s if horizon_s is not None else settings.collision_horizon_s
        self.min_history = min_history if min_history is not None else settings.collision_min_history
        self.time_step_s = (
            time_step_s if time_step_s is not None else settings.collision_time_step_s
        )
        self.horizons_s = tuple(settings.collision_prediction_horizons)
        self._history = TrackHistory(
            max_samples=history_max if history_max is not None else settings.collision_history_max,
            stale_frames=stale_frames if stale_frames is not None else settings.collision_stale_frames,
        )

    def enrich(self, detections: list[Detection], t: float, frame_idx: int) -> None:
        """Update track history and set ``collision_risk`` / ``collision_eta``."""
        for det in detections:
            det.collision_risk = False
            det.collision_eta = self._NO_COLLISION_ETA

        active: dict[int, Detection] = {}
        for det in detections:
            if det.track_id < 0:
                continue
            cx, cy, w, h = bbox_center_and_size(det)
            self._history.update(det.track_id, t, cx, cy, w, h, frame_idx)
            active[det.track_id] = det

        self._history.prune(frame_idx)

        track_ids = sorted(active)
        for i, id_a in enumerate(track_ids):
            samples_a = self._history.samples(id_a)
            if len(samples_a) < self.min_history:
                continue
            vel_a = compute_velocity(samples_a)
            if vel_a is None:
                continue
            cx_a, cy_a, _, _ = bbox_center_and_size(active[id_a])
            vx_a, vy_a = vel_a

            for id_b in track_ids[i + 1 :]:
                samples_b = self._history.samples(id_b)
                if len(samples_b) < self.min_history:
                    continue
                vel_b = compute_velocity(samples_b)
                if vel_b is None:
                    continue
                cx_b, cy_b, _, _ = bbox_center_and_size(active[id_b])
                vx_b, vy_b = vel_b

                eta = find_collision_eta(
                    cx_a,
                    cy_a,
                    vx_a,
                    vy_a,
                    cx_b,
                    cy_b,
                    vx_b,
                    vy_b,
                    threshold=self.distance_threshold,
                    horizon_s=self.horizon_s,
                    time_step_s=self.time_step_s,
                )
                if eta is None:
                    continue

                for track_id in (id_a, id_b):
                    det = active[track_id]
                    det.collision_risk = True
                    det.collision_eta = min(det.collision_eta, eta)
