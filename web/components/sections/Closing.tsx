import { Quote, Sparkles } from "lucide-react";
import type { Closing as ClosingT } from "@/lib/types";

export function Closing({ data, accent }: { data: ClosingT; accent: string }) {
  return (
    <section className="mx-auto max-w-3xl px-6 py-24">
      <h2
        className="inline-flex items-center gap-2 text-sm font-bold uppercase tracking-widest"
        style={{ color: accent }}
      >
        <Sparkles size={15} aria-hidden className="shrink-0" /> {data.title}
      </h2>
      {data.pull_quote && (
        <blockquote className="mt-6 flex gap-4">
          <Quote size={36} style={{ color: accent }} className="shrink-0" />
          <p className="font-display text-2xl font-bold leading-snug sm:text-3xl">
            {data.pull_quote}
          </p>
        </blockquote>
      )}
      {data.attribution && (
        <p className="mt-3 pl-12 text-sm font-semibold text-ink/60">— {data.attribution}</p>
      )}
      {data.narrative && <p className="mt-8 text-lg text-ink/75">{data.narrative}</p>}
    </section>
  );
}
