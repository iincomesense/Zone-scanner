# -*- coding: utf-8 -*-
"""
news.py — Live Financial News Feed Fetcher (RSS)
"""
import time
import datetime
import feedparser

NEWS_SOURCES = [
    {"url": "https://www.moneycontrol.com/rss/MCtopnews.xml", "name": "Moneycontrol"},
    {"url": "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms", "name": "Economic Times"},
    {"url": "https://www.livemint.com/rss/markets", "name": "Mint"}
]

def fetch_latest(limit=20):
    all_news = []
    for source in NEWS_SOURCES:
        try:
            feed = feedparser.parse(source["url"])
            for entry in feed.entries[:7]:
                published = entry.get("published_parsed") or time.localtime()
                dt = datetime.datetime.fromtimestamp(time.mktime(published))
                
                all_news.append({
                    "title": entry.get("title", ""),
                    "link": entry.get("link", ""),
                    "published": dt,
                    "source": source["name"],
                    "summary": entry.get("summary", ""),
                    "tags": [source["name"].upper()]
                })
        except Exception:
            continue
            
    # सबसे नई खबर सबसे ऊपर
    all_news.sort(key=lambda x: x["published"], reverse=True)
    return all_news[:limit]

def fetch_article(url):
    # RSS में summary आ जाती है, इसलिए अलग से फैच की जरूरत नहीं
    return ""
