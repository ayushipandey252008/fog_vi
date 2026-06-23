"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { Clock, ArrowUpRight, Car, CloudFog, AlertTriangle } from "lucide-react";
import type { LocalHistoryItem } from "@/lib/history";
import { formatDate, formatNumber } from "@/lib/utils";
import { Badge } from "@/components/ui/Badge";
import type { JobStatus } from "@/lib/api";

function statusTone(s: JobStatus): "success" | "danger" | "primary" | "neutral" {
  if (s === "completed") return "success";
  if (s === "failed") return "danger";
  if (s === "processing") return "primary";
  return "neutral";
}

export function HistoryList({ items }: { items: LocalHistoryItem[] }) {
  if (items.length === 0) {
    return (
      <div className="glass flex flex-col items-center rounded-2xl px-8 py-16 text-center">
        <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-white/5 text-slate-400">
          <Clock className="h-7 w-7" />
        </span>
        <h3 className="mt-5 text-lg font-semibold">No detections yet</h3>
        <p className="mt-2 max-w-sm text-sm text-slate-400">
          Completed jobs will appear here. Upload a foggy clip to get started.
        </p>
        <Link
          href="/app"
          className="mt-6 rounded-2xl bg-gradient-accent px-5 py-2.5 text-sm font-medium text-white shadow-glow hover:brightness-110"
        >
          Upload video
        </Link>
      </div>
    );
  }

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {items.map((item, i) => (
        <motion.div
          key={item.job_id}
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: i * 0.04, duration: 0.4 }}
        >
          <Link
            href={`/app?job=${encodeURIComponent(item.job_id)}`}
            className="glass group block h-full rounded-2xl p-5 shadow-card transition-colors hover:border-white/25"
          >
            <div className="flex items-start justify-between gap-3">
              <h3 className="truncate text-sm font-semibold" title={item.filename}>
                {item.filename}
              </h3>
              <ArrowUpRight className="h-4 w-4 shrink-0 text-slate-500 transition-colors group-hover:text-accent" />
            </div>
            <p className="mt-1 flex items-center gap-1.5 text-xs text-slate-500">
              <Clock className="h-3.5 w-3.5" />
              {formatDate(item.created_at)}
            </p>
            <div className="mt-4 flex flex-wrap items-center justify-between gap-2">
              <span className="flex items-center gap-1.5 text-sm text-slate-300">
                <Car className="h-4 w-4 text-accent" />
                {formatNumber(item.total_vehicles)} vehicles
              </span>
              <div className="flex flex-wrap items-center gap-2">
                {(item.fog_density ?? 0) > 0 && (
                  <span className="flex items-center gap-1 text-xs text-slate-400">
                    <CloudFog className="h-3.5 w-3.5" />
                    {Math.round(item.fog_density ?? 0)}% fog
                  </span>
                )}
                {(item.risk_score ?? 0) > 0 && (
                  <span className="flex items-center gap-1 text-xs text-danger">
                    <AlertTriangle className="h-3.5 w-3.5" />
                    Risk {(item.risk_score ?? 0).toFixed(1)}
                  </span>
                )}
                <Badge tone={statusTone(item.status)}>{item.status}</Badge>
              </div>
            </div>
          </Link>
        </motion.div>
      ))}
    </div>
  );
}
