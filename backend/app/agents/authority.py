"""Source authority tiering — used to decide which sources to trust for HARD
facts (funding amounts, dates). A random Medium blog is not Crunchbase.

`authority(domain)` -> "high" | "med" | "low". Financial facts sourced only from
`low` domains are treated as unreliable and sent to the web-search corrector.
"""
from __future__ import annotations

from urllib.parse import urlparse

# Reputable for company/financial facts: databases, wire services, business press,
# SE-Asia startup trade press, official filings.
_HIGH = {
    "crunchbase.com", "pitchbook.com", "cbinsights.com", "tracxn.com",
    "reuters.com", "bloomberg.com", "wsj.com", "ft.com", "cnbc.com",
    "forbes.com", "techcrunch.com", "sec.gov",
    "dealstreetasia.com", "techinasia.com", "e27.co", "kr-asia.com",
    "businesstimes.com.sg", "straitstimes.com", "channelnewsasia.com",
    "nikkei.com", "theverge.com", "wikipedia.org",
}

# Low authority for HARD facts: open-publishing blogs / forums where anyone can
# post an unverified funding table. (Fine as narrative colour, not as a source
# of truth for amounts.)
_LOW = {
    "medium.com", "substack.com", "blogspot.com", "wordpress.com",
    "quora.com", "reddit.com", "tumblr.com", "hashnode.dev",
    "stackademic.com",
}


def _domain(url_or_domain: str) -> str:
    s = (url_or_domain or "").strip().lower()
    if "://" in s or "/" in s:
        s = urlparse(s if "://" in s else f"//{s}", scheme="http").netloc or s
    return s[4:] if s.startswith("www.") else s


def authority(url_or_domain: str) -> str:
    d = _domain(url_or_domain)
    if not d:
        return "med"
    # exact or subdomain match against the reputable set
    if any(d == h or d.endswith("." + h) for h in _HIGH):
        return "high"
    if any(d == h or d.endswith("." + h) for h in _LOW):
        return "low"
    return "med"
