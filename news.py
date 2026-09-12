# -*- coding: utf-8 -*-
"""
news.py — Live Financial News Feed Fetcher (RSS)
Super-fast aggregation for Indian Stock Market.
"""
import time
import datetime
import feedparser

# Google News सबसे तेज़ एग्रीगेटर है, जो मिनटों में खबरें अपडेट करता है
NEWS_SOURCES = [
    {"url": "https://news.google.com/rss/search?q=NSE+OR+BSE+OR+Nifty+OR+Stock+Market+India+when:1d&hl=en-IN&gl=IN&ceid=IN:en", "name": "Google Finance"},
    {"url": "https://www.moneycontrol.com/rss/MCtopnews.xml", "name": "Moneycontrol"}
]

def fetch_latest(limit=20):
    all_news = []
    for source in NEWS_SOURCES:
        try:
            feed = feedparser.parse(source["url"])
            for entry in feed.entries[:12]: # हर सोर्स से टॉप 12
                # Timezone parsing
                published = entry.get("published_parsed")
                if published:
                    dt = datetime.datetime.fromtimestamp(time.mktime(published))
                else:
                    dt = datetime.datetime.now()
                
                # Google News के लंबे टाइटल्स को साफ करना
                title = entry.get("title", "")
                if " - " in title and source["name"] == "Google Finance":
                    title = title.rsplit(" - ", 1)[0]

                all_news.append({
                    "title": title,
                    "link": entry.get("link", ""),
                    "published": dt,
                    "source": source["name"],
                    "summary": entry.get("summary", ""),
                    "tags": [source["name"].upper()]
                })
        except Exception:
            continue
            
    # समय के अनुसार सॉर्ट करें (सबसे नई खबर सबसे ऊपर)
    all_news.sort(key=lambda x: x["published"], reverse=True)
    
    # डुप्लीकेट न्यूज़ को हटाना (अगर दोनों सोर्स में एक ही खबर हो)
    unique_news = []
    seen_titles = set()
    for news in all_news:
        if news["title"] not in seen_titles:
            unique_news.append(news)
            seen_titles.add(news["title"])
            
    return unique_news[:limit]

def fetch_article(url):
    return ""
