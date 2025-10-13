import os
import re
import json
import time
import sqlite3
import logging
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, List, Dict, Optional, Tuple
from functools import wraps, lru_cache

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Optional Reddit import (guard at runtime)
try:
    import praw
except Exception:
    praw = None

# ---------------------------
# Logging Setup
# ---------------------------

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

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

# Request session with connection pooling
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "bl4-shift-bot/1.0"})

# ---------------------------
# Retry Decorator
# ---------------------------

def retry(max_attempts=3, delay=1, backoff=2):
    """Retry decorator with exponential backoff"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_attempts - 1:
                        logger.error(f"Function {func.__name__} failed after {max_attempts} attempts: {e}")
                        raise
                    wait_time = delay * (backoff ** attempt)
                    logger.warning(f"Attempt {attempt + 1} failed for {func.__name__}: {e}. Retrying in {wait_time}s...")
                    time.sleep(wait_time)
            return wrapper
        return decorator

# ---------------------------
# Configuration Validation
# ---------------------------

def validate_config():
    """Validate configuration on startup"""
    if not (HTML_SOURCES or (REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET and REDDIT_SUBS)):
        raise ValueError("No valid sources configured. Provide HTML_SOURCES and/or Reddit credentials in .env.")
    
    if DISCORD_WEBHOOK_URL and not DISCORD_WEBHOOK_URL.startswith('http'):
        raise ValueError("Invalid Discord webhook URL format")
    
    if SLACK_WEBHOOK_URL and not SLACK_WEBHOOK_URL.startswith('http'):
        raise ValueError("Invalid Slack webhook URL format")
    
    logger.info("Configuration validated successfully")

# ---------------------------
# Code extraction & reward inference
# ---------------------------

CODE_PATTERNS = [
    re.compile(r"\b[A-Z0-9]{5}(?:-[A-Z0-9]{5}){4}\b", re.I),  # 5x5
    re.compile(r"\b[A-Z0-9]{4}(?:-[A-Z0-9]{4}){3,4}\b", re.I) # 4x4
]

REWARD_KEYWORDS = {
    "golden key": [
        "golden key", "golden keys", "5 golden keys", "3 golden keys",
        "gold key", "gold keys", "5 keys", "3 keys"
    ],
    "diamond key": [
        "diamond key", "diamond keys"
    ],
    "vault card": [
        "vault card", "vaultcard"
    ],
    "cosmetic": [
        "cosmetic", "skin", "weapon skin", "head", "appearance", "outfit", "customization"
    ],
    "weapon": [
        "weapon", "gun", "legendary weapon", "rare weapon"
    ],
    "eridium": [
        "eridium"
    ],
    "xp": [
        "xp", "experience"
    ],
    "event": [
        "event", "limited time", "expires"
    ]
}

def normalize_code(code: str) -> str:
    """Normalize code format for better duplicate detection"""
    return re.sub(r'[^A-Z0-9]', '', code.upper())

def extract_codes(text: str) -> List[str]:
    """Extract shift codes from text with improved normalization"""
    found = set()
    for pat in CODE_PATTERNS:
        for m in pat.findall(text or ""):
            normalized = normalize_code(m)
            # Re-format to standard format
            if len(normalized) == 25:  # 5x5 format
                formatted = '-'.join([normalized[i:i+5] for i in range(0, 25, 5)])
            elif len(normalized) in [16, 20]:  # 4x4 format
                chunk_size = 4
                formatted = '-'.join([normalized[i:i+chunk_size] for i in range(0, len(normalized), chunk_size)])
            else:
                formatted = m.upper()
            found.add(formatted)
    return sorted(found)

@lru_cache(maxsize=1000)
def infer_reward(text: str) -> Optional[str]:
    """Infer reward type from text with caching"""
    if not text:
        return None
    
    lower = text.lower()
    scores: Dict[str, int] = {}
    
    for reward, kws in REWARD_KEYWORDS.items():
        for kw in kws:
            if kw in lower:
                scores[reward] = scores.get(reward, 0) + 1
    
    if not scores:
        return None
    
    return sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[0][0]

# ---------------------------
# Storage (SQLite) with improvements
# ---------------------------

def init_db(db_path: str = DB_PATH):
    """Initialize database with improved schema"""
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            normalized_code TEXT NOT NULL,
            reward_type TEXT,
            source TEXT,
            context TEXT,
            date_found_utc TEXT,
            expiry_date TEXT,
            is_active BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Create indexes for better performance
    conn.execute("CREATE INDEX IF NOT EXISTS idx_code ON codes(code)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_normalized_code ON codes(normalized_code)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_is_active ON codes(is_active)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_date_found ON codes(date_found_utc)")
    
    conn.commit()
    return conn

def code_exists(conn: sqlite3.Connection, code: str) -> bool:
    """Check if code exists using normalized format"""
    normalized = normalize_code(code)
    cur = conn.execute("SELECT 1 FROM codes WHERE normalized_code = ?", (normalized,))
    return cur.fetchone() is not None

def insert_codes_batch(conn: sqlite3.Connection, codes_data: List[Tuple]):
    """Insert multiple codes in a single transaction"""
    if not codes_data:
        return
    
    try:
        conn.executemany(
            """INSERT OR IGNORE INTO codes 
               (code, normalized_code, reward_type, source, context, date_found_utc) 
               VALUES (?,?,?,?,?,?)""",
            codes_data
        )
        conn.commit()
        logger.info(f"Inserted {len(codes_data)} codes in batch")
    except Exception as e:
        logger.error(f"Batch insert failed: {e}")
        conn.rollback()
        raise

def get_stats(conn: sqlite3.Connection) -> Dict:
    """Get database statistics"""
    cur = conn.execute("SELECT COUNT(*) FROM codes")
    total_codes = cur.fetchone()[0]
    
    cur = conn.execute("SELECT COUNT(*) FROM codes WHERE is_active = 1")
    active_codes = cur.fetchone()[0]
    
    cur = conn.execute("SELECT COUNT(DISTINCT reward_type) FROM codes WHERE reward_type IS NOT NULL")
    reward_types = cur.fetchone()[0]
    
    return {
        "total_codes": total_codes,
        "active_codes": active_codes,
        "reward_types": reward_types
    }

# ---------------------------
# Notifiers with retry logic
# ---------------------------

REDEEM_URL = os.getenv("REDEEM_URL", "https://shift.gearboxsoftware.com/rewards")

@retry(max_attempts=3, delay=2)
def send_webhook(url: str, payload: dict, timeout: int = 15):
    """Send webhook with retry logic"""
    response = SESSION.post(url, json=payload, timeout=timeout)
    response.raise_for_status()
    return response

def notify_discord(code: str, reward: Optional[str], source: str, context: str):
    """Send Discord notification with improved formatting"""
    if not DISCORD_WEBHOOK_URL:
        return
    
    try:
        src_label = "Reddit" if source.lower().startswith("reddit:") else "Website"
        content = (
            f"🎮 **New Borderlands SHiFT Code Found!**\n"
            f"**Code:** `{code}`\n"
            f"**Reward:** {reward or 'Unknown'}\n"
            f"**Source:** {src_label}\n"
            f"**Redeem:** {REDEEM_URL}\n"
            f"**Time:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
        )
        
        payload = {
            "content": content,
            "username": "SHiFT Code Bot",
            "avatar_url": "https://i.imgur.com/borderlands-icon.png"  # Optional
        }
        
        send_webhook(DISCORD_WEBHOOK_URL, payload)
        logger.info(f"Discord notification sent for code: {code}")
        
    except Exception as e:
        logger.error(f"Discord notification failed for {code}: {e}")

def notify_slack(code: str, reward: Optional[str], source: str, context: str):
    """Send Slack notification with improved formatting"""
    if not SLACK_WEBHOOK_URL:
        return
    
    try:
        excerpt = context if len(context) < 1500 else (context[:1500] + "…")
        
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "🎮 New Borderlands SHiFT Code",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Code:*\n`{code}`"},
                    {"type": "mrkdwn", "text": f"*Reward:*\n{reward or 'Unknown'}"},
                    {"type": "mrkdwn", "text": f"*Source:*\n{source}"},
                    {"type": "mrkdwn", "text": f"*Time:*\n{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"}
                ]
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Context:*\n{excerpt}"}
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Redeem Code"},
                        "url": REDEEM_URL,
                        "style": "primary"
                    }
                ]
            }
        ]
        
        payload = {"blocks": blocks}
        send_webhook(SLACK_WEBHOOK_URL, payload)
        logger.info(f"Slack notification sent for code: {code}")
        
    except Exception as e:
        logger.error(f"Slack notification failed for {code}: {e}")

def notify_all(new_items: List[Tuple[str, Optional[str], str, str]]):
    """Send notifications for all new codes"""
    if not new_items:
        return
    
    logger.info(f"Sending notifications for {len(new_items)} new codes")
    
    for code, reward, src, ctx in new_items:
        try:
            notify_discord(code, reward, src, ctx)
            notify_slack(code, reward, src, ctx)
            # Small delay between notifications to avoid rate limits
            time.sleep(0.5)
        except Exception as e:
            logger.error(f"Notification failed for code {code}: {e}")

# ---------------------------
# Fetchers with improvements
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

    @retry(max_attempts=3, delay=2)
    def fetch_url(self, url: str) -> str:
        """Fetch URL content with retry logic"""
        response = SESSION.get(url, timeout=20)
        response.raise_for_status()
        return response.text

    def fetch(self) -> Iterable[FoundItem]:
        """Fetch codes from HTML sources"""
        for url in self.urls:
            try:
                logger.info(f"Fetching HTML from: {url}")
                html_content = self.fetch_url(url)
                
                soup = BeautifulSoup(html_content, "html.parser")
                text = soup.get_text("\n", strip=True)
                
                codes = extract_codes(text)
                logger.info(f"Found {len(codes)} codes from {url}")
                
                for code in codes:
                    reward = infer_reward(text)
                    yield FoundItem(
                        code=code,
                        reward=reward,
                        source=f"HTML:{url}",
                        context=text[:2500]
                    )
                    
            except Exception as e:
                logger.error(f"HTML fetch failed for {url}: {e}")

class RedditFetcher(BaseFetcher):
    name = "reddit"

    def __init__(self, client_id: str, client_secret: str, user_agent: str, subs: List[str]):
        self.enabled = bool(client_id and client_secret and user_agent and praw)
        self.subs = subs
        
        if self.enabled:
            try:
                self.reddit = praw.Reddit(
                    client_id=client_id,
                    client_secret=client_secret,
                    user_agent=user_agent,
                )
                # Test connection
                self.reddit.user.me()
                logger.info("Reddit connection established successfully")
            except Exception as e:
                logger.error(f"Reddit connection failed: {e}")
                self.enabled = False
                self.reddit = None
        else:
            self.reddit = None
            logger.warning("Reddit fetcher disabled - missing credentials or praw library")

    def fetch(self) -> Iterable[FoundItem]:
        """Fetch codes from Reddit sources"""
        if not self.enabled:
            return
            
        for sub in self.subs:
            try:
                logger.info(f"Fetching from r/{sub}")
                posts_processed = 0
                
                for post in self.reddit.subreddit(sub).new(limit=25):
                    posts_processed += 1
                    blob = f"{post.title}\n\n{getattr(post, 'selftext', '')}"
                    
                    codes = extract_codes(blob)
                    if not codes:
                        continue
                    
                    # Fetch comments with better error handling
                    try:
                        post.comments.replace_more(limit=0)
                        comment_count = min(10, len(post.comments))
                        
                        for i in range(comment_count):
                            comment = post.comments[i]
                            if hasattr(comment, "body"):
                                blob += "\n" + comment.body
                                
                    except Exception as e:
                        logger.warning(f"Failed to fetch comments for post {post.id}: {e}")
                    
                    reward = infer_reward(blob)
                    
                    for code in codes:
                        yield FoundItem(
                            code=code,
                            reward=reward,
                            source=f"Reddit:r/{sub} ({post.id})",
                            context=blob[:2500]
                        )
                
                logger.info(f"Processed {posts_processed} posts from r/{sub}")
                
            except Exception as e:
                logger.error(f"Reddit fetch failed for r/{sub}: {e}")

# ---------------------------
# Metrics and Health Check
# ---------------------------

def collect_metrics(new_items: List[FoundItem], execution_time: float, fetchers: List[BaseFetcher]) -> Dict:
    """Collect execution metrics"""
    return {
        "codes_found": len(new_items),
        "sources_checked": len(fetchers),
        "execution_time_seconds": round(execution_time, 2),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "new_codes": [{"code": item.code, "reward": item.reward, "source": item.source} for item in new_items]
    }

def health_check() -> Dict:
    """Perform health check"""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("SELECT 1").fetchone()
        conn.close()
        
        # Test session
        SESSION.get("https://httpbin.org/status/200", timeout=5)
        
        return {
            "status": "healthy",
            "database": "ok",
            "network": "ok",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

# ---------------------------
# Main Pipeline
# ---------------------------

def run_once() -> List[FoundItem]:
    """Run the bot once with improved error handling and logging"""
    logger.info("Starting bot execution")
    
    # Validate configuration
    validate_config()
    
    # Initialize fetchers
    fetchers: List[BaseFetcher] = []
    
    if HTML_SOURCES:
        fetchers.append(HtmlFetcher(HTML_SOURCES))
        logger.info(f"HTML fetcher initialized with {len(HTML_SOURCES)} sources")
    
    if REDDIT_SUBS:
        reddit_fetcher = RedditFetcher(
            client_id=REDDIT_CLIENT_ID,
            client_secret=REDDIT_CLIENT_SECRET,
            user_agent=REDDIT_USER_AGENT,
            subs=REDDIT_SUBS
        )
        if reddit_fetcher.enabled:
            fetchers.append(reddit_fetcher)
            logger.info(f"Reddit fetcher initialized with {len(REDDIT_SUBS)} subreddits")
    
    if not fetchers:
        logger.error("No fetchers available")
        return []
    
    # Initialize database
    conn = init_db(DB_PATH)
    
    # Collect new items
    new_items: List[FoundItem] = []
    codes_to_insert: List[Tuple] = []
    
    for fetcher in fetchers:
        try:
            logger.info(f"Running {fetcher.name} fetcher")
            fetcher_start = time.time()
            
            for item in fetcher.fetch():
                if not code_exists(conn, item.code):
                    new_items.append(item)
                    codes_to_insert.append((
                        item.code,
                        normalize_code(item.code),
                        item.reward,
                        item.source,
                        item.context,
                        datetime.now(timezone.utc).isoformat()
                    ))
            
            fetcher_time = time.time() - fetcher_start
            logger.info(f"{fetcher.name} fetcher completed in {fetcher_time:.2f}s")
            
        except Exception as e:
            logger.error(f"Fetcher {fetcher.name} failed: {e}")
            traceback.print_exc()
    
    # Batch insert new codes
    if codes_to_insert:
        insert_codes_batch(conn, codes_to_insert)
    
    # Send notifications
    if new_items:
        notify_all([(item.code, item.reward, item.source, item.context) for item in new_items])
    
    # Log database stats
    stats = get_stats(conn)
    logger.info(f"Database stats: {stats}")
    
    conn.close()
    return new_items

def main():
    """Main entry point with comprehensive logging and metrics"""
    try:
        logger.info("=" * 50)
        logger.info("Borderlands 4 SHiFT Code Bot Starting")
        logger.info("=" * 50)
        
        # Health check
        health = health_check()
        if health["status"] != "healthy":
            logger.error(f"Health check failed: {health}")
            return
        
        start_time = time.time()
        found_items = run_once()
        execution_time = time.time() - start_time
        
        # Collect and log metrics
        metrics = collect_metrics(found_items, execution_time, [])
        
        if found_items:
            logger.info(f"🎉 Found {len(found_items)} new code(s) in {execution_time:.1f}s")
            for item in found_items:
                logger.info(f"  - {item.code} [{item.reward or 'Unknown'}] <- {item.source}")
        else:
            logger.info(f"No new codes found. Execution completed in {execution_time:.1f}s")
        
        # Save metrics to file (optional)
        try:
            with open("metrics.json", "w") as f:
                json.dump(metrics, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save metrics: {e}")
        
        logger.info("Bot execution completed successfully")
        
    except Exception as e:
        logger.error(f"Bot execution failed: {e}")
        traceback.print_exc()
        raise

if __name__ == "__main__":
    main()