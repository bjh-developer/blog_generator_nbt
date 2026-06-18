import { Users } from "lucide-react";
import type { FounderMode as FounderModeT } from "@/lib/types";

export function FounderMode({ data, eyebrow }: { data: FounderModeT; eyebrow: string }) {
  return (
    <section className="mx-auto max-w-3xl px-6 py-20">
      <p className="inline-flex items-center gap-2 text-sm font-bold uppercase tracking-widest text-orange">
        <Users size={16} /> {eyebrow}
      </p>
      <h2 className="mt-3 font-display text-3xl font-extrabold sm:text-5xl">{data.title}</h2>
      {data.narrative && <p className="mt-4 text-lg text-ink/75">{data.narrative}</p>}

      {data.facts.length > 0 && (
        <div className="mt-8 grid gap-3 sm:grid-cols-3">
          {data.facts.map((f, i) => (
            <div key={i} className="rounded-2xl border border-ink/10 bg-white p-4 text-center">
              <p className="font-display text-2xl font-extrabold text-purple">{f.value}</p>
              <p className="mt-1 text-xs font-semibold uppercase tracking-wide text-ink/60">
                {f.label}
              </p>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
