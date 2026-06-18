import { Quote } from "lucide-react";
import type { Closing as ClosingT } from "@/lib/types";

export function Closing({ data, accent }: { data: ClosingT; accent: string }) {
  return (
    <section className="mx-auto max-w-3xl px-6 py-24">
      <p className="text-sm font-bold uppercase tracking-widest" style={{ color: accent }}>
        ✦ {data.title}
      </p>
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
