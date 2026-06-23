import type { HistoryItem, JobStatus } from "@/lib/api";

const KEY = "fogvision_history";

export interface LocalHistoryItem {
  job_id: string;
  filename: string;
  created_at: string; // ISO
  total_vehicles: number;
  status: JobStatus;
  fog_density?: number;
  risk_score?: number;
}

export function readHistory(): LocalHistoryItem[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as LocalHistoryItem[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function saveHistoryItem(item: LocalHistoryItem): void {
  if (typeof window === "undefined") return;
  try {
    const existing = readHistory().filter((h) => h.job_id !== item.job_id);
    const next = [item, ...existing].slice(0, 50);
    window.localStorage.setItem(KEY, JSON.stringify(next));
  } catch {
    /* storage may be unavailable */
  }
}

/** Merge local + backend history, dedup by job_id (local wins). */
export function mergeHistory(
  local: LocalHistoryItem[],
  remote: HistoryItem[]
): LocalHistoryItem[] {
  const map = new Map<string, LocalHistoryItem>();
  for (const r of remote) {
    map.set(r.job_id, {
      job_id: r.job_id,
      filename: r.filename,
      created_at: r.created_at,
      total_vehicles: r.total_vehicles,
      status: r.status,
      fog_density: r.fog_density,
      risk_score: r.risk_score,
    });
  }
  for (const l of local) {
    map.set(l.job_id, l);
  }
  return Array.from(map.values()).sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  );
}
