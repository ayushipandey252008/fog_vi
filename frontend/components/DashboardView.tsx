"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  Activity,
  Car,
  Bus,
  Bike,
  Gauge,
  Film,
  Layers,
  Truck,
  ArrowRight,
  LayoutDashboard,
  CloudFog,
  AlertTriangle,
} from "lucide-react";
import { getHistory, type HistoryItem } from "@/lib/api";
import { formatDate, formatDuration, formatNumber } from "@/lib/utils";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { MetricCard } from "@/components/MetricCard";
import { ChartShell, chartColors, tooltipStyle } from "@/components/charts/ChartShell";
import {
  RoadConditionIntelligence,
  type RoadConditionMetrics,
} from "@/components/RoadConditionIntelligence";

interface Totals {
  videos: number;
  total: number;
  cars: number;
  trucks: number;
  buses: number;
  motorcycles: number;
  avgConfidence: number;
  avgFps: number;
  totalTime: number;
  avgFogDensity: number;
  avgRiskScore: number;
}

function aggregate(items: HistoryItem[]): Totals {
  const t: Totals = {
    videos: items.length,
    total: 0,
    cars: 0,
    trucks: 0,
    buses: 0,
    motorcycles: 0,
    avgConfidence: 0,
    avgFps: 0,
    totalTime: 0,
    avgFogDensity: 0,
    avgRiskScore: 0,
  };
  let confSum = 0;
  let confCount = 0;
  let fpsSum = 0;
  let fpsCount = 0;
  let fogSum = 0;
  let fogCount = 0;
  let riskSum = 0;
  let riskCount = 0;
  for (const it of items) {
    t.total += it.total_vehicles ?? 0;
    t.cars += it.cars ?? 0;
    t.trucks += it.trucks ?? 0;
    t.buses += it.buses ?? 0;
    t.motorcycles += it.motorcycles ?? 0;
    t.totalTime += it.processing_time_s ?? 0;
    if (it.average_confidence) {
      confSum += it.average_confidence;
      confCount += 1;
    }
    if (it.fps_processed) {
      fpsSum += it.fps_processed;
      fpsCount += 1;
    }
    if (it.fog_density != null && it.fog_density > 0) {
      fogSum += it.fog_density;
      fogCount += 1;
    }
    if (it.risk_score != null && it.risk_score > 0) {
      riskSum += it.risk_score;
      riskCount += 1;
    }
  }
  t.avgConfidence = confCount ? confSum / confCount : 0;
  t.avgFps = fpsCount ? fpsSum / fpsCount : 0;
  t.avgFogDensity = fogCount ? fogSum / fogCount : 0;
  t.avgRiskScore = riskCount ? riskSum / riskCount : 0;
  return t;
}

export function DashboardView() {
  const [items, setItems] = useState<HistoryItem[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const remote = await getHistory(); // best-effort; [] when backend is down
      if (cancelled) return;
      setItems(remote.filter((r) => r.status === "completed"));
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const totals = useMemo(() => aggregate(items ?? []), [items]);

  const classData = useMemo(
    () => [
      { name: "Cars", value: totals.cars, fill: chartColors.cars },
      { name: "Trucks", value: totals.trucks, fill: chartColors.trucks },
      { name: "Buses", value: totals.buses, fill: chartColors.buses },
      { name: "Motorcycles", value: totals.motorcycles, fill: chartColors.motorcycles },
    ],
    [totals]
  );

  const perVideo = useMemo(
    () =>
      (items ?? [])
        .slice(0, 12)
        .reverse()
        .map((it, i) => ({
          name: it.filename.length > 14 ? `#${i + 1}` : it.filename,
          vehicles: it.total_vehicles ?? 0,
          job_id: it.job_id,
        })),
    [items]
  );

  const metrics = [
    { icon: Film, label: "Videos Processed", value: formatNumber(totals.videos), accent: "primary" as const },
    { icon: Layers, label: "Total Vehicles", value: formatNumber(totals.total), accent: "primary" as const },
    { icon: CloudFog, label: "Avg Fog Density", value: `${totals.avgFogDensity.toFixed(0)}%`, accent: "accent" as const },
    { icon: AlertTriangle, label: "Avg Risk Score", value: totals.avgRiskScore.toFixed(1), accent: "danger" as const },
    { icon: Car, label: "Cars", value: formatNumber(totals.cars), accent: "primary" as const },
    { icon: Truck, label: "Trucks", value: formatNumber(totals.trucks), accent: "accent" as const },
    { icon: Bus, label: "Buses", value: formatNumber(totals.buses), accent: "success" as const },
    { icon: Bike, label: "Motorcycles", value: formatNumber(totals.motorcycles), accent: "accent" as const },
    { icon: Gauge, label: "Avg Confidence", value: `${(totals.avgConfidence * 100).toFixed(1)}%`, accent: "success" as const },
    { icon: Activity, label: "Avg FPS", value: totals.avgFps.toFixed(1), accent: "accent" as const },
  ];

  const hasData = (items?.length ?? 0) > 0;

  const aggregateRoadMetrics: RoadConditionMetrics | null = useMemo(() => {
    if (!hasData || totals.avgFogDensity <= 0) return null;
    const fogLevel =
      totals.avgFogDensity <= 30
        ? "Clear"
        : totals.avgFogDensity <= 60
        ? "Moderate"
        : totals.avgFogDensity <= 80
        ? "Dense"
        : "Severe";
    const visibility =
      fogLevel === "Clear"
        ? 200
        : fogLevel === "Moderate"
        ? 100
        : fogLevel === "Dense"
        ? 50
        : 30;
    const riskLevel =
      totals.avgRiskScore <= 3
        ? "Low"
        : totals.avgRiskScore <= 6
        ? "Medium"
        : totals.avgRiskScore <= 8
        ? "High"
        : "Extreme";
    const speedBase =
      fogLevel === "Clear" ? 80 : fogLevel === "Moderate" ? 60 : fogLevel === "Dense" ? 40 : 20;
    return {
      fog_density: totals.avgFogDensity,
      fog_level: fogLevel,
      visibility_range_m: visibility,
      risk_score: totals.avgRiskScore,
      risk_level: riskLevel,
      recommended_speed_kmh: totals.avgRiskScore > 8 ? Math.max(20, speedBase - 20) : speedBase,
    };
  }, [hasData, totals]);

  return (
    <div className="space-y-10">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <span className="flex items-center gap-2 text-sm text-accent">
            <LayoutDashboard className="h-4 w-4" /> Analytics
          </span>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight">Dashboard</h1>
          <p className="mt-1 text-sm text-slate-400">
            Aggregate detection analytics across every processed video.
          </p>
        </div>
        <Button href="/app">
          New detection <ArrowRight className="h-4 w-4" />
        </Button>
      </div>

      {items === null ? (
        <div className="py-24 text-center text-slate-500">Loading analytics…</div>
      ) : !hasData ? (
        <Card className="flex flex-col items-center justify-center gap-4 py-20 text-center">
          <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-white/5">
            <LayoutDashboard className="h-7 w-7 text-slate-500" />
          </span>
          <div>
            <p className="text-lg font-medium">No analytics yet</p>
            <p className="mt-1 text-sm text-slate-500">
              Process a foggy video and its detection metrics will appear here.
              (If the backend isn&apos;t running, start it to see your history.)
            </p>
          </div>
          <Button href="/app">Upload a video</Button>
        </Card>
      ) : (
        <>
          {/* metric cards */}
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
            {metrics.map((m, i) => (
              <MetricCard key={m.label} index={i} {...m} />
            ))}
          </div>

          {aggregateRoadMetrics && (
            <RoadConditionIntelligence metrics={aggregateRoadMetrics} compact />
          )}

          {/* charts */}
          <div className="grid gap-6 lg:grid-cols-2">
            <ChartShell title="Vehicle class distribution" subtitle="All videos combined">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={classData}
                    dataKey="value"
                    nameKey="name"
                    innerRadius="55%"
                    outerRadius="80%"
                    paddingAngle={2}
                    stroke="none"
                  >
                    {classData.map((d) => (
                      <Cell key={d.name} fill={d.fill} />
                    ))}
                  </Pie>
                  <Tooltip contentStyle={tooltipStyle} />
                  <Legend
                    verticalAlign="bottom"
                    iconType="circle"
                    formatter={(v) => <span className="text-xs text-slate-400">{v}</span>}
                  />
                </PieChart>
              </ResponsiveContainer>
            </ChartShell>

            <ChartShell title="Vehicles per video" subtitle="Most recent 12 jobs">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={perVideo} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke={chartColors.grid} vertical={false} />
                  <XAxis dataKey="name" stroke={chartColors.axis} tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
                  <YAxis stroke={chartColors.axis} tick={{ fontSize: 12 }} tickLine={false} axisLine={false} allowDecimals={false} />
                  <Tooltip contentStyle={tooltipStyle} cursor={{ fill: "rgba(255,255,255,0.04)" }} />
                  <Bar dataKey="vehicles" name="Vehicles" fill={chartColors.count} radius={[6, 6, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </ChartShell>
          </div>

          {/* recent jobs table */}
          <Card>
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-base font-semibold">Recent detections</h3>
              <span className="text-xs text-slate-500">
                {formatDuration(totals.totalTime)} total processing time
              </span>
            </div>
            <div className="divide-y divide-white/5">
              {(items ?? []).slice(0, 10).map((it) => (
                <motion.div
                  key={it.job_id}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className="flex items-center justify-between gap-4 py-3"
                >
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-slate-200">{it.filename}</p>
                    <p className="text-xs text-slate-500">{formatDate(it.created_at)}</p>
                  </div>
                  <div className="flex items-center gap-4">
                    {(it.fog_density ?? 0) > 0 && (
                      <Badge tone="neutral">{Math.round(it.fog_density ?? 0)}% fog</Badge>
                    )}
                    {(it.risk_score ?? 0) > 0 && (
                      <Badge tone="danger">Risk {(it.risk_score ?? 0).toFixed(1)}</Badge>
                    )}
                    <Badge tone="accent">{formatNumber(it.total_vehicles)} vehicles</Badge>
                    <Link
                      href={`/app?job=${encodeURIComponent(it.job_id)}`}
                      className="flex items-center gap-1 text-sm text-accent hover:text-white"
                    >
                      View <ArrowRight className="h-3.5 w-3.5" />
                    </Link>
                  </div>
                </motion.div>
              ))}
            </div>
          </Card>
        </>
      )}
    </div>
  );
}
