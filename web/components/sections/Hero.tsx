"use client";

import { useEffect, useRef, useState } from "react";
import { Sparkles } from "lucide-react";
import type { Hero as HeroT } from "@/lib/types";
import { palette } from "@/lib/theme";

// highlight accent words inside a headline line
function accentize(line: string, orange?: string | null, purple?: string | null) {
  const parts: { text: string; color?: string }[] = [{ text: line }];
  const apply = (word: string | null | undefined, color: string) => {
    if (!word) return;
    for (let i = 0; i < parts.length; i++) {
      const idx = parts[i].text.indexOf(word);
      if (parts[i].color === undefined && idx !== -1) {
        const before = parts[i].text.slice(0, idx);
        const after = parts[i].text.slice(idx + word.length);
        parts.splice(i, 1, { text: before }, { text: word, color }, { text: after });
        break;
      }
    }
  };
  apply(orange, palette.orange);
  apply(purple, palette.purple);
  return parts;
}

function StatCard({ value, label }: { value: string; label: string }) {
  return (
    <div className="flex flex-col items-center border-r border-ink/10 px-4 py-3 last:border-r-0">
      <span className="font-display text-2xl font-extrabold sm:text-3xl">{value}</span>
      <span className="mt-1 text-center text-[11px] font-semibold uppercase tracking-wide text-ink/60">
        {label}
      </span>
    </div>
  );
}

export function Hero({ hero, eyebrow }: { hero: HeroT; eyebrow: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [shown, setShown] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(
      ([e]) => e.isIntersecting && (setShown(true), io.disconnect()),
      { threshold: 0.3 },
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);

  return (
    <header ref={ref} className="mx-auto max-w-4xl px-6 pt-16 text-center">
      <div className="inline-flex items-center gap-2 rounded-pill bg-white px-4 py-1.5 text-xs font-bold uppercase tracking-widest text-purple shadow-sm">
        <Sparkles size={14} className="text-orange" /> {eyebrow}
      </div>

      <h1 className="mt-8 font-display text-4xl font-extrabold leading-[1.05] sm:text-6xl">
        <span className="block">{hero.line1}</span>
        <span className="block">
          {accentize(hero.line2, hero.accent_word_orange, hero.accent_word_purple).map((p, i) => (
            <span key={i} style={p.color ? { color: p.color } : undefined}>
              {p.text}
            </span>
          ))}
        </span>
      </h1>

      {hero.subheadline && (
        <p className="mx-auto mt-6 max-w-2xl text-lg text-ink/70">{hero.subheadline}</p>
      )}

      {hero.stat_bar.length > 0 && (
        <div
          className={`mx-auto mt-10 flex max-w-2xl flex-wrap justify-center rounded-2xl border border-ink/10 bg-white shadow-sm transition-all duration-700 ${
            shown ? "translate-y-0 opacity-100" : "translate-y-3 opacity-0"
          }`}
        >
          {hero.stat_bar.map((s) => (
            <StatCard key={s.label} value={s.value} label={s.label} />
          ))}
        </div>
      )}
    </header>
  );
}
