import Link from "next/link";
import { ArrowUpRight } from "lucide-react";
import { allStories } from "@/lib/content";
import { PillNav } from "@/components/sections/PillNav";

export const metadata = { title: "Startup Breakdowns · NBT" };

export default function BreakdownsIndex() {
  const stories = allStories();
  return (
    <main className="min-h-dvh">
      <PillNav active="Breakdowns" />
      <div className="mx-auto max-w-4xl px-6 py-16">
        <p className="text-sm font-bold uppercase tracking-widest text-orange">✦ The breakdowns</p>
        <h1 className="mt-3 font-display text-4xl font-extrabold sm:text-6xl">
          Startup stories, decoded for builders.
        </h1>

        {stories.length === 0 ? (
          <p className="mt-10 text-ink/60">
            No breakdowns yet. Run the pipeline: <code>POST /generate</code>.
          </p>
        ) : (
          <div className="mt-12 grid gap-5 sm:grid-cols-2">
            {stories.map((s) => (
              <Link
                key={s.meta.slug}
                href={`/breakdowns/${s.meta.slug}`}
                className="group rounded-3xl border border-ink/10 bg-white p-6 shadow-sm transition-all hover:-translate-y-1 hover:shadow-md"
              >
                <p className="text-xs font-bold uppercase tracking-widest text-purple">
                  {s.meta.volume} · {s.meta.category_tag}
                </p>
                <h2 className="mt-3 font-display text-2xl font-extrabold">{s.meta.startup_name}</h2>
                <p className="mt-2 line-clamp-3 text-ink/70">{s.hero.subheadline}</p>
                <span className="mt-4 inline-flex items-center gap-1 text-sm font-semibold text-orange">
                  Read breakdown <ArrowUpRight size={15} className="transition-transform group-hover:translate-x-0.5" />
                </span>
              </Link>
            ))}
          </div>
        )}
      </div>
    </main>
  );
}
