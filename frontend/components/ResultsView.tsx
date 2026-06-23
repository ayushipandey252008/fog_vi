"use client";

import { motion } from "framer-motion";
import {
  Car,
  Truck,
  Bus,
  Bike,
  Layers,
  Gauge,
  Timer,
  Activity,
  Download,
  RotateCcw,
  ShieldAlert,
  ShieldCheck,
} from "lucide-react";
import { apiBase, downloadUrl, type ResultsResponse } from "@/lib/api";
import { formatDuration, formatNumber } from "@/lib/utils";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { MetricCard } from "@/components/MetricCard";
import { ClassCountsChart } from "@/components/charts/ClassCountsChart";
import { ConfidenceChart } from "@/components/charts/ConfidenceChart";
import { TimelineChart } from "@/components/charts/TimelineChart";
import { BeforeAfterSlider } from "@/components/BeforeAfterSlider";
import { FrameViewer } from "@/components/FrameViewer";
import {
  RoadConditionIntelligence,
  roadMetricsFromAnalytics,
} from "@/components/RoadConditionIntelligence";

interface Props {
  results: ResultsResponse;
  fps: number;
  onReset: () => void;
}

function VideoPanel({ label, src, tone }: { label: string; src: string; tone: "neutral" | "accent" }) {
  return (
    <Card className="p-4">
      <div className="mb-3 flex items-center justify-between">
        <span className="text-sm font-medium text-slate-200">{label}</span>
        <Badge tone={tone === "accent" ? "accent" : "neutral"}>
          {tone === "accent" ? "Detections" : "Source"}
        </Badge>
      </div>
      <video
        src={src}
        controls
        playsInline
        preload="metadata"
        className="aspect-video w-full rounded-xl bg-black"
      />
    </Card>
  );
}

export function ResultsView({ results, fps, onReset }: Props) {
  const a = results.analytics;
  const originalSrc = apiBase(results.original_url);
  const processedSrc = apiBase(results.processed_url);

  const dangerAlerts = a.danger_alerts ?? 0;
  const metrics = [
    { icon: Layers, label: "Total Vehicles", value: formatNumber(a.total_vehicles), accent: "primary" as const },
    { icon: Car, label: "Cars", value: formatNumber(a.cars), accent: "primary" as const },
    { icon: Truck, label: "Trucks", value: formatNumber(a.trucks), accent: "accent" as const },
    { icon: Bus, label: "Buses", value: formatNumber(a.buses), accent: "success" as const },
    { icon: Bike, label: "Motorcycles", value: formatNumber(a.motorcycles), accent: "accent" as const },
    {
      icon: dangerAlerts > 0 ? ShieldAlert : ShieldCheck,
      label: "Proximity Alerts",
      value: formatNumber(dangerAlerts),
      accent: (dangerAlerts > 0 ? "danger" : "success") as "danger" | "success",
    },
    { icon: Gauge, label: "Avg Confidence", value: `${(a.average_confidence * 100).toFixed(1)}%`, accent: "success" as const },
    { icon: Timer, label: "Processing Time", value: formatDuration(a.processing_time_s), accent: "primary" as const },
    { icon: Activity, label: "FPS Processed", value: a.fps_processed.toFixed(1), accent: "accent" as const },
  ];

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      className="space-y-10"
    >
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-semibold tracking-tight">
            Detection results
          </h2>
          <p className="mt-1 text-sm text-slate-400">
            Job <span className="font-mono text-slate-300">{results.job_id}</span>
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Button href={downloadUrl(results.job_id)} external variant="secondary">
            <Download className="h-4 w-4" />
            Download
          </Button>
          <Button onClick={onReset}>
            <RotateCcw className="h-4 w-4" />
            Process another
          </Button>
        </div>
      </div>

      {/* proximity danger alert */}
      {dangerAlerts > 0 && (
        <motion.div
          initial={{ opacity: 0, scale: 0.98 }}
          animate={{ opacity: 1, scale: 1 }}
          className="flex items-center gap-4 rounded-2xl border border-danger/40 bg-danger/10 px-5 py-4"
        >
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-danger/20 text-danger">
            <ShieldAlert className="h-6 w-6" />
          </span>
          <div>
            <p className="font-semibold text-danger">Danger: vehicles came too close</p>
            <p className="mt-0.5 text-sm text-slate-300">
              {formatNumber(dangerAlerts)} frame{dangerAlerts === 1 ? "" : "s"} flagged
              {a.danger_vehicles > 0
                ? ` across ${formatNumber(a.danger_vehicles)} vehicle${a.danger_vehicles === 1 ? "" : "s"}`
                : ""}
              {a.max_proximity > 0
                ? ` · closest approach filled ${(a.max_proximity * 100).toFixed(0)}% of the frame height`
                : ""}
              . Watch for the red boxes and warning banner in the processed video.
            </p>
          </div>
        </motion.div>
      )}

      <RoadConditionIntelligence metrics={roadMetricsFromAnalytics(a)} />

      {/* video players */}
      <div className="grid gap-6 lg:grid-cols-2">
        <VideoPanel label="Original" src={originalSrc} tone="neutral" />
        <VideoPanel label="Processed" src={processedSrc} tone="accent" />
      </div>

      {/* metrics */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
        {metrics.map((m, i) => (
          <MetricCard key={m.label} index={i} {...m} />
        ))}
      </div>

      {/* charts */}
      <div className="grid gap-6 lg:grid-cols-2">
        <ClassCountsChart analytics={a} />
        <ConfidenceChart data={results.confidence_hist} />
      </div>
      <TimelineChart data={results.timeline} />

      {/* before / after */}
      <div>
        <h3 className="mb-4 text-lg font-semibold">
          Fog enhancement · before &amp; after
        </h3>
        <BeforeAfterSlider
          before={results.before_after.original}
          after={results.before_after.enhanced}
          beforeLabel="Foggy original"
          afterLabel="Enhanced"
        />
        <p className="mt-3 text-xs text-slate-500">
          Drag the handle to compare the raw foggy frame against the enhanced
          input used for detection.
        </p>
      </div>

      {/* frame-by-frame */}
      <div>
        <h3 className="mb-4 text-lg font-semibold">Frame-by-frame viewer</h3>
        <FrameViewer src={processedSrc} fps={fps} />
        <p className="mt-3 text-xs text-slate-500">
          Step through the processed video one frame at a time to inspect
          individual detections.
        </p>
      </div>
    </motion.div>
  );
}
