import type { TimelineSection } from "@/lib/types";
import { kindColor, kindLabel } from "@/lib/theme";
import { Badge } from "@/components/ui/badge";

export function Timeline({ data, eyebrow }: { data: TimelineSection; eyebrow: string }) {
  return (
    <section className="mx-auto max-w-3xl px-6 py-20">
      <p className="text-sm font-bold uppercase tracking-widest text-orange">✦ {eyebrow}</p>
      <h2 className="mt-3 font-display text-3xl font-extrabold sm:text-5xl">{data.title}</h2>

      <div className="relative mt-12 border-l-2 border-lilac pl-8">
        {data.events.map((e, i) => (
          <div key={i} className="relative mb-12 last:mb-0">
            <span
              className="absolute -left-[41px] top-1 h-4 w-4 rounded-full border-2 border-white"
              style={{ background: kindColor[e.kind] }}
            />
            <div className="mb-2 flex items-center gap-3">
              <span className="font-display font-bold text-orange">{e.year}</span>
              <Badge style={{ background: `${kindColor[e.kind]}22`, color: kindColor[e.kind] }}>
                {kindLabel[e.kind]}
              </Badge>
            </div>
            <h3 className="font-display text-xl font-bold">{e.heading}</h3>
            {e.body && <p className="mt-2 text-ink/70">{e.body}</p>}
          </div>
        ))}
      </div>
    </section>
  );
}
