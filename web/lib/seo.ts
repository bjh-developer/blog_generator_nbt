import type { StoryBrief } from "./types";

// Base URL for absolute canonical/OG links. Override per environment via
// NEXT_PUBLIC_SITE_URL. Kept route-local (not in the root layout) so the whole
// breakdown route stays portable into the main site without metadata conflicts.
export const SITE_URL = (
  process.env.NEXT_PUBLIC_SITE_URL || "https://nextbigthingsg.com"
).replace(/\/$/, "");

export const breakdownUrl = (slug: string) => `${SITE_URL}/breakdowns/${slug}`;

const clean = (s?: string | null) => (s ?? "").replace(/\s+/g, " ").trim();

export function heroQuestion(story: StoryBrief): string {
  return clean(`${story.hero.line1} ${story.hero.line2}`);
}

// JSON-LD graph: Article (the breakdown) + BreadcrumbList (trail) +
// FAQPage (Q/A pairs answer engines can lift directly).
export function buildJsonLd(story: StoryBrief): object[] {
  const url = breakdownUrl(story.meta.slug);
  const name = clean(story.meta.startup_name);
  const headline = heroQuestion(story) || `${name} · NBT Breakdown`;
  const description = clean(story.hero.subheadline);

  const publisher = {
    "@type": "Organization",
    name: "NBT — NextBigThing",
    url: SITE_URL,
  };

  const article = {
    "@context": "https://schema.org",
    "@type": "Article",
    "@id": `${url}#article`,
    mainEntityOfPage: { "@type": "WebPage", "@id": url },
    headline: headline.slice(0, 110), // schema.org headline guidance
    description,
    about: { "@type": "Organization", name },
    inLanguage: "en",
    isAccessibleForFree: true,
    author: publisher,
    publisher,
    ...(story.meta.research_date ? { datePublished: story.meta.research_date } : {}),
  };

  const breadcrumb = {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: [
      { "@type": "ListItem", position: 1, name: "Breakdowns", item: `${SITE_URL}/breakdowns` },
      { "@type": "ListItem", position: 2, name, item: url },
    ],
  };

  // FAQ: lead with the hero question, then each lesson as a Q/A pair.
  const faqEntries: { q: string; a: string }[] = [];
  const heroAnswer = clean(
    story.core_insight
      ? `${story.core_insight.statement} ${story.core_insight.narrative}`
      : story.hero.subheadline,
  );
  if (heroQuestion(story) && heroAnswer) {
    faqEntries.push({ q: heroQuestion(story), a: heroAnswer });
  }
  for (const l of story.lessons) {
    const q = clean(l.headline);
    const a = clean(l.body);
    if (q && a) faqEntries.push({ q, a });
  }

  const faq =
    faqEntries.length > 0
      ? {
          "@context": "https://schema.org",
          "@type": "FAQPage",
          mainEntity: faqEntries.map((e) => ({
            "@type": "Question",
            name: e.q,
            acceptedAnswer: { "@type": "Answer", text: e.a },
          })),
        }
      : null;

  return [article, breadcrumb, ...(faq ? [faq] : [])];
}
