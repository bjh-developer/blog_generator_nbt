import { Map as MapIcon } from "lucide-react";
import type { CompetitorSection, QuadrantItem } from "@/lib/types";
import { palette } from "@/lib/theme";
import { Eyebrow } from "@/components/ui/Eyebrow";

const SLOTS: Record<string, string> = { tl: "tl", tr: "tr", bl: "bl", br: "br" };

function Cell({ items }: { items: QuadrantItem[] }) {
  return (
    <div className="flex flex-col gap-2">
      {items.map((q, i) => (
        <div
          key={i}
          className={`rounded-xl border p-3 ${
            q.winner ? "border-orange bg-orange/10" : "border-ink/10 bg-white"
          }`}
        >
          <p className="font-display font-bold" style={q.winner ? { color: palette.orange } : undefined}>
            {q.name}
          </p>
          {q.their_bet && <p className="mt-1 text-xs text-ink/70">{q.their_bet}</p>}
          {q.the_gap && <p className="mt-1 text-xs text-ink/50">↳ {q.the_gap}</p>}
        </div>
      ))}
    </div>
  );
}

export function Competitors({ data, eyebrow }: { data: CompetitorSection; eyebrow: string }) {
  const by = (slot: string) => data.quadrants.filter((q) => SLOTS[q.quadrant] === slot);
  return (
    <section className="mx-auto max-w-3xl px-6 py-20">
      <Eyebrow icon={MapIcon}>{eyebrow}</Eyebrow>
      <h2 className="mt-3 font-display text-3xl font-extrabold sm:text-5xl">{data.title}</h2>
      {data.framing && <p className="mt-4 text-lg text-ink/75">{data.framing}</p>}

      <div className="mt-10 flex gap-3 pt-8 pb-6 px-2">
        {data.axis_y && (
          <div className="flex w-6 items-center justify-center">
            <span className="-rotate-90 whitespace-nowrap text-xs font-bold uppercase tracking-widest text-ink/50">
              {data.axis_y} →
            </span>
          </div>
        )}
        <div className="flex-1">
          <div className="grid grid-cols-2 gap-3">
            <Cell items={by("tl")} />
            <Cell items={by("tr")} />
            <Cell items={by("bl")} />
            <Cell items={by("br")} />
          </div>
          {data.axis_x && (
            <p className="mt-3 text-center text-xs font-bold uppercase tracking-widest text-ink/50">
              {data.axis_x} →
            </p>
          )}
        </div>
      </div>
    </section>
  );
}
