import { ArrowUpRight, GraduationCap } from "lucide-react";
import type { LessonCard } from "@/lib/types";
import { Eyebrow } from "@/components/ui/Eyebrow";

export function Lessons({ lessons, eyebrow }: { lessons: LessonCard[]; eyebrow: string }) {
  return (
    <section className="bg-[#1a1426] py-24 text-white">
      <div className="mx-auto max-w-3xl px-6 text-center">
        <Eyebrow icon={GraduationCap}>{eyebrow}</Eyebrow>
        <h2 className="mt-3 font-display text-3xl font-extrabold sm:text-5xl">
          What ambitious founders should steal from this playbook.
        </h2>
      </div>

      <div className="mx-auto mt-12 flex max-w-3xl flex-col gap-5 px-6">
        {lessons.map((l) => (
          <div key={l.number} className="rounded-3xl border border-white/10 bg-white/[0.03] p-7">
            <p className="text-sm font-bold uppercase tracking-widest text-orange">
              Lesson {String(l.number).padStart(2, "0")}
            </p>
            <h3 className="mt-3 font-display text-xl font-bold">{l.headline}</h3>
            {l.body && <p className="mt-3 text-white/70">{l.body}</p>}
            {l.applicable_to && (
              <span className="mt-5 inline-flex items-center gap-2 rounded-pill border border-white/20 px-4 py-2 text-xs font-semibold uppercase tracking-wide text-white/70">
                <ArrowUpRight size={14} aria-hidden /> {l.applicable_to}
              </span>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}
