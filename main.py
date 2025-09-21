import os
import re
import json
import time
import sqlite3
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, List, Dict, Optional, Tuple

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Optional Reddit import (guard at runtime)
try:
    import praw
except Exception:
    praw = None


# ---------------------------
# Utilities & Config
# ---------------------------

load_dotenv()

DB_PATH = os.getenv("DB_PATH", "./shift_codes.db")

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "").strip()

REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID", "").strip()
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET", "").strip()
REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT", "bl4-shift-bot/1.0").strip()
REDDIT_SUBS = [s.strip() for s in os.getenv("REDDIT_SUBS", "").split(",") if s.strip()]

HTML_SOURCES = [u.strip() for u in os.getenv("HTML_SOURCES", "").split(",") if u.strip()]


# ---------------------------
# Code extraction & reward inference
# ---------------------------

CODE_PATTERNS = [
    re.compile(r"\b[A-Z0-9]{5}(?:-[A-Z0-9]{5}){4}\b", re.I),  # 5x5
    re.compile(r"\b[A-Z0-9]{4}(?:-[A-Z0-9]{4}){3,4}\b", re.I) # 4x4
]

REWARD_KEYWORDS = {
    "golden key": ["golden key", "gold keys", "keys", "gold key", "5 keys", "3 keys"],
    "vault card": ["vault card", "vaultcard"],
    "cosmetic": ["skin", "head", "cosmetic"],
    "diamond key": ["diamond key"],
    "weapon": ["weapon", "gun"],
    "eridium": ["eridium"],
    "xp": ["xp", "experience"],
    "event": ["event", "limited time", "expires"],
}

def extract_codes(text: str) -> List[str]:
    found = set()
    for pat in CODE_PATTERNS:
        for m in pat.findall(text or ""):
            found.add(m.upper())
    return sorted(found)

def infer_reward(text: str) -> Optional[str]:
    lower = (text or "").lower()
    scores: Dict[str, int] = {}
    for reward, kws in REWARD_KEYWORDS.items():
        for kw in kws:
            if kw in lower:
                scores[reward] = scores.get(reward, 0) + 1
    if not scores:
        return None
    return sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[0][0]


# ---------------------------
# Storage (SQLite)
# ---------------------------

def init_db(db_path: str = DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.execute("""        CREATE TABLE IF NOT EXISTS codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            reward_type TEXT,
            source TEXT,
            context TEXT,
            date_found_utc TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_code ON codes(code)")
    conn.commit()
    return conn

def code_exists(conn: sqlite3.Connection, code: str) -> bool:
    cur = conn.execute("SELECT 1 FROM codes WHERE code = ?", (code,))
    return cur.fetchone() is not None

def insert_code(conn: sqlite3.Connection, code: str, reward_type: Optional[str], source: str, context: str):
    conn.execute(
        "INSERT OR IGNORE INTO codes (code, reward_type, source, context, date_found_utc) VALUES (?,?,?,?,?)",
        (code, reward_type, source, context, datetime.now(timezone.utc).isoformat())
    )
    conn.commit()


# ---------------------------
# Notifiers (Discord / Slack)
# ---------------------------

REDEEM_URL = os.getenv("REDEEM_URL", "https://shift.gearboxsoftware.com/rewards")

def notify_discord(code: str, reward: Optional[str], source: str, context: str):
    if not DISCORD_WEBHOOK_URL:
        return
    src_label = "Reddit" if source.lower().startswith("reddit:") else "Website"
    content = (
        f"**New Borderlands SHiFT Code**\n"
        f"**Code:** `{code}`\n"
        f"**Reward:** {reward or 'Unknown'}\n"
        f"**Source:** {src_label}\n"
        f"**Redeem:** {REDEEM_URL}"
    )
    payload = {"content": content}
    try:
        requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=15).raise_for_status()
    except Exception as e:
        print(f"[WARN] Discord notify failed: {e}")


def notify_slack(code: str, reward: Optional[str], source: str, context: str):
    if not SLACK_WEBHOOK_URL:
        return
    excerpt = context if len(context) < 1500 else (context[:1500] + "…")
    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": "New Borderlands SHiFT Code", "emoji": True}},
        {"type": "section", "fields": [
            {"type": "mrkdwn", "text": f"*Code:*\n`{code}`"},
            {"type": "mrkdwn", "text": f"*Reward:*\n{reward or 'Unknown'}"},
            {"type": "mrkdwn", "text": f"*Source:*\n{source}"},
        ]},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*Context*\n{excerpt}"}}
    ]
    try:
        requests.post(SLACK_WEBHOOK_URL, json={"blocks": blocks}, timeout=15).raise_for_status()
    except Exception as e:
        print(f"[WARN] Slack notify failed: {e}")

def notify_all(new_items: List[Tuple[str, Optional[str], str, str]]):
    for code, reward, src, ctx in new_items:
        notify_discord(code, reward, src, ctx)
        notify_slack(code, reward, src, ctx)


# ---------------------------
# Fetchers
# ---------------------------

@dataclass
class FoundItem:
    code: str
    reward: Optional[str]
    source: str
    context: str

class BaseFetcher:
    name: str = "base"
    def fetch(self) -> Iterable[FoundItem]:
        raise NotImplementedError


class HtmlFetcher(BaseFetcher):
    name = "html"

    def __init__(self, urls: List[str]):
        self.urls = urls

    def fetch(self) -> Iterable[FoundItem]:
        for url in self.urls:
            try:
                r = requests.get(url, timeout=20, headers={"User-Agent": "bl4-shift-bot/1.0"})
                r.raise_for_status()
                soup = BeautifulSoup(r.text, "html.parser")
                text = soup.get_text("\n", strip=True)
                codes = extract_codes(text)
                for code in codes:
                    reward = infer_reward(text)
                    yield FoundItem(code=code, reward=reward, source=f"HTML:{url}", context=text[:2500])
            except Exception as e:
                print(f"[WARN] HTML fetch failed for {url}: {e}")

class RedditFetcher(BaseFetcher):
    name = "reddit"

    def __init__(self, client_id: str, client_secret: str, user_agent: str, subs: List[str]):
        self.enabled = bool(client_id and client_secret and user_agent and praw)
        self.subs = subs
        if self.enabled:
            self.reddit = praw.Reddit(
                client_id=client_id,
                client_secret=client_secret,
                user_agent=user_agent,
            )
        else:
            self.reddit = None

    def fetch(self) -> Iterable[FoundItem]:
        if not self.enabled:
            return
        for sub in self.subs:
            try:
                for post in self.reddit.subreddit(sub).new(limit=25):
                    blob = f"{post.title}\n\n{getattr(post, 'selftext', '')}"
                    codes = extract_codes(blob)
                    if not codes:
                        continue
                    try:
                        post.comments.replace_more(limit=0)
                        take = min(10, len(post.comments))
                        for i in range(take):
                            c = post.comments[i]
                            if hasattr(c, "body"):
                                blob += "\n" + c.body
                    except Exception:
                        pass
                    reward = infer_reward(blob)
                    for code in codes:
                        yield FoundItem(
                            code=code,
                            reward=reward,
                            source=f"Reddit:r/{sub} ({post.id})",
                            context=blob[:2500]
                        )
            except Exception as e:
                print(f"[WARN] Reddit fetch failed for r/{sub}: {e}")


# ---------------------------
# Pipeline
# ---------------------------

def run_once() -> List[FoundItem]:
    fetchers: List[BaseFetcher] = []

    if HTML_SOURCES:
        fetchers.append(HtmlFetcher(HTML_SOURCES))

    if REDDIT_SUBS:
        fetchers.append(RedditFetcher(
            client_id=REDDIT_CLIENT_ID,
            client_secret=REDDIT_CLIENT_SECRET,
            user_agent=REDDIT_USER_AGENT,
            subs=REDDIT_SUBS
        ))

    if not fetchers:
        print("No sources are configured. Provide HTML_SOURCES and/or Reddit credentials in .env.")
        return []

    conn = init_db(DB_PATH)
    new_items: List[FoundItem] = []
    for f in fetchers:
        try:
            for item in f.fetch():
                if not code_exists(conn, item.code):
                    insert_code(conn, item.code, item.reward, item.source, item.context)
                    new_items.append(item)
        except Exception:
            traceback.print_exc()

    if new_items:
        notify_all([(i.code, i.reward, i.source, i.context) for i in new_items])

    return new_items

def main():
    start = time.time()
    found = run_once()
    dt = time.time() - start
    if found:
        print(f"🎉 Found {len(found)} new code(s) in {dt:.1f}s")
        for i in found:
            print(f"- {i.code} [{i.reward or 'Unknown'}] <- {i.source}")
    else:
        print(f"No new codes. Done in {dt:.1f}s")

if __name__ == "__main__":
    main()
