"use client";

import { Bar, BarChart, CartesianGrid, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { TrendingUp, DollarSign } from "lucide-react";
import type { FundingSection } from "@/lib/types";
import { palette } from "@/lib/theme";

// chart values are in $M; show compact labels ($0.02M, $0.6M, $1B)
function fmtChartValue(v: number): string {
  return v >= 1000 ? `$${+(v / 1000).toFixed(1)}B` : `$${+v.toFixed(2)}M`;
}

export function Funding({ data, eyebrow }: { data: FundingSection; eyebrow: string }) {
  return (
    <section className="mx-auto max-w-3xl px-6 py-20">
      <p className="text-sm font-bold uppercase tracking-widest text-orange">✦ {eyebrow}</p>
      <h2 className="mt-3 font-display text-3xl font-extrabold sm:text-5xl">{data.title}</h2>
      {data.narrative && <p className="mt-4 text-lg text-ink/75">{data.narrative}</p>}

      {data.chart.length > 0 && (
        <div className="mt-8 rounded-2xl border border-ink/10 bg-white p-5 shadow-sm">
          <div className="mb-3 flex items-center gap-2 text-sm font-bold text-ink/70">
            <TrendingUp size={16} className="text-bluebrand" /> Capital raised
            {data.chart[0].unit ? ` (${data.chart[0].unit})` : ""}
          </div>
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={data.chart}>
              <defs>
                <linearGradient id="fund" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={palette.blue} stopOpacity={0.95} />
                  <stop offset="100%" stopColor={palette.blue} stopOpacity={0.5} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke={palette.lilac} vertical={false} />
              <XAxis dataKey="label" tick={{ fontSize: 12 }} />
              <YAxis tick={{ fontSize: 12 }} />
              <Tooltip cursor={{ fill: palette.lilac, fillOpacity: 0.3 }} />
              <Bar dataKey="value" fill="url(#fund)" radius={[6, 6, 0, 0]} minPointSize={4}>
                <LabelList
                  dataKey="value"
                  position="top"
                  fontSize={11}
                  fill={palette.ink}
                  formatter={(v: number) => fmtChartValue(v)}
                />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {data.rounds.length > 0 && (
        <div className="mt-6 grid gap-3 sm:grid-cols-2">
          {data.rounds.map((r, i) => (
            <div key={i} className="rounded-2xl border border-ink/10 bg-cream p-4">
              <div className="flex items-center justify-between">
                <span className="font-display font-bold">{r.label}</span>
                <span className="text-sm text-ink/60">{r.date}</span>
              </div>
              <div className="mt-2 flex items-center gap-3">
                {r.amount && (
                  <span className="inline-flex items-center gap-1 font-display text-xl font-extrabold text-bluebrand">
                    <DollarSign size={16} />
                    {r.amount.replace("$", "")}
                  </span>
                )}
                {r.valuation && <span className="text-sm text-ink/60">@ {r.valuation} val</span>}
              </div>
              {r.signal && <p className="mt-2 text-sm text-ink/70">{r.signal}</p>}
            </div>
          ))}
        </div>
      )}

      {data.pricing_note && (
        <p className="mt-6 rounded-2xl bg-orchid/30 p-4 text-ink/80">{data.pricing_note}</p>
      )}
    </section>
  );
}
