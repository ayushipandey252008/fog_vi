"""Application configuration.

All settings are overridable via environment variables (see ``.env.example``).
Paths are resolved relative to the repository root so the app works regardless
of the current working directory.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Repository root = two levels up from this file (backend/app/config.py -> repo/).
REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Typed application settings loaded from the environment / ``.env``."""

    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT / "backend" / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Server -----------------------------------------------------------
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # --- Model / inference ------------------------------------------------
    model_name: str = "yolov8n.pt"  # swap for yolov8s.pt / yolov8m.pt
    confidence: float = 0.4
    iou: float = 0.5
    tracker: str = "bytetrack.yaml"
    device: str = "auto"  # auto | cpu | cuda | mps
    imgsz: int = 640
    max_frames: int = 0  # 0 = process all frames; >0 caps for quick demos

    # --- Proximity / danger detection ------------------------------------
    # A vehicle's bounding-box height relative to the frame height is used as a
    # mono-camera proximity proxy. Above danger_ratio => "danger" (too close);
    # above caution_ratio => "caution".
    danger_ratio: float = 0.5
    caution_ratio: float = 0.32

    # --- Trajectory collision prediction ---------------------------------
    collision_distance_threshold: float = 80.0  # px between predicted centers
    collision_horizon_s: float = 3.0
    collision_min_history: int = 3  # frames before velocity is trusted
    collision_history_max: int = 30
    collision_stale_frames: int = 15
    collision_time_step_s: float = 0.1  # ETA search step size
    collision_prediction_horizons: tuple[float, float, float] = (1.0, 2.0, 3.0)

    # --- Fog density / road risk -----------------------------------------
    fog_sample_interval: int = 30  # sample every N frames for fog estimation

    # --- Enhancement defaults --------------------------------------------
    enable_clahe: bool = True
    enable_gamma: bool = True
    gamma_value: float = 1.2
    enable_hist_eq: bool = True
    enable_sharpen: bool = True

    # --- Storage paths ----------------------------------------------------
    uploads_dir: Path = REPO_ROOT / "uploads"
    outputs_dir: Path = REPO_ROOT / "outputs"
    models_dir: Path = REPO_ROOT / "models"
    data_dir: Path = REPO_ROOT / "backend" / "data"

    max_upload_mb: int = 500

    @property
    def jobs_dir(self) -> Path:
        return self.data_dir / "jobs"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def ensure_dirs(self) -> None:
        """Create all runtime directories if missing."""
        for path in (
            self.uploads_dir,
            self.outputs_dir,
            self.models_dir,
            self.data_dir,
            self.jobs_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)


# COCO class ids we care about -> human label. Everything else is ignored.
VEHICLE_CLASSES: dict[int, str] = {
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck",
}


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    settings = Settings()
    settings.ensure_dirs()
    return settings
