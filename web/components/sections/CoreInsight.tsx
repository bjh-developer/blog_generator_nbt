import { Lightbulb } from "lucide-react";
import type { CoreInsight as CoreInsightT } from "@/lib/types";
import { Eyebrow } from "@/components/ui/Eyebrow";

export function CoreInsight({ data, accent }: { data: CoreInsightT; accent: string }) {
  return (
    <section className="mx-auto max-w-3xl px-6 py-20">
      <div className="rounded-3xl p-8 sm:p-12" style={{ background: `${accent}22` }}>
        <Eyebrow icon={Lightbulb} color={accent}>{data.title}</Eyebrow>
        <h2 className="mt-4 font-display text-2xl font-bold leading-snug sm:text-3xl">
          {data.statement}
        </h2>
        {data.narrative && <p className="mt-5 text-lg text-ink/75">{data.narrative}</p>}
      </div>
    </section>
  );
}
