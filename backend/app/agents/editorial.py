"""EditorialAgent: ResearchDoc -> StoryBrief (the UI contract).

Deterministic assembly (pure, tested) for data-shaped sections; one constrained
LLM call writes the NBT-voice prose. Sections with no support are left None so
the frontend omits them. Stats come only from grounded metrics/funding.
"""
from __future__ import annotations

import logging
import re
from datetime import date
from typing import List, Optional

from pydantic import Field, model_validator

from app import store
from app.agents import verify
from app.llm import gateway
from app.schemas import (
    Closing, CompetitorSection, CoreInsight, FounderMode, FounderModeFact,
    FundingPoint, FundingRoundView, FundingSection, Hero, LenientModel, LessonCard,
    LoopNode, ProductLoop, QuadrantItem, ResearchDoc, Source, StatItem, StoryBrief,
    StoryMeta, TimelineItem, TimelineSection,
)

log = logging.getLogger("app.agents.editorial")


# --- pure helpers ----------------------------------------------------------

def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def funding_chart(rd: ResearchDoc) -> List[FundingPoint]:
    pts: List[FundingPoint] = []
    for f in rd.funding:
        if f.amount_usd:
            pts.append(FundingPoint(label=f.round, value=round(f.amount_usd / 1e6, 2),
                                    unit="$M", date=f.date or None))
    pts.sort(key=lambda p: p.date or "")
    return pts


# quantifier words -> symbol, applied to the front of a stat value
_QUANT = [
    ("more than ", ">"), ("over ", ">"), ("greater than ", ">"), ("at least ", ">"),
    ("less than ", "<"), ("under ", "<"), ("fewer than ", "<"), ("up to ", "<"),
    ("approximately ", "~"), ("approx ", "~"), ("nearly ", "~"), ("almost ", "~"),
    ("around ", "~"), ("about ", "~"),
]
# verbose magnitude words -> compact suffix (first match wins; space forms first)
_UNIT = [(" billion", "B"), (" million", "M"), (" thousand", "K"),
         ("bn", "B"), ("mn", "M")]
_STAT_MAX_LEN = 12
# a real stat leads with a number (after an optional ~ < > and/or $)
_STAT_NUM = re.compile(r"^[~<>≈]?\s*\$?\s*\d")


def _compress_units(v: str) -> str:
    low = v.lower()
    for word, sym in _UNIT:
        idx = low.find(word)
        # only compress a magnitude word attached to a number, so "half a
        # million" doesn't collapse into "half aM"
        if idx > 0 and v[idx - 1].isdigit():
            return v[:idx] + sym + v[idx + len(word):]
    return v


def normalize_stat_value(value: str) -> str:
    v = value.strip()
    low = v.lower()
    for word, sym in _QUANT:
        if low.startswith(word):
            v = sym + v[len(word):].lstrip()
            break
    return _compress_units(v)


def stat_bar(rd: ResearchDoc) -> List[StatItem]:
    out: List[StatItem] = []
    for m in rd.metrics:
        val = normalize_stat_value(m.value)
        if len(val) > _STAT_MAX_LEN:
            continue                       # drop prose-like stats (e.g. "Top 2 Free...")
        if not _STAT_NUM.match(val):
            continue                       # drop non-quantitative junk (e.g. "half aM")
        out.append(StatItem(value=val, label=m.label))
        if len(out) >= 4:
            break
    return out


# which moments define the success/failure storyline (lower = more important)
_TIMELINE_PRIORITY = {
    "inflection": 0,        # pivots, near-deaths, breakthroughs
    "founder_story": 1,     # origin, the bet
    "funding": 2,           # money milestones
    "product": 3,           # routine shipping
    "user_delight": 4,
}
_TIMELINE_MAX = 6


def timeline_items(rd: ResearchDoc, max_items: int = _TIMELINE_MAX) -> List[TimelineItem]:
    # Deterministic fallback when the LLM emits no timeline_events: dedupe, keep
    # the most storyline-defining kinds up to a cap, then order chronologically.
    seen: set = set()
    uniq: list = []
    for e in rd.timeline + rd.product_evolution:
        year = (e.date or "")[:4]
        key = (year, e.event.strip().lower()[:60])
        if key in seen:
            continue
        seen.add(key)
        uniq.append((e, year))
    uniq.sort(key=lambda ey: _TIMELINE_PRIORITY.get(ey[0].kind, 5))
    top = uniq[:max_items]
    top.sort(key=lambda ey: ey[1] or "")
    return [TimelineItem(year=y, kind=e.kind, heading=e.event, body=e.significance)
            for e, y in top]


def _fmt_usd(v: float) -> str:
    """$1.5M / $85M / $1B / $3.2B — roll into billions at >= $1B."""
    return f"${v/1e9:g}B" if v >= 1e9 else f"${v/1e6:g}M"


def funding_rounds(rd: ResearchDoc) -> List[FundingRoundView]:
    out: List[FundingRoundView] = []
    for f in rd.funding:
        out.append(FundingRoundView(
            label=f.round, date=f.date,
            amount=(_fmt_usd(f.amount_usd) if f.amount_usd else None),
            valuation=(_fmt_usd(f.valuation_usd) if f.valuation_usd else None),
        ))
    return out


# labels signalling the round was guessed/inferred, not grounded — drop them
_FUNDING_JUNK = ("unspecified", "multiple rounds", "implied", "estimated",
                 "approx", "unconfirmed", "rumored", "rumoured", "tbd")


def clean_funding(funding: list) -> list:
    """Turn the research merge's noisy funding list into clean, chartable rounds.

    1. drop junk-label rounds (empty / 'unspecified' / 'multiple rounds')
    2. dedupe by (label sans trailing '(YYYY)', year), backfilling amount/val/investors
    3. drop rounds with no amount (can't be charted, clutter the list)
    4. sort chronologically
    """
    kept = []
    for f in funding:
        lbl = (f.round or "").strip()
        if not lbl:
            continue
        if any(j in lbl.lower() for j in _FUNDING_JUNK):
            continue
        kept.append(f)

    by_key: dict = {}
    order: list = []
    for f in kept:
        base = re.sub(r"\s*\(\d{4}\)$", "", f.round).strip().lower()
        key = (base, (f.date or "")[:4])
        if key not in by_key:
            by_key[key] = f
            order.append(key)
        else:
            k = by_key[key]
            if not k.amount_usd and f.amount_usd:
                k.amount_usd = f.amount_usd
            if not k.valuation_usd and f.valuation_usd:
                k.valuation_usd = f.valuation_usd
            if not k.investors and f.investors:
                k.investors = f.investors
    deduped = [by_key[k] for k in order]

    deduped = [f for f in deduped if f.amount_usd]
    deduped.sort(key=lambda f: f.date or "")
    return deduped


# --- LLM narrative contract ------------------------------------------------

class _TimelineN(LenientModel):
    year: str = ""
    kind: str = "product"
    heading: str
    body: str = ""


class _Quadrant(LenientModel):
    name: str
    their_bet: str = ""
    the_gap: str = ""
    quadrant: str = "tl"
    winner: bool = False


class _LessonN(LenientModel):
    headline: str
    body: str = ""
    applicable_to: str = ""


class _Narratives(LenientModel):
    @model_validator(mode="before")
    @classmethod
    def _flatten(cls, data):
        """Free models often nest fields under hero/competitor objects and emit
        quadrants as a name->item map. Flatten that back to our flat schema."""
        if not isinstance(data, dict):
            return data
        d = dict(data)
        hero = d.pop("hero", None)
        if isinstance(hero, dict):
            d.setdefault("hero_line1", hero.get("line1"))
            d.setdefault("hero_line2", hero.get("line2"))
            d.setdefault("accent_word_orange", hero.get("accent_word_orange"))
            d.setdefault("accent_word_purple", hero.get("accent_word_purple"))
            d.setdefault("subheadline", hero.get("subheadline"))
        comp = d.pop("competitor", None) or d.pop("competitors", None)
        if isinstance(comp, dict):
            for k in ("axis_x", "axis_y", "framing", "title", "quadrants"):
                if k in comp and k not in d:
                    d[k if k != "title" else "competitor_title"] = comp[k]
        # quadrants emitted as {name: {...}} -> list of items
        q = d.get("quadrants")
        if isinstance(q, dict):
            items = []
            for name, v in q.items():
                if isinstance(v, dict):
                    items.append({"name": v.get("name", name), **{kk: vv for kk, vv in v.items() if kk != "name"}})
            d["quadrants"] = items
        # drop malformed list entries (junk like {"{": ","}) so one bad item
        # doesn't fail the whole parse
        # keep already-valid (non-dict) items; drop only malformed dicts
        if isinstance(d.get("quadrants"), list):
            d["quadrants"] = [x for x in d["quadrants"]
                              if not isinstance(x, dict) or x.get("name")]
        if isinstance(d.get("lessons"), list):
            d["lessons"] = [x for x in d["lessons"]
                            if not isinstance(x, dict) or x.get("headline")]
        if isinstance(d.get("loop_nodes"), list):
            d["loop_nodes"] = [x for x in d["loop_nodes"]
                               if not isinstance(x, str) or x.strip()]
        if isinstance(d.get("timeline_events"), list):
            d["timeline_events"] = [x for x in d["timeline_events"]
                                    if not isinstance(x, dict) or x.get("heading")]
        return d

    volume: str = "Vol. 01"
    category_tag: str = "Startup Breakdown"
    hero_line1: str
    hero_line2: str
    accent_word_orange: Optional[str] = None
    accent_word_purple: Optional[str] = None
    subheadline: str = ""
    core_insight_title: Optional[str] = None
    core_insight_statement: Optional[str] = None
    core_insight_narrative: str = ""
    timeline_title: str = "The founder's journey"
    timeline_events: List[_TimelineN] = Field(default_factory=list)
    loop_title: Optional[str] = None
    loop_nodes: List[str] = Field(default_factory=list)
    loop_center: str = "NETWORK EFFECT"
    loop_caption: str = ""
    funding_title: str = "Funding & growth"
    funding_narrative: str = ""
    pricing_note: Optional[str] = None
    competitor_title: Optional[str] = None
    competitor_framing: str = ""
    axis_x: str = ""
    axis_y: str = ""
    quadrants: List[_Quadrant] = Field(default_factory=list)
    founder_mode_title: Optional[str] = None
    founder_mode_narrative: str = ""
    lessons: List[_LessonN] = Field(default_factory=list)
    closing_title: str = "The NBT take"
    closing_narrative: str = ""
    pull_quote: Optional[str] = None
    pull_quote_attribution: Optional[str] = None


_SYS = (
    "You are a sharp editorial writer for Next Big Thing (NBT), a Singapore youth "
    "startup community. Turn the RESEARCH into a punchy, insight-led breakdown for "
    "ambitious 18-28 year olds (First Round Review meets Packy McCormick). Not a press "
    "release, not academic.\n\n"
    "RULES:\n"
    "- Hero headline: two short, punchy lines (line1 + line2). Make "
    "it catchy and attractive. Pick accent_word_orange (and "
    "optionally accent_word_purple) from a striking word in the headline.\n"
    "- Reduce the use of 'not x but y' antithesis sentence structure "
    "(e.g. [Company] didn't build [literal/expected thing]. They built "
    "[abstract/emotional thing] over [literal thing it's compared to].).\n"
    "- WRITE TIGHT. Every narrative field is prose, not bullets. "
    "Cut every word that isn't carrying weight.\n"
    "- SECTION TITLES (core_insight_title, timeline_title, loop_title, funding_title, "
    "competitor_title, founder_mode_title, closing_title): write each as an EVOCATIVE "
    "magazine headline UNIQUE to THIS company — name a concrete artifact, moment, or "
    "metaphor from the research. NEVER a generic label. "
    "Good: 'The Cereal Box That Saved Airbnb', 'From Air Mattresses to $31 Billion', "
    "'The Lodging Battlefield', 'Do Things That Don't Scale'. "
    "Bad: 'Funding & growth', 'The founder's journey', 'The competitive map'.\n"
    "- core_insight: push PAST the literal product to the deeper thing customers actually "
    "bought (the feeling/job) and the GAP it closed. core_insight_statement = one sharp "
    "thesis sentence; core_insight_narrative = why it mattered, concrete.\n"
    "- PRIORITIZE the story young founders care about: founder background and what they "
    "did before, how the company actually started (origin), and what the FIRST version "
    "of the product looked like. Put this into founder_mode_narrative.\n"
    "- funding & pricing answer TWO questions only: (1) funding_narrative = how they got "
    "their INITIAL money — the first capital that got them going (grants, competitions, "
    "angels, friends/family, seed/early backers). (2) pricing_note = how the product "
    "EARNS money — the revenue model and how customers actually pay. Keep each tight; "
    "leave empty if the research doesn't support it.\n"
    "- NEVER invent stats, names, or quotes not in the research. If unsupported, leave "
    "the field empty/null.\n"
    "- lessons: each must name a SPECIFIC decision or bet THIS company made, with a "
    "non-obvious takeaway. BAN generic platitudes that could apply to any startup "
    "('create value for all sides', 'believe in your vision', 'identify customer needs', "
    "'focus on growth'). If a headline would fit any company, rewrite it concrete. "
    "Phrase each headline as a punchy IMPERATIVE the reader can steal. "
    "Good: 'Start with your own pain — even if it's just rent', 'Trust is the product, "
    "not a feature', 'Do things that don't scale — then build the machine'. "
    "- timeline_events: 4-6 KEY MILESTONES in the company's journey (founding, first "
    "product, pivots, major funding, breakout growth). "
    "Use varied kinds (founder_story/product/funding/inflection/"
    "user_delight) — do NOT tag everything the same. Order chronologically by year.\n"
    "- loop_nodes: exactly 4 nodes forming a CAUSAL growth loop, each phrased "
    "'More X -> more Y', chained so each node feeds the next and the 4th loops back to "
    "the 1st. Good: 'More hosts -> more listings', 'More listings -> more traveler trust', "
    "'More trust -> more bookings', 'More bookings -> more hosts join'.\n"
    "- competitors: EXACTLY 4 quadrants — the subject company plus 3 rivals. Place "
    "exactly ONE per cell (tr/tl/br/bl); never two in the same cell. The subject "
    "company is winner=true and MUST be placed in 'tr'. Always set axis_x and axis_y. "
    "Because the subject sits top-right, write each axis as '<rival trait> <-> <subject "
    "trait>' so the RIGHT end of axis_x and the TOP (second) end of axis_y describe the "
    "subject's winning traits. Pick a STRATEGIC or EMOTIONAL dimension the subject wins on, "
    "not a dry operational one. Keep poles SHORT: each is 1-3 words, no trailing filler "
    "nouns ('business model', 'strategy', 'approach'). "
    "Good: 'Transactional efficiency <-> Emotional experience'. "
    "Bad: 'Asset-heavy business model <-> Asset-light business model'.\n"
    "- Keep it tight: 3-4 lessons, at most 5 quadrants, 4 loop_nodes. No duplicates.\n\n"
    "Return ONLY a FLAT JSON object with EXACTLY these top-level keys (do not nest "
    "fields under a 'hero' or 'competitor' object):\n"
    '{"volume":"Vol. 01","category_tag":"","hero_line1":"","hero_line2":"",'
    '"accent_word_orange":"","accent_word_purple":"","subheadline":"",'
    '"core_insight_title":"","core_insight_statement":"","core_insight_narrative":"",'
    '"timeline_title":"","timeline_events":[{"year":"","kind":"product","heading":"","body":""}],'
    '"loop_title":"","loop_nodes":["","","",""],"loop_center":"NETWORK EFFECT",'
    '"loop_caption":"","funding_title":"","funding_narrative":"","pricing_note":"",'
    '"competitor_title":"","competitor_framing":"","axis_x":"","axis_y":"",'
    '"quadrants":[{"name":"","their_bet":"","the_gap":"","quadrant":"tr","winner":true}],'
    '"founder_mode_title":"","founder_mode_narrative":"",'
    '"lessons":[{"headline":"","body":"","applicable_to":""}],'
    '"closing_title":"The NBT take","closing_narrative":"","pull_quote":"","pull_quote_attribution":""}'
)


def _dedupe_keep_order(items: list[str]) -> list[str]:
    seen, out = set(), []
    for it in items:
        k = it.strip().lower()[:60]
        if k and k not in seen:
            seen.add(k)
            out.append(it)
    return out


def _research_digest(rd: ResearchDoc) -> str:
    # Cap + dedupe so the editorial prompt stays small -> faster + far fewer
    # malformed-JSON failures from the model.
    parts = [f"STARTUP: {rd.startup_name}"]
    if rd.tagline:
        parts.append(f"TAGLINE: {rd.tagline}")
    if rd.pivotal_insight:
        parts.append(f"INSIGHT: {rd.pivotal_insight}")
    if rd.origin_story:
        parts.append(f"ORIGIN: {rd.origin_story[:600]}")
    if rd.founders:
        founders = _dedupe_keep_order([
            f"- {f.name} ({f.role}): {f.background}"
            + (f" | why: {f.why}" if f.why else "")
            for f in rd.founders])[:5]
        parts.append("FOUNDERS:\n" + "\n".join(founders))
    if rd.product_evolution:
        pe = _dedupe_keep_order([f"- {e.date} {e.event}: {e.significance}"
                                 for e in rd.product_evolution])[:6]
        parts.append("PRODUCT EVOLUTION (earliest = first version):\n" + "\n".join(pe))
    if rd.timeline:
        tl = _dedupe_keep_order([f"- {e.date} [{e.kind}] {e.event}: {e.significance}"
                                 for e in rd.timeline])[:10]
        parts.append("TIMELINE:\n" + "\n".join(tl))
    if rd.funding:
        parts.append("FUNDING (investors = where money came from):\n" + "\n".join(
            f"- {f.round} {f.date} amount={f.amount_usd} val={f.valuation_usd}"
            + (f" investors={', '.join(f.investors)}" if f.investors else "")
            for f in rd.funding[:6]))
    if rd.metrics:
        parts.append("METRICS:\n" + "\n".join(f"- {m.label}: {m.value}" for m in rd.metrics[:8]))
    if rd.competitors:
        parts.append("COMPETITORS:\n" + "\n".join(
            f"- {c.name}: {c.positioning} (gap: {c.our_advantage})"
            for c in rd.competitors[:5]))
    if rd.lessons:
        lessons = _dedupe_keep_order([f"- {l.lesson}: {l.context}" for l in rd.lessons])[:8]
        parts.append("LESSONS:\n" + "\n".join(lessons))
    return "\n\n".join(parts)


# --- assembly --------------------------------------------------------------

def assemble(rd: ResearchDoc, nar: _Narratives, sources: List[Source],
             confidence: float = 0.0) -> StoryBrief:
    slug = slugify(rd.startup_name)
    meta = StoryMeta(startup_name=rd.startup_name, slug=slug, volume=nar.volume,
                     category_tag=nar.category_tag, research_date=date.today().isoformat())

    hero = Hero(line1=nar.hero_line1, line2=nar.hero_line2,
                accent_word_orange=nar.accent_word_orange,
                accent_word_purple=nar.accent_word_purple,
                subheadline=nar.subheadline, stat_bar=stat_bar(rd))

    core = None
    if nar.core_insight_statement:
        core = CoreInsight(title=nar.core_insight_title or "The core insight",
                           statement=nar.core_insight_statement,
                           narrative=nar.core_insight_narrative)

    _VALID_KINDS = ("founder_story", "product", "funding", "inflection", "user_delight")
    if nar.timeline_events:
        tl_items = [TimelineItem(
            year=t.year,
            kind=(t.kind if t.kind in _VALID_KINDS else "product"),
            heading=t.heading, body=t.body) for t in nar.timeline_events if t.heading]
    else:
        tl_items = timeline_items(rd)        # deterministic fallback
    timeline = TimelineSection(title=nar.timeline_title, events=tl_items) if tl_items else None

    loop = None
    if len(nar.loop_nodes) >= 4:
        loop = ProductLoop(title=nar.loop_title or "The product loop",
                           nodes=[LoopNode(label=n) for n in nar.loop_nodes[:4]],
                           center_label=nar.loop_center, caption=nar.loop_caption)

    chart = funding_chart(rd)
    rounds = funding_rounds(rd)
    funding = None
    if chart or rounds:
        funding = FundingSection(title=nar.funding_title, narrative=nar.funding_narrative,
                                 rounds=rounds, chart=chart, pricing_note=nar.pricing_note)

    competitors = None
    if nar.quadrants:
        quads = [QuadrantItem(name=q.name, their_bet=q.their_bet, the_gap=q.the_gap,
                              quadrant=(q.quadrant if q.quadrant in ("tr", "tl", "br", "bl") else "tl"),
                              winner=q.winner) for q in nar.quadrants]
        competitors = CompetitorSection(title=nar.competitor_title or "The competitive map",
                                        framing=nar.competitor_framing,
                                        axis_x=nar.axis_x, axis_y=nar.axis_y, quadrants=quads)

    founder_mode = None
    if nar.founder_mode_title and nar.founder_mode_narrative:
        founder_mode = FounderMode(title=nar.founder_mode_title,
                                   narrative=nar.founder_mode_narrative)

    lessons = [LessonCard(number=i + 1, headline=l.headline, body=l.body,
                          applicable_to=l.applicable_to)
               for i, l in enumerate(nar.lessons)]

    closing = None
    if nar.closing_narrative:
        closing = Closing(title=nar.closing_title, narrative=nar.closing_narrative,
                          pull_quote=nar.pull_quote, attribution=nar.pull_quote_attribution)

    from app.schemas import SourceRef as _SourceRef
    src_refs = [_SourceRef(outlet=s.publisher, url=s.url) for s in sources]

    return StoryBrief(
        meta=meta, hero=hero, core_insight=core, timeline=timeline, product_loop=loop,
        funding=funding, competitors=competitors, founder_mode=founder_mode,
        lessons=lessons, closing=closing, sources=src_refs, overall_confidence=confidence,
    )


async def build(rd: ResearchDoc, sources: List[Source]) -> StoryBrief:
    log.info("=== editorial: building story for %s ===", rd.startup_name)
    corpus = "\n".join(store.read_cached_text(s.raw_text_ref) for s in sources)

    # clean the research merge's noisy funding into chartable rounds; an empty
    # result makes assemble() omit the funding section entirely
    if rd.funding:
        before = len(rd.funding)
        rd.funding = clean_funding(rd.funding)
        if len(rd.funding) != before:
            log.info("funding cleaned: %d -> %d rounds", before, len(rd.funding))

    # relevance + grounding gates (the key problem)
    if rd.metrics and corpus:
        before = len(rd.metrics)
        rd.metrics = verify.filter_metrics(rd.metrics, corpus)
        log.info("metrics grounded: %d/%d kept", len(rd.metrics), before)
    if rd.lessons:
        keep = await verify.relevance_filter([l.lesson for l in rd.lessons])
        rd.lessons = [rd.lessons[i] for i in keep] or rd.lessons
        log.info("lessons relevant: %d kept", len(rd.lessons))

    try:
        # human-sounding voice: warmer temp + nucleus sampling, penalties to kill
        # the repetitive boilerplate cadence that flags LLM prose.
        nar = await gateway.complete_json(
            _SYS, _research_digest(rd), _Narratives,
            role="editorial", temperature=0.85, structured=False,
            sampling={"top_p": 0.92, "frequency_penalty": 0.5, "presence_penalty": 0.3},
        )
    except gateway.LLMError as e:
        log.error("editorial narrative failed: %s — minimal fallback", e)
        nar = _Narratives(hero_line1=f"{rd.startup_name} didn't follow the playbook.",
                          hero_line2="They wrote their own.",
                          subheadline=rd.tagline or "")

    conf = 0.0
    if rd.metrics and corpus:
        scores = [verify.ground_score(f"{m.value} {m.label}", corpus) for m in rd.metrics]
        conf = round(sum(scores) / len(scores), 3) if scores else 0.0

    sb = assemble(rd, nar, sources, confidence=conf)
    log.info("=== editorial done: slug=%s sections=%s ===", sb.meta.slug,
             [k for k in ("core_insight", "timeline", "product_loop", "funding",
                          "competitors", "founder_mode") if getattr(sb, k)])
    return sb
