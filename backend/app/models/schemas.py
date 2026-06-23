"""Pydantic request/response models shared across the API."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    queued = "queued"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class EnhancementSettings(BaseModel):
    """Toggleable fog-enhancement parameters."""

    clahe: bool = True
    gamma: float = Field(default=1.2, ge=0.1, le=4.0)
    hist_eq: bool = True
    sharpen: bool = True


class ProcessRequest(BaseModel):
    """Optional overrides supplied when starting processing."""

    enhancement: EnhancementSettings | None = None
    model_name: str | None = None
    conf: float | None = Field(default=None, ge=0.05, le=0.95)


class UploadResponse(BaseModel):
    job_id: str
    filename: str
    size_bytes: int
    duration_s: float
    fps: float
    frame_count: int
    width: int
    height: int
    thumbnail: str  # data URL (image/jpeg;base64)


class ProcessResponse(BaseModel):
    job_id: str
    status: JobStatus


class StatusResponse(BaseModel):
    job_id: str
    status: JobStatus
    progress: float = 0.0
    current_frame: int = 0
    total_frames: int = 0
    eta_seconds: float = 0.0
    error: str | None = None
    preview_url: str | None = None  # live annotated-frame preview while processing


class Analytics(BaseModel):
    total_vehicles: int
    cars: int
    trucks: int
    buses: int
    motorcycles: int
    average_confidence: float
    processing_time_s: float
    fps_processed: float
    danger_alerts: int = 0       # frames with at least one "too close" vehicle
    danger_vehicles: int = 0     # unique vehicles that entered the danger zone
    max_proximity: float = 0.0   # closest approach (box-height / frame-height)
    fog_density: float = 0.0
    fog_level: str = "Clear"
    visibility_range_m: float = 200.0
    risk_score: float = 0.0
    risk_level: str = "Low"
    recommended_speed_kmh: int = 80


class TimelinePoint(BaseModel):
    frame: int
    t: float
    cars: int
    trucks: int
    buses: int
    motorcycles: int
    total: int
    danger: int = 0


class ConfidenceBucket(BaseModel):
    bucket: str
    count: int


class BeforeAfter(BaseModel):
    original: str  # data URL
    enhanced: str  # data URL


class ResultsResponse(BaseModel):
    job_id: str
    status: JobStatus
    analytics: Analytics | None = None
    timeline: list[TimelinePoint] = []
    confidence_hist: list[ConfidenceBucket] = []
    before_after: BeforeAfter | None = None
    original_url: str | None = None
    processed_url: str | None = None
    error: str | None = None


class HistoryItem(BaseModel):
    job_id: str
    filename: str
    created_at: str
    status: JobStatus
    total_vehicles: int = 0
    cars: int = 0
    trucks: int = 0
    buses: int = 0
    motorcycles: int = 0
    average_confidence: float = 0.0
    processing_time_s: float = 0.0
    fps_processed: float = 0.0
    fog_density: float = 0.0
    risk_score: float = 0.0
