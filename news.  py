"""
news.py — live financial headlines from free, keyless RSS feeds.

Feeds are hand-picked so every user gets real, current news without any API key.
Each entry: {title, link, source, published, summary, tags}.
`fetch_article(url)` fetches the full body text for the in-page reader.
"""
from __future__ import annotations

import re
import html
import time
import datetime
import requests
import feedparser

# (source name, rss url) — keyless, dependable.
FEEDS = [
    ("Moneycontrol", "https://www.moneycontrol.com/rss/headlines.xml"),
    ("Economic Times", "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms"),
    ("Business Standard", "https://www.business-standard.com/rss/markets-106.rss"),
    ("Reuters Markets", "https://feeds.reuters.com/reuters/businessNews"),
    ("Reuters India", "https://feeds.reuters.com/Reuters/IndiaTopNews"),
    ("Investing", "https://www.investing.com/rss/news_1.rss"),
]

# Keywords -> tag, used to auto-flag headlines that mention the user's themes.
TAG_KEYWORDS = {
    "NIFTY": "NIFTY",
    "SENSEX": "SENSEX",
    "BANKNIFTY": "BANKNIFTY",
    "FED": "FED",
    "RBI": "RBI",
    "USD/INR": "USDINR",
    "RUPEE": "USDINR",
    "GOLD": "GOLD",
    "SILVER": "SILVER",
    "CRUDE": "OIL",
    "OIL": "OIL",
    "DOW": "US30",
    "S&P": "US500",
    "NIKKEI": "JP225",
    "DXY": "DXY",
    "TREASURY": "RATES",
    "BOND": "RATES",
}


def _fetch_feed(url, timeout=12):
    try:
        r = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200:
            return []
        return feedparser.parse(r.content).entries
    except Exception:
        return []


def _clean(txt):
    if not txt:
        return ""
    txt = html.unescape(txt)
    txt = re.sub(r"<[^>]+>", " ", txt)
    return re.sub(r"\s+", " ", txt).strip()


def _tags(title):
    t = []
    up = title.upper()
    for kw, tag in TAG_KEYWORDS.items():
        if kw in up and tag not in t:
            t.append(tag)
    return t[:3]


def fetch_article(url, max_chars=1400):
    """Fetch and strip a webpage into readable text (for the in-page 'read full')."""
    if not url or url == "#":
        return ""
    try:
        r = requests.get(url, timeout=12, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200:
            return ""
        t = r.text
        # strip scripts/styles, then tags, keep some paragraph breaks
        t = re.sub(r"(?is)<(script|style|noscript|nav|footer|header|figure|svg)[^>]*>.*?</\1>", " ", t)
        t = re.sub(r"(?is)<br[^>]*>", "\n", t)
        t = re.sub(r"(?is)</p>", "\n", t)
        t = re.sub(r"(?is)<[^>]+>", " ", t)
        t = html.unescape(t)
        t = re.sub(r"[ \t]+", " ", t)
        t = re.sub(r"\n\s*\n+", "\n", t)
        t = t.strip()
        # Drop obvious header/footer/navigation boilerplate lines (keep article body)
        drop = ("subscribe now", "cookie policy", "republication", "newsletter",
                "©", "all rights reserved", "read more", "also read", "watch")
        lines = [ln.strip() for ln in t.split("\n")]
        keep = []
        for ln in lines:
            low = ln.lower()
            if any(d in low for d in drop) and len(low) < 120:
                continue
            keep.append(ln)
        t = "\n".join(keep)
        return t[:max_chars]
    except Exception:
        return ""


def fetch_latest(limit=30, with_body=False):
    """Return newest items across feeds, merged & de-duplicated, newest first.

    with_body=True also adds `body` (<=~900 chars) by fetching the article page
    (only called for a short list of headlines to keep it light)."""
    items = _fetch_latest_core(limit)
    if with_body:
        for it in items:
            it["body"] = fetch_article(it["link"], max_chars=900) or it.get("summary", "")
    return items


def _fetch_latest_core(limit=30):
    """Return newest items across feeds, merged & de-duplicated, newest first."""
    seen = set()
    items = []
    for name, url in FEEDS:
        for e in _fetch_feed(url):
            title = _clean(e.get("title", ""))
            if not title:
                continue
            link = e.get("link", "")
            if link in seen:
                continue
            seen.add(link)
            ts = None
            for k in ("published", "updated"):
                if e.get(k):
                    try:
                        st = e.get("published_parsed") or e.get("updated_parsed")
                        if st:
                            ts = datetime.datetime(*st[:6])
                    except Exception:
                        ts = None
                    break
            summary = _clean(e.get("summary", ""))[:220]
            items.append({
                "title": title,
                "link": link,
                "source": name,
                "published": ts or datetime.datetime.now(),
                "summary": summary,
                "tags": _tags(title + " " + summary),
            })
    items.sort(key=lambda x: x["published"], reverse=True)
    return items[:limit]


if __name__ == "__main__":
    for it in fetch_latest(15):
        print(f"[{it['source']}] {it['published'].strftime('%H:%M')} {it['title'][:90]}  [{','.join(it['tags'])}]")
