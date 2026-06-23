<div align="center">

# 🌫️ FogVision AI

### Vehicle Detection in Dense Fog using YOLOv8

**Upload foggy traffic footage and instantly identify vehicles using advanced
computer vision powered by YOLOv8 + ByteTrack.**

`FastAPI` · `OpenCV` · `Ultralytics YOLOv8` · `Next.js 15` · `TypeScript` · `TailwindCSS` · `Recharts`

</div>

---

## Overview

FogVision AI is an AI-powered computer-vision platform that detects vehicles in
dense foggy conditions from uploaded videos. It enhances visibility frame-by-frame,
runs YOLOv8 detection with multi-object tracking, renders an annotated video, and
produces a rich analytics dashboard — all locally, with no database, auth, or cloud.

**Detected classes:** Car · Truck · Bus · Motorcycle.

### What it does

1. Processes an uploaded video frame-by-frame — **detection starts automatically the moment you upload**.
2. Enhances visibility in foggy frames (CLAHE, gamma, histogram equalisation, sharpening).
3. Runs YOLOv8 vehicle detection (confidence ≥ 0.4).
4. Tracks objects across frames with ByteTrack and draws boxes + confidence + track id.
5. **Streams a real-time annotated feed** (MJPEG) so you watch detections live as they happen.
6. **Flags vehicles that get too close** with a red box + "TOO CLOSE" tag and a danger banner.
7. **Predicts trajectory-based collisions** using ByteTrack vehicle tracks and estimates **Time-To-Collision (TTC)**.
8. **Surfaces collision risk alerts** with severity-colored boxes, on-box TTC labels, and warning banners.
9. **Estimates fog density** from frame quality metrics (contrast, blur, edge density).
10. **Derives visibility range** from fog conditions (metres).
11. **Computes a dynamic road risk score** (0–10) blending fog, traffic density, proximity alerts, and collision alerts.
12. **Recommends a safe driving speed** based on fog level and composite risk.
13. Generates a downloadable processed MP4 and a full analytics dashboard — including collision analytics and **Road Condition Intelligence** metrics.

### Road Condition Intelligence

The results dashboard and aggregate **Dashboard** view include a dedicated analytics
section powered by `app/pipeline/fog_density.py`:

- **Fog Density** — percentage score (0–100) with level classification (Clear · Moderate · Dense · Severe), sampled from original frames during processing.
- **Visibility Estimation** — inferred range in metres from fog level (e.g. 200 m clear → 30 m severe).
- **Risk Score** — composite 0–10 score (Low · Medium · High · Extreme) from fog density, vehicle count, proximity danger frames, and collision alert frames.
- **Recommended Speed** — safe speed guidance in km/h, reduced further when risk is extreme.

---

## Architecture

```
fog/
├── backend/            FastAPI + OpenCV + Ultralytics YOLOv8
│   └── app/
│       ├── api/         HTTP routes
│       ├── core/        job manager, device detect, logging
│       ├── pipeline/    enhancement · detector · collision · fog_density · annotator · processor
│       └── models/      Pydantic schemas
├── frontend/           Next.js 15 · TS · Tailwind · Framer Motion · Recharts
├── docs/               ARCHITECTURE.md · API.md · INSTALL.md
├── models/             YOLO weights (downloaded at setup)
├── uploads/            uploaded source videos
└── outputs/            processed annotated videos
```

**Processing pipeline (per job):**

```
Video → Enhancement → Detection + Tracking → Collision Prediction
     → Fog Density Estimation → Risk Scoring → Analytics Dashboard
```

See **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** for the full pipeline diagram.

---

## Installation

> **Requires Python 3.11 or 3.12** (PyTorch/Ultralytics have no 3.13/3.14 wheels)
> and **Node.js 18+**. Full guide in **[docs/INSTALL.md](docs/INSTALL.md)**.

### Quickest start — one command

From the repo root, this installs everything on first run and launches both servers:

```bash
./run.sh
```

Then open **http://localhost:3000**. Press `Ctrl+C` once to stop both. To run the
backend and frontend separately, follow the two sections below.

### Running the backend

```bash
cd backend
./setup.sh                       # venv + deps + model weights
source .venv/bin/activate
uvicorn app.main:app --reload    # http://localhost:8000  (docs at /docs)
```

### Running the frontend

```bash
cd frontend
npm install
cp .env.example .env.local       # NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev                      # http://localhost:3000
```

Open **http://localhost:3000**, go to **Detect**, and drop in a foggy clip — detection
streams live immediately. The **Dashboard** and **History** tabs show your analytics.

### Troubleshooting

- **Port 8000 already in use / uploads fail with a weird "field required":** another app
  is on the backend port. `run.sh` now refuses to start in that case. Free it with
  `lsof -ti tcp:8000 | xargs kill -9`, then confirm `curl localhost:8000/` returns
  `"FogVision AI"`. (Don't run two apps on port 8000 at once.)
- **Processed video won't play in the browser:** `brew install ffmpeg` so OpenCV can
  write H.264 (`avc1`) instead of the `mp4v` fallback.
- **`__webpack_modules__ is not a function` in the browser:** stale Next cache — run
  `rm -rf frontend/.next` and restart.
- **`No module named torch` / install fails:** you're on Python 3.13/3.14. Use 3.11 or
  3.12 (`brew install python@3.12`) and re-run `backend/setup.sh`.

> After changing backend code, restart the server (the `run.sh` launch does not use
> `--reload`). For auto-reload during development use `uvicorn app.main:app --reload`.

---

## API usage

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `POST` | `/upload` | Upload a video, returns `job_id` + metadata |
| `POST` | `/process/{job_id}` | Start background processing |
| `GET`  | `/status/{job_id}` | Poll progress (frame / ETA / %) |
| `GET`  | `/stream/{job_id}` | Real-time MJPEG feed of annotated frames |
| `GET`  | `/results/{job_id}` | Analytics + media URLs |
| `GET`  | `/download/{job_id}` | Download the processed MP4 |
| `GET`  | `/history` | List of past jobs |

Quick example:

```bash
JOB=$(curl -s -F "file=@fog_traffic.mp4" http://localhost:8000/upload | python -c "import sys,json;print(json.load(sys.stdin)['job_id'])")
curl -s -X POST http://localhost:8000/process/$JOB
curl -s http://localhost:8000/status/$JOB
```

Full reference: **[docs/API.md](docs/API.md)**.

---

## Configuration

Edit `backend/.env` (copied from `.env.example`):

```env
MODEL_NAME=yolov8n.pt   # swap for yolov8s.pt / yolov8m.pt
CONFIDENCE=0.4
DEVICE=auto             # auto → cuda → mps → cpu
MAX_FRAMES=0            # cap frames for quick demos
DANGER_RATIO=0.5        # box-height/frame-height above this → "too close" alert
CAUTION_RATIO=0.32      # above this → "close" (amber)
```

---

## Performance notes

Optimised for 1080p footage. On consumer NVIDIA GPUs (CUDA) expect ~10–20 FPS with
`yolov8n.pt`. On **Apple Silicon** inference uses the **MPS** backend (auto-detected);
on CPU it still runs but slower — use `MAX_FRAMES` or a smaller resolution for demos.
The first detection of a session includes a one-time model warm-up (a few seconds).

---

## Screenshots

> Add screenshots here after running locally:
>
> - **Landing** — hero with animated particles and vehicle visualization
> - **Upload** — drag-and-drop with thumbnail + metadata
> - **Processing** — progress bar, live frame counter, ETA
> - **Results** — original vs processed players, collision overlays, Road Condition Intelligence cards, charts, before/after slider

| Screen | Image |
|--------|-------|
| Landing | `docs/screenshots/landing.png` |
| Results | `docs/screenshots/results.png` |

---

## Bonus features

- ⚡ **Real-time detection stream** — annotated frames stream live (MJPEG) the instant you upload
- 🚨 **Proximity danger alerts** — vehicles that get too close are flagged red with a "TOO CLOSE" warning banner + alert metrics
- 🚗 **Trajectory-based collision prediction** — ByteTrack trajectories forecast intersecting paths
- ⏱️ **Time-To-Collision (TTC) estimation** — predicted seconds until paths converge
- ⚠️ **Collision risk alerts and warning banners** — severity-colored boxes, on-box TTC, and top-of-frame warnings
- 🌫️ **Fog density estimation** — contrast, blur, and edge-density heuristics scored 0–100%
- 👁️ **Visibility range estimation** — metres inferred from fog level
- 📊 **Dynamic road risk scoring** — composite 0–10 score from fog, traffic, and alert rates
- 🛣️ **Recommended safe speed guidance** — km/h cap adjusted for fog and extreme risk
- 📊 **Analytics dashboard** (`/dashboard`) — aggregate stats across every processed video, including fog density and risk score averages
- 🎞️ Frame-by-frame detection viewer (scrub the processed video)
- 📈 Vehicle timeline graph (per-class counts over time, with danger overlay)
- 📊 Detection confidence distribution chart
- 🪄 Before vs After fog-enhancement comparison slider
- 🗂️ Processing history stored locally (`localStorage` + backend `/history`)

---

## Future improvements

- Lane-level counting and direction estimation
- Speed estimation via homography calibration
- Real-time RTSP/webcam streaming input
- Dehazing with a dedicated defog network (e.g. AOD-Net) before detection
- Export analytics to CSV / PDF report
- GPU batch inference for higher throughput

---

## Tech stack

**Backend:** Python · FastAPI · OpenCV · Ultralytics YOLOv8 · ByteTrack · NumPy
**Frontend:** Next.js 15 · TypeScript · TailwindCSS · Framer Motion · Recharts
**Storage:** local filesystem (JSON job store) — no database, no auth, no cloud.

---

<div align="center">
Built as a production-grade MVP. Premium dark UI, modular AI pipeline, fully local.
</div>
