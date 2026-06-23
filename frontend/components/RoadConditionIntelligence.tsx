"use client";

import { motion } from "framer-motion";
import { CloudFog, Eye, AlertTriangle, GaugeCircle } from "lucide-react";
import type { Analytics } from "@/lib/api";
import { cn } from "@/lib/utils";

type SeverityTone = "success" | "warning" | "orange" | "danger";

const toneStyles: Record<SeverityTone, { bar: string; text: string; bg: string; border: string }> = {
  success: {
    bar: "bg-success",
    text: "text-success",
    bg: "bg-success/10",
    border: "border-success/30",
  },
  warning: {
    bar: "bg-yellow-400",
    text: "text-yellow-400",
    bg: "bg-yellow-400/10",
    border: "border-yellow-400/30",
  },
  orange: {
    bar: "bg-orange-400",
    text: "text-orange-400",
    bg: "bg-orange-400/10",
    border: "border-orange-400/30",
  },
  danger: {
    bar: "bg-danger",
    text: "text-danger",
    bg: "bg-danger/10",
    border: "border-danger/30",
  },
};

function fogTone(level: string): SeverityTone {
  if (level === "Clear") return "success";
  if (level === "Moderate") return "warning";
  if (level === "Dense") return "orange";
  return "danger";
}

function riskTone(level: string): SeverityTone {
  if (level === "Low") return "success";
  if (level === "Medium") return "warning";
  if (level === "High") return "orange";
  return "danger";
}

function GaugeCard({
  icon: Icon,
  title,
  value,
  subtitle,
  tone,
  progress,
  index,
}: {
  icon: typeof CloudFog;
  title: string;
  value: string;
  subtitle: string;
  tone: SeverityTone;
  progress: number;
  index: number;
}) {
  const styles = toneStyles[tone];
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.06, duration: 0.4 }}
      className={cn("glass rounded-2xl border p-5 shadow-card", styles.border, styles.bg)}
    >
      <div className="flex items-start justify-between gap-3">
        <span className={cn("flex h-10 w-10 items-center justify-center rounded-xl", styles.bg, styles.text)}>
          <Icon className="h-5 w-5" />
        </span>
        <span className={cn("rounded-full px-2.5 py-1 text-xs font-semibold uppercase tracking-wide", styles.bg, styles.text)}>
          {subtitle}
        </span>
      </div>
      <p className="mt-4 text-xs uppercase tracking-wide text-slate-500">{title}</p>
      <p className={cn("mt-1 text-2xl font-semibold tracking-tight", styles.text)}>{value}</p>
      <div className="mt-4 h-2 overflow-hidden rounded-full bg-white/5">
        <div
          className={cn("h-full rounded-full transition-all", styles.bar)}
          style={{ width: `${Math.min(100, Math.max(0, progress))}%` }}
        />
      </div>
    </motion.div>
  );
}

export interface RoadConditionMetrics {
  fog_density: number;
  fog_level: string;
  visibility_range_m: number;
  risk_score: number;
  risk_level: string;
  recommended_speed_kmh: number;
}

export function roadMetricsFromAnalytics(a: Analytics): RoadConditionMetrics {
  return {
    fog_density: a.fog_density ?? 0,
    fog_level: a.fog_level ?? "Clear",
    visibility_range_m: a.visibility_range_m ?? 200,
    risk_score: a.risk_score ?? 0,
    risk_level: a.risk_level ?? "Low",
    recommended_speed_kmh: a.recommended_speed_kmh ?? 80,
  };
}

export function RoadConditionIntelligence({
  metrics,
  compact = false,
}: {
  metrics: RoadConditionMetrics;
  compact?: boolean;
}) {
  const fog = fogTone(metrics.fog_level);
  const risk = riskTone(metrics.risk_level);
  const speedTone: SeverityTone =
    metrics.risk_score > 8 ? "danger" : metrics.risk_score > 6 ? "orange" : fog;

  return (
    <section className={compact ? "space-y-4" : "space-y-6"}>
      <div>
        <h3 className="text-lg font-semibold">Road Condition Intelligence</h3>
        {!compact && (
          <p className="mt-1 text-sm text-slate-400">
            Fog density, visibility, composite risk, and recommended safe speed for this clip.
          </p>
        )}
      </div>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <GaugeCard
          icon={CloudFog}
          title="Fog Density"
          value={`${metrics.fog_density.toFixed(0)}%`}
          subtitle={metrics.fog_level}
          tone={fog}
          progress={metrics.fog_density}
          index={0}
        />
        <GaugeCard
          icon={Eye}
          title="Visibility"
          value={`${Math.round(metrics.visibility_range_m)} m`}
          subtitle={metrics.fog_level}
          tone={fog}
          progress={Math.min(100, (metrics.visibility_range_m / 200) * 100)}
          index={1}
        />
        <GaugeCard
          icon={AlertTriangle}
          title="Risk Score"
          value={`${metrics.risk_score.toFixed(1)} / 10`}
          subtitle={metrics.risk_level}
          tone={risk}
          progress={(metrics.risk_score / 10) * 100}
          index={2}
        />
        <GaugeCard
          icon={GaugeCircle}
          title="Recommended Speed"
          value={`${metrics.recommended_speed_kmh} km/h`}
          subtitle={metrics.risk_level}
          tone={speedTone}
          progress={(metrics.recommended_speed_kmh / 80) * 100}
          index={3}
        />
      </div>
    </section>
  );
}
