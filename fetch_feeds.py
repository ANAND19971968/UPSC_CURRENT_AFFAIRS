#!/usr/bin/env python3
"""
FREE, legal, no-server harvester for your UPSC site.
- Pulls official RSS feeds (starting with PIB).
- Normalizes to items.json used by index.html.
- Classifies into UPSC categories with simple rules.
- Keeps last 14 days.
Deploy with GitHub Actions (see .github/workflows/fetch.yml).

Extend FEEDS later (e.g., MEA RSS list on https://www.mea.gov.in/rss-feeds.htm).
"""

import hashlib, json, re, sys
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
import time

try:
    import feedparser  # pip install feedparser
except Exception as e:
    print("feedparser missing. Run: pip install feedparser", file=sys.stderr)
    raise

IST = timezone(timedelta(hours=5, minutes=30))

# --- SOURCES (start minimal, official, stable) ---
FEEDS = [
    {
        "name": "PIB Press Releases (English)",
        "url": "https://pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=3",
        "default_category": "Governance"
    },
    # You can add more later. Prefer official RSS.
    # Example (validate before enabling):
    # {"name":"MEA Press Releases","url":"<PUT_RSS_URL_HERE>","default_category":"International Relations"},
]

# --- CATEGORY RULES ---
RULES = [
    (r"\b(RBI|repo rate|CPI|WPI|inflation|GST|Budget|Fiscal|GDP|SEBI|bank|NBFC|monetary|bond|yield|FDI)\b", "Economy"),
    (r"\b(UN|UNFCCC|BRICS|SCO|G20|bilateral|MoU|agreement|treaty|Indo[- ]?Pacific|MEA|summit|dialogue)\b", "International Relations"),
    (r"\b(environment|forest|wildlife|tiger|NTCA|conservation|pollution|climate|emission|biodiversit(y|ies))\b", "Environment"),
    (r"\b(ISRO|space|satellite|launch|AI|quantum|semiconductor|science|technology|DST|MeitY|CSIR)\b", "Science & Tech"),
    (r"\b(cyclone|flood|earthquake|NDMA|disaster|NDRF|security|border|defence|police|cybersecurity)\b", "Security/Disaster"),
    (r"\b(Supreme Court|High Court|SC\b|HC\b|judgment|verdict|order)\b", "Judgments"),
    (r"\b(Bill|Act|Amendment|Ordinance|Parliament|Lok Sabha|Rajya Sabha|Gazette)\b", "Bills & Acts"),
    (r"\b(Yojana|Mission|Scheme|PM[- ]?[A-Z]|SAMARTH|PM[- ]?KISAN|PMAY|AYUSH|NREGA|Ujjwala|UDAN|Awas)\b", "Schemes"),
    (r"\b(UNESCO|heritage|temple|festival|culture|archaeolog(y|ical)|ASI)\b", "History & Culture"),
    (r"\b(IMD|monsoon|heatwave|El[- ]?Ni\u00f1o|La[- ]?Ni\u00f1a|river|glacier|plateau|geomorphology|earth|geography)\b", "Geography"),
    (r"\b(NITI Aayog|index|report|survey|ranking|scorecard|white paper)\b", "Reports & Indices"),
    # Polity/Governance fallback:
    (r"\b(Cabinet|Constitution|federal|Centre|State|ministry|department|regulation|notification|guideline|policy)\b", "Polity"),
]

FALLBACK = "Polity"

# --- HELPERS ---
def to_ist_ymd(dt_struct, fallback_today=True):
    if not dt_struct:
        if fallback_today:
            return datetime.now(IST).strftime("%Y-%m-%d")
        return None
    # feedparser returns time.struct_time in UTC usually
    try:
        dt = datetime(*dt_struct[:6], tzinfo=timezone.utc).astimezone(IST)
        return dt.strftime("%Y-%m-%d")
    except Exception:
        if fallback_today:
            return datetime.now(IST).strftime("%Y-%m-%d")
        return None

def classify(title, summary, source_hint):
    text = f"{title} {summary} {source_hint}".lower()
    for pattern, cat in RULES:
        if re.search(pattern, text, flags=re.I):
            return cat
    return FALLBACK

def mains_angle(cat):
    M = {
        "Economy": "Inflation–growth, inclusion, fiscal–monetary, reforms implications.",
        "International Relations": "Strategic context for India; treaties, groupings, regional balance.",
        "Environment": "Conservation vs development; climate resilience; regulatory capacity.",
        "Science & Tech": "Tech sovereignty, public–private R&D, ethical and strategic issues.",
        "Security/Disaster": "Preparedness, response, resilience, reforms in institutions.",
        "Judgments": "Implications for rights, federalism, separation of powers.",
        "Bills & Acts": "Objectives, key provisions, impact on stakeholders, challenges.",
        "Schemes": "Targeting, funding, coverage, leakages, evaluation metrics.",
        "History & Culture": "Cultural conservation, tourism, livelihoods, identity debates.",
        "Geography": "Resource distribution, disaster risk, human–environment interactions.",
        "Reports & Indices": "Methodology, findings, policy takeaways and limitations.",
        "Polity": "Governance design, accountability, centre–state dynamics, implementation."
    }
    return M.get(cat, "Policy relevance and implementation challenges.")

def prelims_facts(entry, date_str):
    out = [f"Source: {entry.get('feed_name','')}",
           f"Date: {date_str}"]
    # Light facts from link domain/ministry tokens
    netloc = urlparse(entry.get('link','')).netloc.replace('www.','')
    if netloc:
        out.append(f"Domain: {netloc}")
    return out

def item_id(title, link):
    base = (title or "") + "|" + (link or "")
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:12]

# --- LOAD FEEDS ---
entries = []
for f in FEEDS:
    try:
        d = feedparser.parse(f["url"])
        for e in d.entries:
            title = e.get("title","").strip()
            link  = e.get("link","").strip()
            summary = (e.get("summary") or e.get("description") or "").strip()
            date_str = to_ist_ymd(e.get("published_parsed") or e.get("updated_parsed"))
            rec = {
                "feed_name": f["name"],
                "title": title,
                "link": link,
                "summary": re.sub("<[^<]+?>", "", summary)[:450],
                "date": date_str,
            }
            entries.append(rec)
    except Exception as ex:
        print(f"[WARN] Failed {f['name']}: {ex}", file=sys.stderr)

# --- FILTER last 14 days ---
today_ist = datetime.now(IST).date()
def within_days(dstr, n=14):
    try:
        dt = datetime.strptime(dstr, "%Y-%m-%d").date()
        return (today_ist - dt).days <= n
    except Exception:
        return True

entries = [e for e in entries if within_days(e["date"], 14)]

# --- NORMALIZE TO FRONTEND FORMAT ---
items = []
for e in entries:
    cat = classify(e["title"], e["summary"], e["feed_name"])
    item = {
        "id": item_id(e["title"], e["link"]),
        "date": e["date"],
        "category": cat,
        "title": e["title"],
        "source": e["feed_name"],
        "link": e["link"],
        "summary": e["summary"],
        "prelims": prelims_facts(e, e["date"]),
        "why": "Mains angle: " + mains_angle(cat),
        "tags": []
    }
    items.append(item)

# --- DEDUP ---
seen = set()
deduped = []
for it in items:
    key = (it["title"], it["link"])
    if key in seen: continue
    seen.add(key)
    deduped.append(it)

# --- SORT newest first, then category ---
deduped.sort(key=lambda it: (it["date"], it["category"], it["title"]), reverse=True)

# --- WRITE items.json ---
with open("items.json","w", encoding="utf-8") as f:
    json.dump(deduped, f, ensure_ascii=False, indent=2)

print(f"Wrote {len(deduped)} items to items.json")
