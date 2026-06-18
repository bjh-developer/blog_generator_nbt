import { notFound } from "next/navigation";
import type { Metadata } from "next";
import { allSlugs, getStory } from "@/lib/content";
import { accentFor } from "@/lib/theme";
import { PillNav } from "@/components/sections/PillNav";
import { Hero } from "@/components/sections/Hero";
import { CoreInsight } from "@/components/sections/CoreInsight";
import { Timeline } from "@/components/sections/Timeline";
import { ProductLoop } from "@/components/sections/ProductLoop";
import { Funding } from "@/components/sections/Funding";
import { Competitors } from "@/components/sections/Competitors";
import { FounderMode } from "@/components/sections/FounderMode";
import { Lessons } from "@/components/sections/Lessons";
import { Closing } from "@/components/sections/Closing";
import { Footer } from "@/components/sections/Footer";

export function generateStaticParams() {
  return allSlugs().map((slug) => ({ slug }));
}

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  try {
    const { slug } = await params;
    const s = getStory(slug);
    return {
      title: `${s.meta.startup_name} · NBT Breakdown`,
      description: s.hero.subheadline,
    };
  } catch {
    return { title: "Breakdown not found" };
  }
}

export default async function BreakdownPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  let story;
  try {
    story = getStory(slug);
  } catch {
    notFound();
  }

  const eyebrow = `${story.meta.volume} · ${story.meta.category_tag}`;
  let i = 0; // accent rotation index across rendered sections

  return (
    <main className="min-h-dvh pb-px">
      <PillNav active="Breakdowns" />
      <Hero hero={story.hero} eyebrow={eyebrow} />

      {story.core_insight && <CoreInsight data={story.core_insight} accent={accentFor(i++)} />}
      {story.timeline && <Timeline data={story.timeline} eyebrow="The founder's journey" />}
      {story.product_loop && <ProductLoop data={story.product_loop} />}
      {story.funding && <Funding data={story.funding} eyebrow="Funding & growth" />}
      {story.competitors && <Competitors data={story.competitors} eyebrow="The competitive map" />}
      {story.founder_mode && <FounderMode data={story.founder_mode} eyebrow="Founder mode" />}
      {story.lessons.length > 0 && <Lessons lessons={story.lessons} eyebrow="Lessons for builders" />}
      {story.closing && <Closing data={story.closing} accent={accentFor(i++)} />}

      <Footer sources={story.sources} confidence={story.overall_confidence} />
    </main>
  );
}
