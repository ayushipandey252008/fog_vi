"""Fog density estimation and dynamic road risk scoring.

Uses image-quality heuristics (contrast, Laplacian variance, edge density) to
estimate fog density, derive visibility range, and compute a composite road
risk score from environmental and traffic factors.
"""

from __future__ import annotations

from typing import TypedDict

import cv2
import numpy as np

FOG_LEVEL_CLEAR = "Clear"
FOG_LEVEL_MODERATE = "Moderate"
FOG_LEVEL_DENSE = "Dense"
FOG_LEVEL_SEVERE = "Severe"

RISK_LEVEL_LOW = "Low"
RISK_LEVEL_MEDIUM = "Medium"
RISK_LEVEL_HIGH = "High"
RISK_LEVEL_EXTREME = "Extreme"

VISIBILITY_BY_LEVEL: dict[str, float] = {
    FOG_LEVEL_CLEAR: 200.0,
    FOG_LEVEL_MODERATE: 100.0,
    FOG_LEVEL_DENSE: 50.0,
    FOG_LEVEL_SEVERE: 30.0,
}

SPEED_BY_FOG_LEVEL: dict[str, int] = {
    FOG_LEVEL_CLEAR: 80,
    FOG_LEVEL_MODERATE: 60,
    FOG_LEVEL_DENSE: 40,
    FOG_LEVEL_SEVERE: 20,
}

_DEFAULT_VISIBILITY_M = 100.0


class FogEstimate(TypedDict):
    fog_density: float
    fog_level: str


class RiskEstimate(TypedDict):
    risk_score: float
    risk_level: str


def classify_fog_level(fog_density: float) -> str:
    """Map fog density (0–100) to a human-readable level."""
    if fog_density <= 30:
        return FOG_LEVEL_CLEAR
    if fog_density <= 60:
        return FOG_LEVEL_MODERATE
    if fog_density <= 80:
        return FOG_LEVEL_DENSE
    return FOG_LEVEL_SEVERE


def classify_risk_level(risk_score: float) -> str:
    """Map risk score (0–10) to a severity band."""
    if risk_score <= 3:
        return RISK_LEVEL_LOW
    if risk_score <= 6:
        return RISK_LEVEL_MEDIUM
    if risk_score <= 8:
        return RISK_LEVEL_HIGH
    return RISK_LEVEL_EXTREME


def _prepare_gray(frame: np.ndarray, max_dim: int = 640) -> np.ndarray:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
    h, w = gray.shape[:2]
    if max(h, w) > max_dim:
        scale = max_dim / max(h, w)
        gray = cv2.resize(gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    return gray


def grayscale_contrast_score(gray: np.ndarray) -> float:
    """Return fog component 0..1 (higher = foggier) from intensity spread."""
    std = float(np.std(gray))
    return float(np.clip(1.0 - std / 60.0, 0.0, 1.0))


def laplacian_variance_score(gray: np.ndarray) -> float:
    """Return fog component 0..1 from blur / lack of fine detail."""
    lap_var = cv2.Laplacian(gray, cv2.CV_64F).var()
    return float(np.clip(1.0 - lap_var / 400.0, 0.0, 1.0))


def edge_density_score(gray: np.ndarray) -> float:
    """Return fog component 0..1 from Canny edge sparsity."""
    edges = cv2.Canny(gray, 50, 150)
    density = float(np.count_nonzero(edges)) / float(edges.size)
    return float(np.clip(1.0 - density / 0.12, 0.0, 1.0))


def estimate_fog_density(frame: np.ndarray) -> FogEstimate:
    """Estimate fog density from a BGR frame using contrast, blur, and edges."""
    gray = _prepare_gray(frame)
    contrast = grayscale_contrast_score(gray)
    laplacian = laplacian_variance_score(gray)
    edges = edge_density_score(gray)

    fog_density = (0.35 * contrast + 0.40 * laplacian + 0.25 * edges) * 100.0
    fog_density = round(float(np.clip(fog_density, 0.0, 100.0)), 1)
    return {
        "fog_density": fog_density,
        "fog_level": classify_fog_level(fog_density),
    }


def estimate_visibility_range_m(fog_level: str) -> float:
    """Return estimated visibility range in metres for a fog level."""
    return VISIBILITY_BY_LEVEL.get(fog_level, _DEFAULT_VISIBILITY_M)


def compute_risk_score(
    fog_density: float,
    vehicle_count: int,
    danger_alerts: int,
    collision_alerts: int,
    *,
    total_frames: int = 1,
) -> RiskEstimate:
    """Compute a composite road risk score (0–10) from fog and traffic signals."""
    frames = max(total_frames, 1)

    fog_factor = (fog_density / 100.0) * 10.0
    vehicle_factor = min(vehicle_count / 20.0, 1.0) * 10.0
    danger_factor = min(danger_alerts / frames * 10.0, 10.0)
    collision_factor = min(collision_alerts / frames * 10.0, 10.0)

    risk = (
        0.4 * fog_factor
        + 0.25 * vehicle_factor
        + 0.20 * danger_factor
        + 0.15 * collision_factor
    )
    risk_score = round(float(np.clip(risk, 0.0, 10.0)), 1)
    return {
        "risk_score": risk_score,
        "risk_level": classify_risk_level(risk_score),
    }


def recommended_speed_kmh(fog_level: str, risk_score: float) -> int:
    """Return a recommended safe speed from fog level, reduced when risk is extreme."""
    speed = SPEED_BY_FOG_LEVEL.get(fog_level, 60)
    if risk_score > 8:
        speed = max(20, speed - 20)
    return speed
