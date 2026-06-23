# FogVision AI — Architecture

## High-level flow

```
┌─────────────┐     upload      ┌──────────────────────────────────────────┐
│             │ ───────────────▶│              FastAPI backend               │
│  Next.js    │                 │                                            │
│  frontend   │  poll /status   │  ┌────────────┐   ┌─────────────────────┐ │
│  (Browser)  │ ◀──────────────▶│  │ JobManager │──▶│  ThreadPoolExecutor │ │
│             │                 │  │ (JSON store)│   └──────────┬──────────┘ │
│             │  /results       │  └────────────┘              │            │
│             │ ◀───────────────│                              ▼            │
│             │                 │              ┌──────────────────────────┐ │
│             │  /download      │              │      Processing pipeline  │ │
│             │ ◀───────────────│              │  extract → enhance →      │ │
└─────────────┘                 │              │  detect → collision →     │ │
                                │              │  annotate → fog/risk →    │ │
                                │              │  encode → analytics       │ │
                                │              └──────────────────────────┘ │
                                └──────────────────────────────────────────┘
```

## Backend modules

| Module | Responsibility |
|--------|----------------|
| `app/main.py` | FastAPI app, CORS, static media mounts, lifespan |
| `app/config.py` | Env-driven settings, vehicle class map, path management |
| `app/api/routes.py` | HTTP endpoints (upload/process/status/results/download/history) |
| `app/core/job_manager.py` | Job lifecycle, JSON persistence, thread-pool dispatch, history |
| `app/core/device.py` | Compute-device auto-detection (`cuda → mps → cpu`) |
| `app/core/logging.py` | Centralised logging configuration |
| `app/pipeline/enhancement.py` | Modular fog enhancement (CLAHE, gamma, hist-eq, sharpen) |
| `app/pipeline/detector.py` | YOLOv8 + ByteTrack, vehicle-class filtering |
| `app/pipeline/collision.py` | Trajectory history, collision prediction, TTC |
| `app/pipeline/fog_density.py` | Fog density, visibility, road risk score, safe speed |
| `app/pipeline/annotator.py` | Bounding-box / label rendering |
| `app/pipeline/processor.py` | Orchestrates the per-frame pipeline + analytics |
| `app/models/schemas.py` | Pydantic request/response contracts |

## Processing pipeline

### Per frame

1. **Extract** — OpenCV `VideoCapture` streams frames one at a time (constant memory).
2. **Fog sample** — Every *N* frames (configurable), estimate fog density on the **original**
   frame before enhancement.
3. **Enhance** — `FogEnhancer` composes enabled steps in order:
   `CLAHE → gamma → histogram equalisation → unsharp sharpening`.
4. **Detect + Track** — `VehicleDetector` runs `YOLO.track(persist=True,
   tracker="bytetrack.yaml")` and filters to COCO ids `{2,3,5,7}`
   (car, motorcycle, bus, truck).
5. **Collision prediction** — `CollisionPredictor` enriches detections with
   `collision_risk` and `collision_eta` from ByteTrack trajectory history.
6. **Annotate** — boxes, proximity alerts, collision overlays, encode to MP4
   (codec fallback: `avc1 → mp4v → H264 → XVID`).

### Post-processing (end of video)

7. **Fog density aggregation** — Average sampled fog density → `fog_level`,
   `visibility_range_m`.
8. **Risk scoring** — `compute_risk_score()` blends fog density, vehicle count,
   proximity danger frames, and collision alert frames into a 0–10 score.
9. **Recommended speed** — Derived from fog level, reduced when `risk_score > 8`.
10. **Analyse** — unique vehicles per class, confidence histogram, timeline,
    road-condition fields stored in `Analytics` and returned via `/results`.

## Analytics dashboard

The frontend **Road Condition Intelligence** section surfaces:

- Fog density (% + level)
- Visibility range (m)
- Road risk score (0–10 + level)
- Recommended safe speed (km/h)

Aggregate averages appear on the dashboard; per-job values appear on the results
page and in history listings.

## Concurrency & persistence

- Each job is processed on a `ThreadPoolExecutor` worker, so HTTP requests never
  block. Progress is written to `backend/data/jobs/<job_id>.json` every few frames.
- That JSON file is the single source of truth and **doubles as local history**,
  surviving backend restarts. No database is used.

## Device strategy

`resolve_device("auto")` selects the best backend in order **cuda → mps → cpu**.
Any unavailable explicit choice falls back to CPU with a warning, so the pipeline
always runs. On Apple Silicon this resolves to **mps**.
