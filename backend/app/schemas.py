"""Data contracts.

ResearchDoc = internal, source-attributed research (ResearchAgent output).
StoryBrief  = editorial output that drives the Next.js UI (EditorialAgent output).
Keep StoryBrief in sync with web/lib/types.ts.
"""
from __future__ import annotations

import re
from typing import List, Literal, Optional, get_args

from pydantic import BaseModel, Field, field_validator

# --- shared ----------------------------------------------------------------

TimelineKind = Literal["founder_story", "product", "funding", "inflection", "user_delight"]

# OSS models emit human money strings ("$3.3 billion", "1.2M", "3.3 billion each")
# for float fields. Parse to a number; unparseable -> None (field is Optional).
_MONEY_MULT = {
    "trillion": 1e12, "t": 1e12,
    "billion": 1e9, "bn": 1e9, "b": 1e9,
    "million": 1e6, "mm": 1e6, "m": 1e6,
    "thousand": 1e3, "k": 1e3,
}


def _parse_money(s: str) -> Optional[float]:
    t = s.strip().lower().replace(",", "").replace("$", "").replace("~", "").replace("≈", "")
    m = re.search(r"-?\d+(?:\.\d+)?", t)
    if not m:
        return None
    num = float(m.group())
    tail = t[m.end():]
    for w in sorted(_MONEY_MULT, key=len, reverse=True):
        if re.match(rf"\s*{w}\b", tail):
            return num * _MONEY_MULT[w]
    return num


def _is_float_field(f) -> bool:
    return f.annotation is float or float in get_args(f.annotation)


class LenientModel(BaseModel):
    """Base that tolerates free-model drift: a `null` sent for a field whose
    default is a str/list is coerced to that default instead of failing."""

    @field_validator("*", mode="before")
    @classmethod
    def _none_to_default(cls, v, info):
        f = cls.model_fields.get(info.field_name)
        if v is None:
            if f is not None and isinstance(f.default, (str, list)):
                return f.default
            return v
        # coerce human money strings on float fields; unparseable -> None
        if isinstance(v, str) and f is not None and _is_float_field(f):
            return _parse_money(v)
        return v


class SourceRef(LenientModel):
    quote: Optional[str] = None
    outlet: Optional[str] = None
    url: Optional[str] = None


# scraped article (SourceAgent output) -------------------------------------
SourceLabel = Literal["success", "cautionary", "reject"]


class Source(LenientModel):
    id: str
    url: str
    title: str
    publisher: Optional[str] = None
    raw_text_ref: str = ""
    label: SourceLabel = "reject"


# --- ResearchDoc (internal) ------------------------------------------------

class TimelineEvent(LenientModel):
    date: str                       # YYYY | YYYY-MM | YYYY-MM-DD
    kind: TimelineKind = "product"
    event: str
    significance: str = ""
    source: SourceRef = Field(default_factory=SourceRef)


class Founder(LenientModel):
    name: str
    role: str = ""
    background: str = ""
    why: Optional[str] = None
    source: SourceRef = Field(default_factory=SourceRef)


class FundingRound(LenientModel):
    round: str
    date: str = ""
    amount_usd: Optional[float] = None
    valuation_usd: Optional[float] = None
    investors: List[str] = Field(default_factory=list)
    source: SourceRef = Field(default_factory=SourceRef)


class Metric(LenientModel):
    label: str
    value: str
    date: Optional[str] = None
    source_url: Optional[str] = None


class Competitor(LenientModel):
    name: str
    positioning: str = ""
    strengths: List[str] = Field(default_factory=list)
    weaknesses: List[str] = Field(default_factory=list)
    our_advantage: Optional[str] = None


class Lesson(LenientModel):
    lesson: str
    context: str = ""
    applicable_to: str = ""
    source: SourceRef = Field(default_factory=SourceRef)


class ResearchDoc(LenientModel):
    startup_name: str
    tagline: Optional[str] = None
    pivotal_insight: Optional[str] = None
    origin_story: Optional[str] = None
    timeline: List[TimelineEvent] = Field(default_factory=list)
    founders: List[Founder] = Field(default_factory=list)
    product_evolution: List[TimelineEvent] = Field(default_factory=list)
    funding: List[FundingRound] = Field(default_factory=list)
    metrics: List[Metric] = Field(default_factory=list)
    competitors: List[Competitor] = Field(default_factory=list)
    product_loop_steps: List[str] = Field(default_factory=list)
    lessons: List[Lesson] = Field(default_factory=list)
    sources: List[SourceRef] = Field(default_factory=list)


# --- StoryBrief (drives UI) ------------------------------------------------

class StoryMeta(LenientModel):
    startup_name: str
    slug: str
    volume: str
    category_tag: str
    research_date: str


class StatItem(LenientModel):
    value: str
    label: str


class Hero(LenientModel):
    line1: str
    line2: str
    accent_word_orange: Optional[str] = None
    accent_word_purple: Optional[str] = None
    subheadline: str = ""
    stat_bar: List[StatItem] = Field(default_factory=list)


class CoreInsight(LenientModel):
    title: str
    statement: str
    narrative: str = ""
    icon: str = "Lightbulb"


class TimelineItem(LenientModel):
    year: str
    kind: TimelineKind = "product"
    heading: str
    body: str = ""


class TimelineSection(LenientModel):
    title: str
    events: List[TimelineItem] = Field(default_factory=list)


class LoopNode(LenientModel):
    label: str
    sub: str = ""


class ProductLoop(LenientModel):
    title: str
    nodes: List[LoopNode] = Field(default_factory=list)   # 4 for the circular diagram
    center_label: str = "NETWORK EFFECT"
    caption: str = ""


class FundingPoint(LenientModel):
    label: str
    value: float
    unit: Optional[str] = None
    date: Optional[str] = None


class FundingRoundView(LenientModel):
    label: str
    date: str = ""
    amount: Optional[str] = None
    valuation: Optional[str] = None
    signal: str = ""


class FundingSection(LenientModel):
    title: str
    narrative: str = ""
    rounds: List[FundingRoundView] = Field(default_factory=list)
    chart: List[FundingPoint] = Field(default_factory=list)
    pricing_note: Optional[str] = None


class QuadrantItem(LenientModel):
    name: str
    their_bet: str = ""
    the_gap: str = ""
    quadrant: Literal["tr", "tl", "br", "bl"] = "tr"
    winner: bool = False


class CompetitorSection(LenientModel):
    title: str
    framing: str = ""
    axis_x: str = ""
    axis_y: str = ""
    quadrants: List[QuadrantItem] = Field(default_factory=list)


class FounderModeFact(LenientModel):
    label: str
    value: str


class FounderMode(LenientModel):
    title: str
    narrative: str = ""
    facts: List[FounderModeFact] = Field(default_factory=list)


class LessonCard(LenientModel):
    number: int
    headline: str
    body: str = ""
    applicable_to: str = ""


class Closing(LenientModel):
    title: str
    narrative: str = ""
    pull_quote: Optional[str] = None
    attribution: Optional[str] = None


class StoryBrief(LenientModel):
    meta: StoryMeta
    hero: Hero
    core_insight: Optional[CoreInsight] = None
    timeline: Optional[TimelineSection] = None
    product_loop: Optional[ProductLoop] = None
    funding: Optional[FundingSection] = None
    competitors: Optional[CompetitorSection] = None
    founder_mode: Optional[FounderMode] = None
    lessons: List[LessonCard] = Field(default_factory=list)
    closing: Optional[Closing] = None
    sources: List[SourceRef] = Field(default_factory=list)
    overall_confidence: float = 0.0


# --- API -------------------------------------------------------------------

class GenerateRequest(LenientModel):
    query: str = Field(..., min_length=2)
    max_sources: int = 8
