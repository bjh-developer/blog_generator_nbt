"use client";

import { useEffect, useState } from "react";

export interface NavItem {
  id: string;
  label: string;
}

// Desktop-only floating table of contents with scroll-spy. Hidden under lg so
// it never competes with content on narrow viewports. Smooth-scrolls to anchors
// (respecting reduced-motion) and reflects the active section.
export function SectionNav({
  items,
  darkIds = [],
}: {
  items: NavItem[];
  darkIds?: string[];
}) {
  const [active, setActive] = useState(items[0]?.id ?? "");
  const onDark = darkIds.includes(active);

  useEffect(() => {
    if (items.length === 0) return;
    const els = items
      .map((it) => document.getElementById(it.id))
      .filter((el): el is HTMLElement => el !== null);

    const io = new IntersectionObserver(
      (entries) => {
        // pick the entry nearest the top that is intersecting
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible[0]) setActive(visible[0].target.id);
      },
      { rootMargin: "-30% 0px -60% 0px", threshold: 0 },
    );
    els.forEach((el) => io.observe(el));
    return () => io.disconnect();
  }, [items]);

  if (items.length < 2) return null;

  const go = (id: string) => {
    const el = document.getElementById(id);
    if (!el) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    el.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
  };

  return (
    <nav
      aria-label="Sections"
      className="fixed left-6 top-1/2 z-40 hidden -translate-y-1/2 xl:block 2xl:left-10"
    >
      <ul className="flex flex-col gap-1">
        {items.map((it) => {
          const on = it.id === active;
          return (
            <li key={it.id}>
              <button
                onClick={() => go(it.id)}
                aria-current={on ? "true" : undefined}
                className="group flex items-center gap-3 py-1.5 text-left"
              >
                <span
                  className={`h-px transition-all duration-300 ${
                    on
                      ? "w-8 bg-orange"
                      : onDark
                        ? "w-4 bg-white/30 group-hover:w-6 group-hover:bg-white/60"
                        : "w-4 bg-ink/25 group-hover:w-6 group-hover:bg-ink/50"
                  }`}
                />
                <span
                  className={`text-xs font-bold uppercase tracking-widest transition-colors ${
                    on
                      ? onDark
                        ? "text-white"
                        : "text-ink"
                      : onDark
                        ? "text-white/45 group-hover:text-white/80"
                        : "text-ink/40 group-hover:text-ink/70"
                  }`}
                >
                  {it.label}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
