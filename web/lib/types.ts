// Mirror of backend/app/schemas.py StoryBrief. Keep field names + optionality in sync.

export type TimelineKind =
  | "founder_story" | "product" | "funding" | "inflection" | "user_delight";

export interface SourceRef { title?: string | null; outlet?: string | null; url?: string | null; }

export interface StoryMeta {
  startup_name: string; slug: string; volume: string;
  category_tag: string; research_date: string;
}
export interface StatItem { value: string; label: string; }
export interface Hero {
  line1: string; line2: string;
  accent_word_orange?: string | null; accent_word_purple?: string | null;
  subheadline: string; stat_bar: StatItem[];
}
export interface CoreInsight { title: string; statement: string; narrative: string; icon: string; }
export interface TimelineItem { year: string; kind: TimelineKind; heading: string; body: string; }
export interface TimelineSection { title: string; events: TimelineItem[]; }
export interface LoopNode { label: string; sub: string; }
export interface ProductLoop { title: string; nodes: LoopNode[]; center_label: string; caption: string; }
export interface FundingPoint { label: string; value: number; unit?: string | null; date?: string | null; }
export interface FundingRoundView { label: string; date: string; amount?: string | null; valuation?: string | null; signal: string; }
export interface FundingSection {
  title: string; narrative: string; rounds: FundingRoundView[];
  chart: FundingPoint[]; pricing_note?: string | null;
}
export interface QuadrantItem {
  name: string; their_bet: string; the_gap: string;
  quadrant: "tr" | "tl" | "br" | "bl"; winner: boolean;
}
export interface CompetitorSection {
  title: string; framing: string; axis_x: string; axis_y: string; quadrants: QuadrantItem[];
}
export interface FounderModeFact { label: string; value: string; }
export interface FounderMode { title: string; narrative: string; facts: FounderModeFact[]; }
export interface LessonCard { number: number; headline: string; body: string; applicable_to: string; }
export interface Closing { title: string; narrative: string; pull_quote?: string | null; attribution?: string | null; }

export interface StoryBrief {
  meta: StoryMeta;
  hero: Hero;
  core_insight?: CoreInsight | null;
  timeline?: TimelineSection | null;
  product_loop?: ProductLoop | null;
  funding?: FundingSection | null;
  competitors?: CompetitorSection | null;
  founder_mode?: FounderMode | null;
  lessons: LessonCard[];
  closing?: Closing | null;
  sources: SourceRef[];
  overall_confidence: number;
}
