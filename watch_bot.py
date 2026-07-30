#!/usr/bin/env python3
"""
Cybersecurity + AI watch bot -> Discord
Fetches new articles from several RSS feeds and posts them to a Discord
channel via webhook. Keeps track of already-sent articles (state.json)
so the same link is never spammed twice.
"""

import html
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

import feedparser
import requests

# ---------------------------------------------------------------------------
# FEED CONFIGURATION
# Add or remove feeds here freely.
# ---------------------------------------------------------------------------
FEEDS = {
    # General cybersecurity / CVE
    "The Hacker News": "https://feeds.feedburner.com/TheHackersNews",
    "BleepingComputer": "https://www.bleepingcomputer.com/feed/",
    "CERT-FR (ANSSI)": "https://www.cert.ssi.gouv.fr/avis/feed/",
    "CISA Advisories": "https://www.cisa.gov/cybersecurity-advisories/all.xml",
    "Krebs on Security": "https://krebsonsecurity.com/feed/",
    "Schneier on Security": "https://www.schneier.com/feed/atom/",
    "SANS Internet Storm Center": "https://isc.sans.edu/rssfeed.xml",
    # blog.talosintelligence.com/feeds/posts/default (the old Feedburner-era
    # URL) now 404s; this is the current feed advertised on the blog itself.Google DeepMind Blog
    "Cisco Talos Intelligence": "https://blog.talosintelligence.com/rss/",
    "The Record": "https://therecord.media/feed",
    "NCSC UK": "https://www.ncsc.gov.uk/api/1/services/v1/report-rss-feed.xml",
    # AI & security
    "OpenAI News": "https://openai.com/news/rss.xml",
    # Anthropic has no official RSS feed (anthropic.com/news/rss.xml returns a
    # 404). This one is generated unofficially by scraping anthropic.com/news:
    # https://github.com/leontloveless/ai-rss-feeds
    "Anthropic News": "https://raw.githubusercontent.com/leontloveless/ai-rss-feeds/main/feeds/anthropic.xml",
    "Google DeepMind Blog": "https://deepmind.google/blog/rss.xml",
    "Google AI Blog": "https://blog.google/technology/ai/rss/",
    # Claude blog (claude.com/blog) has no official RSS feed either; same
    # unofficial mirror project as Anthropic News above.
    "Claude Blog": "https://raw.githubusercontent.com/leontloveless/ai-rss-feeds/main/feeds/claude.xml",
    # cursor.com/rss.xml exists but serves the HTML app shell, not real RSS;
    # use the unofficial mirror instead.
    "Cursor Blog": "https://raw.githubusercontent.com/leontloveless/ai-rss-feeds/main/feeds/cursor-blog.xml",
    "Cloudflare Blog": "https://blog.cloudflare.com/rss/",
    "Hugging Face - Blog": "https://huggingface.co/blog/feed.xml",
    "Mistral AI": "https://mistral.ai/rss.xml",
    # French-language sources
    "Korben": "https://korben.info/feed",
    "ZATAZ": "https://www.zataz.com/feed/",
    "Undernews": "https://www.undernews.fr/feed",
}

STATE_FILE = os.path.join(os.path.dirname(__file__), "state.json")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
MAX_ITEMS_PER_FEED_ON_FIRST_RUN = 3  # avoid a flood of messages on the first run
# Some feeds return far more articles than one might expect (e.g. the OpenAI
# News feed was observed with >1000 entries, not just the latest articles).
# If this cap is smaller than a feed's entry count, the oldest links get
# evicted and then re-detected as "new" on every run, causing a permanent
# flood. Keep it generous.
MAX_LINKS_STORED_PER_FEED = 5000
# feedparser.parse(url) fetches the URL itself with no timeout; a slow or
# hanging server would block the whole run. Fetch with requests instead
# (which does support a timeout) and hand the raw content to feedparser.
FEED_FETCH_TIMEOUT = 15
FEED_FETCH_HEADERS = {"User-Agent": "watch-bot/1.0 (+https://github.com/)"}
# Discord allows at most 10 embeds per message, and ~6000 characters of
# combined embed content. Batching fewer per message leaves headroom for the
# optional "Tags" field without risking a rejected payload on a busy run.
MAX_EMBEDS_PER_MESSAGE = 5


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_state(state: dict) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def strip_html(text: str) -> str:
    """Remove HTML tags and unescape entities from an RSS summary/description.

    Many feeds embed raw HTML (links, bold, images) in <description>; without
    this, Discord would display the literal tags instead of clean text.
    """
    return html.unescape(re.sub(r"<[^>]+>", "", text or "")).strip()


def build_embed(source: str, title: str, link: str, summary: str, tags: list[str]) -> dict:
    embed = {
        "title": title[:256],
        "url": link,
        "description": strip_html(summary)[:300],
        "color": 0x2B90D9,
        "footer": {"text": f"Source: {source}"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    # Only a few feeds populate <category> tags (e.g. BleepingComputer, OpenAI
    # News, Cloudflare Blog); most don't, so this field is added only when
    # present to avoid an empty "Tags" line on every other message.
    if tags:
        embed["fields"] = [{"name": "Tags", "value": ", ".join(tags)[:1024]}]
    return embed


def merge_links(seen_links: list, current_links: list, max_size: int) -> list:
    """Return seen_links + any new current_links, in order, deduplicated,
    capped to the max_size most recent (oldest evicted first).

    Deliberately list-based rather than going through a set: a set's
    iteration order is arbitrary, which would evict links at random instead
    of the oldest ones and risk re-notifying a link still present in the
    feed.
    """
    seen_set = set(seen_links)
    combined = list(seen_links)
    for link in current_links:
        if link and link not in seen_set:
            combined.append(link)
            seen_set.add(link)
    return combined[-max_size:]


def chunk_list(items: list, size: int) -> list:
    return [items[i : i + size] for i in range(0, len(items), size)]


def fetch_feed(url: str):
    resp = requests.get(url, timeout=FEED_FETCH_TIMEOUT, headers=FEED_FETCH_HEADERS)
    resp.raise_for_status()
    return feedparser.parse(resp.content)


def send_discord_message(embeds: list) -> None:
    if not DISCORD_WEBHOOK_URL:
        print("ERROR: DISCORD_WEBHOOK_URL is not set", file=sys.stderr)
        return

    resp = requests.post(DISCORD_WEBHOOK_URL, json={"embeds": embeds}, timeout=15)
    if resp.status_code >= 300:
        print(f"Discord error ({resp.status_code}): {resp.text}", file=sys.stderr)
    else:
        print(f"Posted {len(embeds)} article(s) in one message")

    # Discord rate-limits webhooks: small safety pause
    time.sleep(1.2)


def send_digest(embeds: list) -> None:
    for chunk in chunk_list(embeds, MAX_EMBEDS_PER_MESSAGE):
        send_discord_message(chunk)


def send_feed_error_report(errors: list) -> None:
    lines = "\n".join(f"- **{source}**: {reason}" for source, reason in errors)
    embed = {
        "title": f"⚠️ {len(errors)} feed(s) failed this run",
        "description": lines[:4000],
        "color": 0xE74C3C,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    send_discord_message([embed])


def main() -> None:
    state = load_state()
    new_state = dict(state)  # working copy
    new_embeds = []
    feed_errors = []

    for source, url in FEEDS.items():
        seen_links = state.get(source, [])
        seen_set = set(seen_links)
        first_run_for_feed = source not in state

        try:
            parsed = fetch_feed(url)
        except Exception as e:
            print(f"Error reading feed {source}: {e}", file=sys.stderr)
            feed_errors.append((source, str(e)))
            continue

        if parsed.bozo and not parsed.entries:
            print(f"Invalid or empty feed for {source}", file=sys.stderr)
            feed_errors.append((source, "invalid or empty feed"))
            continue

        entries = parsed.entries
        # On the very first run for a feed, only NOTIFY about the last N
        # articles to avoid a massive flood, but still WALK (and therefore
        # remember in the state) every article in the feed: otherwise,
        # articles beyond the first N are never recorded in state.json and
        # would all be detected as "new" (and all notified at once) on the
        # very next run.
        notify_count = MAX_ITEMS_PER_FEED_ON_FIRST_RUN if first_run_for_feed else len(entries)

        current_links = []
        for i, entry in enumerate(entries):
            link = entry.get("link", "")
            title = entry.get("title", "Untitled")
            summary = entry.get("summary", entry.get("description", ""))
            tags = [t.get("term") for t in entry.get("tags", []) if t.get("term")]

            current_links.append(link)
            if link and link not in seen_set and i < notify_count:
                new_embeds.append(build_embed(source, title, link, summary, tags))
                print(f"New: [{source}] {title}")

        new_state[source] = merge_links(seen_links, current_links, MAX_LINKS_STORED_PER_FEED)

    send_digest(new_embeds)
    if feed_errors:
        send_feed_error_report(feed_errors)

    save_state(new_state)


if __name__ == "__main__":
    main()
