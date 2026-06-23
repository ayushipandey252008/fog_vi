// Typed API client for the FogVision AI backend.

export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** Build an absolute media URL from a backend-relative path. */
export function apiBase(path: string): string {
  if (!path) return "";
  if (/^https?:\/\//i.test(path)) return path;
  const base = API_BASE.replace(/\/+$/, "");
  const rel = path.startsWith("/") ? path : `/${path}`;
  return `${base}${rel}`;
}

// ---------------------------------------------------------------------------
// Response & request types
// ---------------------------------------------------------------------------

export type JobStatus = "queued" | "processing" | "completed" | "failed";

export interface UploadResponse {
  job_id: string;
  filename: string;
  size_bytes: number;
  duration_s: number;
  fps: number;
  frame_count: number;
  width: number;
  height: number;
  thumbnail: string; // data URL
}

export interface EnhancementSettings {
  clahe: boolean;
  gamma: number;
  hist_eq: boolean;
  sharpen: boolean;
}

export type ModelName = "n" | "s" | "m";

export interface ProcessRequest {
  enhancement?: EnhancementSettings;
  // Full Ultralytics checkpoint name, e.g. "yolov8n.pt".
  model_name?: string;
  conf?: number;
}

/** Map the UI model size ("n" | "s" | "m") to the backend checkpoint name. */
export function modelFileName(size: ModelName): string {
  return `yolov8${size}.pt`;
}

export interface ProcessResponse {
  job_id: string;
  status: JobStatus;
}

export interface StatusResponse {
  job_id: string;
  status: JobStatus;
  progress: number; // 0..1
  current_frame: number;
  total_frames: number;
  eta_seconds: number;
  error?: string;
  preview_url?: string | null; // live annotated frame while processing
}

export interface Analytics {
  total_vehicles: number;
  cars: number;
  trucks: number;
  buses: number;
  motorcycles: number;
  average_confidence: number;
  processing_time_s: number;
  fps_processed: number;
  danger_alerts: number;
  danger_vehicles: number;
  max_proximity: number;
  fog_density: number;
  fog_level: string;
  visibility_range_m: number;
  risk_score: number;
  risk_level: string;
  recommended_speed_kmh: number;
}

export interface TimelinePoint {
  frame: number;
  t: number;
  cars: number;
  trucks: number;
  buses: number;
  motorcycles: number;
  total: number;
  danger: number;
}

export interface ConfidenceBucket {
  bucket: string;
  count: number;
}

export interface BeforeAfter {
  original: string; // data URL
  enhanced: string; // data URL
}

export interface ResultsResponse {
  job_id: string;
  status: JobStatus;
  analytics: Analytics;
  timeline: TimelinePoint[];
  confidence_hist: ConfidenceBucket[];
  before_after: BeforeAfter;
  original_url: string;
  processed_url: string;
}

export interface HistoryItem {
  job_id: string;
  filename: string;
  created_at: string;
  status: JobStatus;
  total_vehicles: number;
  cars?: number;
  trucks?: number;
  buses?: number;
  motorcycles?: number;
  average_confidence?: number;
  processing_time_s?: number;
  fps_processed?: number;
  fog_density?: number;
  risk_score?: number;
}

// ---------------------------------------------------------------------------
// Error helper
// ---------------------------------------------------------------------------

export class ApiError extends Error {
  status?: number;
  constructor(message: unknown, status?: number) {
    super(typeof message === "string" ? message : "Unexpected error");
    this.name = "ApiError";
    this.status = status;
  }
}

/** Normalize FastAPI error bodies (string, {detail}, or 422 detail arrays) to text. */
function extractDetail(data: unknown, fallback: string): string {
  if (typeof data === "string") return data || fallback;
  if (data && typeof data === "object") {
    const obj = data as Record<string, unknown>;
    const d = obj.detail ?? obj.message;
    if (typeof d === "string") return d;
    if (Array.isArray(d)) {
      // FastAPI 422 validation errors: [{ loc, msg, type }, ...]
      const msgs = d
        .map((e) =>
          e && typeof e === "object" && "msg" in e
            ? String((e as Record<string, unknown>).msg)
            : typeof e === "string"
            ? e
            : null
        )
        .filter(Boolean);
      if (msgs.length) return msgs.join("; ");
    }
    if (d && typeof d === "object") {
      try {
        return JSON.stringify(d);
      } catch {
        /* fall through */
      }
    }
  }
  return fallback;
}

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const fallback = `Request failed (${res.status})`;
    let detail = fallback;
    try {
      detail = extractDetail(await res.json(), fallback);
    } catch {
      /* ignore non-JSON error bodies */
    }
    throw new ApiError(detail, res.status);
  }
  return (await res.json()) as T;
}

function networkMessage(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  return "Could not reach the FogVision backend. Make sure it is running at " + API_BASE + ".";
}

// ---------------------------------------------------------------------------
// API calls
// ---------------------------------------------------------------------------

export async function uploadVideo(file: File): Promise<UploadResponse> {
  const form = new FormData();
  // Explicit filename ensures the part is sent as a file even if something
  // (e.g. a browser extension) would otherwise drop it.
  form.append("file", file, file.name);
  try {
    const res = await fetch(`${API_BASE}/upload`, {
      method: "POST",
      body: form,
    });
    return await handle<UploadResponse>(res);
  } catch (err) {
    throw new ApiError(networkMessage(err));
  }
}

export async function startProcessing(
  jobId: string,
  body: ProcessRequest
): Promise<ProcessResponse> {
  try {
    const res = await fetch(`${API_BASE}/process/${encodeURIComponent(jobId)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    return await handle<ProcessResponse>(res);
  } catch (err) {
    throw new ApiError(networkMessage(err));
  }
}

export async function getStatus(jobId: string): Promise<StatusResponse> {
  try {
    const res = await fetch(`${API_BASE}/status/${encodeURIComponent(jobId)}`, {
      cache: "no-store",
    });
    return await handle<StatusResponse>(res);
  } catch (err) {
    throw new ApiError(networkMessage(err));
  }
}

export async function getResults(jobId: string): Promise<ResultsResponse> {
  try {
    const res = await fetch(`${API_BASE}/results/${encodeURIComponent(jobId)}`, {
      cache: "no-store",
    });
    return await handle<ResultsResponse>(res);
  } catch (err) {
    throw new ApiError(networkMessage(err));
  }
}

export function downloadUrl(jobId: string): string {
  return `${API_BASE}/download/${encodeURIComponent(jobId)}`;
}

export async function getHistory(): Promise<HistoryItem[]> {
  try {
    const res = await fetch(`${API_BASE}/history`, { cache: "no-store" });
    return await handle<HistoryItem[]>(res);
  } catch {
    // Best-effort: backend may be down.
    return [];
  }
}
