"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Loader2 } from "lucide-react";
import {
  ApiError,
  getResults,
  getStatus,
  modelFileName,
  startProcessing,
  uploadVideo,
  type ResultsResponse,
  type StatusResponse,
  type UploadResponse,
} from "@/lib/api";
import { saveHistoryItem } from "@/lib/history";
import {
  DEFAULT_CONFIG,
  type DetectionConfig,
} from "@/components/EnhancementSettings";
import { UploadStage } from "@/components/UploadStage";
import { ProcessingView } from "@/components/ProcessingView";
import { ResultsView } from "@/components/ResultsView";

type Stage = "idle" | "uploaded" | "processing" | "results";

const POLL_MS = 1000;

const steps: { key: Stage; label: string }[] = [
  { key: "idle", label: "Upload" },
  { key: "processing", label: "Detect" },
  { key: "results", label: "Results" },
];

function stageIndex(stage: Stage): number {
  return steps.findIndex((s) => s.key === stage);
}

export function Workflow() {
  const params = useSearchParams();
  const jobParam = params.get("job");

  const [stage, setStage] = useState<Stage>("idle");
  const [uploading, setUploading] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const [upload, setUpload] = useState<UploadResponse | null>(null);
  const [config, setConfig] = useState<DetectionConfig>(DEFAULT_CONFIG);
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [results, setResults] = useState<ResultsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loadingJob, setLoadingJob] = useState(false);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const previewRef = useRef<string | null>(null);

  const clearPoll = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const revokePreview = useCallback(() => {
    if (previewRef.current) {
      URL.revokeObjectURL(previewRef.current);
      previewRef.current = null;
    }
  }, []);

  useEffect(() => () => {
    clearPoll();
    revokePreview();
  }, [clearPoll, revokePreview]);

  const finalizeResults = useCallback((res: ResultsResponse) => {
    setResults(res);
    setStage("results");
    saveHistoryItem({
      job_id: res.job_id,
      filename: upload?.filename ?? res.job_id,
      created_at: new Date().toISOString(),
      total_vehicles: res.analytics.total_vehicles,
      status: "completed",
      fog_density: res.analytics.fog_density,
      risk_score: res.analytics.risk_score,
    });
  }, [upload?.filename]);

  // Deep-link: ?job=<id> → load results directly.
  useEffect(() => {
    if (!jobParam) return;
    let cancelled = false;
    setLoadingJob(true);
    setError(null);
    (async () => {
      try {
        const res = await getResults(jobParam);
        if (cancelled) return;
        setResults(res);
        setStage("results");
        saveHistoryItem({
          job_id: res.job_id,
          filename: res.job_id,
          created_at: new Date().toISOString(),
          total_vehicles: res.analytics.total_vehicles,
          status: "completed",
          fog_density: res.analytics.fog_density,
          risk_score: res.analytics.risk_score,
        });
      } catch (err) {
        if (cancelled) return;
        setError(
          err instanceof ApiError
            ? err.message
            : "Could not load that job's results."
        );
        setStage("idle");
      } finally {
        if (!cancelled) setLoadingJob(false);
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobParam]);

  const beginPolling = useCallback(
    (id: string) => {
      clearPoll();
      pollRef.current = setInterval(async () => {
        try {
          const s = await getStatus(id);
          setStatus(s);
          if (s.status === "completed") {
            clearPoll();
            try {
              const res = await getResults(id);
              finalizeResults(res);
            } catch (err) {
              setError(
                err instanceof ApiError
                  ? err.message
                  : "Detection finished but results could not be loaded."
              );
            }
          } else if (s.status === "failed") {
            clearPoll();
            setError(s.error ?? "Detection failed during processing.");
          }
        } catch (err) {
          clearPoll();
          setError(
            err instanceof ApiError
              ? err.message
              : "Lost connection to the backend while processing."
          );
        }
      }, POLL_MS);
    },
    [clearPoll, finalizeResults]
  );

  // Upload, then immediately start real-time detection — no manual step.
  const handleFile = useCallback(
    async (file: File) => {
      setError(null);
      setUploading(true);
      setStatus(null);
      try {
        const res = await uploadVideo(file);
        setUpload(res);
        await startProcessing(res.job_id, {
          enhancement: config.enhancement,
          model_name: modelFileName(config.model_name),
          conf: config.conf,
        });
        setJobId(res.job_id);
        setStage("processing");
        beginPolling(res.job_id);
      } catch (err) {
        setError(
          err instanceof ApiError ? err.message : "Upload failed. Please retry."
        );
      } finally {
        setUploading(false);
      }
    },
    [config, beginPolling]
  );

  const handleReset = useCallback(() => {
    clearPoll();
    revokePreview();
    setStage("idle");
    setUpload(null);
    setJobId(null);
    setStatus(null);
    setResults(null);
    setError(null);
    setConfig(DEFAULT_CONFIG);
  }, [clearPoll, revokePreview]);

  const handleRetry = useCallback(() => {
    handleReset();
  }, [handleReset]);

  const activeIdx = stageIndex(stage);

  if (loadingJob) {
    return (
      <div className="flex items-center justify-center py-32 text-slate-400">
        <Loader2 className="mr-3 h-6 w-6 animate-spin text-accent" />
        Loading job…
      </div>
    );
  }

  return (
    <div>
      {/* stepper */}
      <div className="mb-10 flex items-center gap-2">
        {steps.map((s, i) => {
          const done = i < activeIdx;
          const active = i === activeIdx;
          return (
            <div key={s.key} className="flex flex-1 items-center gap-2">
              <div className="flex items-center gap-2">
                <span
                  className={[
                    "flex h-8 w-8 items-center justify-center rounded-full text-sm font-medium transition-colors",
                    active
                      ? "bg-gradient-accent text-white shadow-glow"
                      : done
                      ? "bg-success/20 text-success"
                      : "bg-white/5 text-slate-500",
                  ].join(" ")}
                >
                  {i + 1}
                </span>
                <span
                  className={[
                    "hidden text-sm sm:inline",
                    active ? "text-white" : "text-slate-500",
                  ].join(" ")}
                >
                  {s.label}
                </span>
              </div>
              {i < steps.length - 1 && (
                <span
                  className={[
                    "h-px flex-1 transition-colors",
                    i < activeIdx ? "bg-success/40" : "bg-white/10",
                  ].join(" ")}
                />
              )}
            </div>
          );
        })}
      </div>

      {stage === "idle" && (
        <UploadStage
          uploading={uploading}
          error={error}
          config={config}
          onFile={handleFile}
          onConfigChange={setConfig}
        />
      )}

      {stage === "processing" && (
        <ProcessingView
          status={status}
          jobId={jobId}
          error={error}
          onRetry={handleRetry}
        />
      )}

      {stage === "results" && results && (
        <ResultsView
          results={results}
          fps={upload?.fps ?? 30}
          onReset={handleReset}
        />
      )}
    </div>
  );
}
