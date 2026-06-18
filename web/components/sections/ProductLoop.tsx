import type { ProductLoop as ProductLoopT } from "@/lib/types";
import { palette } from "@/lib/theme";

// 4 nodes at 12/3/6/9 o'clock with dashed connecting arcs + center label.
const POS = [
  { x: 350, y: 70 },   // top
  { x: 600, y: 250 },  // right
  { x: 350, y: 430 },  // bottom
  { x: 100, y: 250 },  // left
];
const ARC_COLORS = [palette.peach, palette.orange, palette.blue, palette.purple];

export function ProductLoop({ data }: { data: ProductLoopT }) {
  const nodes = data.nodes.slice(0, 4);
  return (
    <section className="mx-auto max-w-4xl px-6 py-20 text-center">
      <p className="text-sm font-bold uppercase tracking-widest text-orange">✦ {data.title}</p>

      <div className="relative mt-10">
        <svg viewBox="0 0 700 500" className="mx-auto w-full max-w-2xl">
          {nodes.map((_, i) => {
            const a = POS[i];
            const b = POS[(i + 1) % nodes.length];
            const mx = (a.x + b.x) / 2 + (b.y - a.y) * 0.25;
            const my = (a.y + b.y) / 2 - (b.x - a.x) * 0.25;
            return (
              <path
                key={i}
                d={`M ${a.x} ${a.y} Q ${mx} ${my} ${b.x} ${b.y}`}
                fill="none"
                stroke={ARC_COLORS[i % 4]}
                strokeWidth={2.5}
                strokeDasharray="7 7"
                markerEnd="url(#arrow)"
              />
            );
          })}
          <defs>
            <marker id="arrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
              <path d="M0,0 L6,3 L0,6 Z" fill={palette.ink} />
            </marker>
          </defs>
          <circle cx="350" cy="250" r="62" fill={`${palette.orange}33`} stroke={palette.lilac} />
          <text x="350" y="245" textAnchor="middle" className="fill-orange text-[13px] font-bold">
            {data.center_label.split(" ")[0]}
          </text>
          <text x="350" y="262" textAnchor="middle" className="fill-orange text-[13px] font-bold">
            {data.center_label.split(" ").slice(1).join(" ")}
          </text>
        </svg>

        <div className="pointer-events-none absolute inset-0">
          {nodes.map((n, i) => (
            <div
              key={i}
              className="absolute w-40 -translate-x-1/2 -translate-y-1/2 rounded-2xl border border-lilac bg-white px-3 py-2 shadow-sm"
              style={{ left: `${(POS[i].x / 700) * 100}%`, top: `${(POS[i].y / 500) * 100}%` }}
            >
              <p className="font-display text-sm font-bold leading-tight">{n.label}</p>
              {n.sub && <p className="mt-0.5 text-[11px] text-ink/60">{n.sub}</p>}
            </div>
          ))}
        </div>
      </div>

      {data.caption && <p className="mx-auto mt-8 max-w-2xl text-ink/70">{data.caption}</p>}
    </section>
  );
}
