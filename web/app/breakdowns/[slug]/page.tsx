import { notFound } from "next/navigation";
import type { Metadata } from "next";
import { allSlugs, getStory } from "@/lib/content";
import { accentFor } from "@/lib/theme";
import { SITE_URL, breakdownUrl, heroQuestion, buildJsonLd } from "@/lib/seo";
import { JsonLd } from "@/components/JsonLd";
import { PillNav } from "@/components/sections/PillNav";
import { ReadingProgress } from "@/components/sections/ReadingProgress";
import { SectionNav, type NavItem } from "@/components/sections/SectionNav";
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
    const title = `${s.meta.startup_name} · NBT Breakdown`;
    const description = s.hero.subheadline || heroQuestion(s);
    const url = breakdownUrl(slug);
    return {
      metadataBase: new URL(SITE_URL),
      title,
      description,
      alternates: { canonical: url },
      openGraph: {
        type: "article",
        url,
        title,
        description,
        siteName: "NBT Breakdowns",
      },
      twitter: {
        card: "summary_large_image",
        title,
        description,
      },
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

  const eyebrow = story.meta.volume;
  let i = 0; // accent rotation index across rendered sections

  // Build the in-page TOC from sections actually present, in render order.
  const nav: NavItem[] = [];
  if (story.core_insight) nav.push({ id: "insight", label: "Insight" });
  if (story.timeline) nav.push({ id: "timeline", label: "Timeline" });
  if (story.product_loop) nav.push({ id: "loop", label: "The Loop" });
  if (story.funding) nav.push({ id: "funding", label: "Funding" });
  if (story.competitors) nav.push({ id: "competitors", label: "Competitors" });
  if (story.founder_mode) nav.push({ id: "founder", label: "Founder" });
  if (story.lessons.length > 0) nav.push({ id: "lessons", label: "Lessons" });
  if (story.closing) nav.push({ id: "closing", label: "The Take" });

  const anchor = "scroll-mt-28";

  return (
    <main className="min-h-dvh pb-px">
      <JsonLd data={buildJsonLd(story)} />
      <ReadingProgress />
      <PillNav active="Breakdowns" />
      <SectionNav items={nav} darkIds={["lessons"]} />
      <Hero hero={story.hero} eyebrow={eyebrow} />

      {story.core_insight && (
        <div id="insight" className={anchor}>
          <CoreInsight data={story.core_insight} accent={accentFor(i++)} />
        </div>
      )}
      {story.timeline && (
        <div id="timeline" className={anchor}>
          <Timeline data={story.timeline} eyebrow="The founder's journey" />
        </div>
      )}
      {story.product_loop && (
        <div id="loop" className={anchor}>
          <ProductLoop data={story.product_loop} />
        </div>
      )}
      {story.funding && (
        <div id="funding" className={anchor}>
          <Funding data={story.funding} eyebrow="Funding & growth" />
        </div>
      )}
      {story.competitors && (
        <div id="competitors" className={anchor}>
          <Competitors data={story.competitors} eyebrow="The competitive map" />
        </div>
      )}
      {story.founder_mode && (
        <div id="founder" className={anchor}>
          <FounderMode data={story.founder_mode} eyebrow="Founder mode" />
        </div>
      )}
      {story.lessons.length > 0 && (
        <div id="lessons" className={anchor}>
          <Lessons lessons={story.lessons} eyebrow="Lessons for builders" />
        </div>
      )}
      {story.closing && (
        <div id="closing" className={anchor}>
          <Closing data={story.closing} accent={accentFor(i++)} />
        </div>
      )}

      <Footer sources={story.sources} />
    </main>
  );
}
