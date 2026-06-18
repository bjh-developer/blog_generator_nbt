import { Lightbulb } from "lucide-react";
import type { CoreInsight as CoreInsightT } from "@/lib/types";

export function CoreInsight({ data, accent }: { data: CoreInsightT; accent: string }) {
  return (
    <section className="mx-auto max-w-3xl px-6 py-20">
      <div className="rounded-3xl p-8 sm:p-12" style={{ background: `${accent}22` }}>
        <div
          className="inline-flex items-center gap-2 text-sm font-bold uppercase tracking-widest"
          style={{ color: accent }}
        >
          <Lightbulb size={16} /> {data.title}
        </div>
        <p className="mt-4 font-display text-2xl font-bold leading-snug sm:text-3xl">
          {data.statement}
        </p>
        {data.narrative && <p className="mt-5 text-lg text-ink/75">{data.narrative}</p>}
      </div>
    </section>
  );
}
