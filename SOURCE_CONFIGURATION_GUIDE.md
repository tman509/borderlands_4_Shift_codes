# Source Configuration Guide

## How to Add/Modify Sources

Edit `config/production.json` in the `sources` array to add websites and Reddit sources.

## Website Sources (HTML)

```json
{
  "id": 4,
  "name": "Your Website Name",
  "url": "https://example.com/news",
  "type": "html",
  "enabled": true,
  "parser_hints": {
    "selectors": [".content", ".article", ".news-item"],
    "fallback_regex": true,
    "max_pages": 3
  },
  "rate_limit": {
    "requests_per_minute": 30,
    "delay_between_requests": 2.0,
    "burst_limit": 5
  }
}
```

## Reddit Sources

```json
{
  "id": 5,
  "name": "Borderlands 4 Reddit",
  "url": "https://www.reddit.com/r/borderlands4",
  "type": "reddit",
  "enabled": true,
  "parser_hints": {
    "subreddit": "borderlands4",
    "post_limit": 25,
    "include_comments": true,
    "sort_method": "new"
  },
  "rate_limit": {
    "requests_per_minute": 20,
    "delay_between_requests": 3.0,
    "burst_limit": 3
  }
}
```

## RSS/Feed Sources

```json
{
  "id": 6,
  "name": "Gaming News RSS",
  "url": "https://example.com/rss.xml",
  "type": "rss",
  "enabled": true,
  "parser_hints": {
    "max_items": 50,
    "include_content": true
  },
  "rate_limit": {
    "requests_per_minute": 60,
    "delay_between_requests": 1.0,
    "burst_limit": 10
  }
}
```

## Configuration Options

### Required Fields:
- `id`: Unique identifier (increment from existing)
- `name`: Human-readable name
- `url`: Source URL
- `type`: "html", "reddit", or "rss"
- `enabled`: true/false

### Parser Hints:
- **HTML**: `selectors` (CSS selectors), `fallback_regex`, `max_pages`
- **Reddit**: `subreddit`, `post_limit`, `include_comments`, `sort_method`
- **RSS**: `max_items`, `include_content`

### Rate Limiting:
- `requests_per_minute`: Max requests per minute
- `delay_between_requests`: Seconds between requests
- `burst_limit`: Max burst requests

## Recommended Sources for Borderlands Shift Codes

### Official Sources:
1. **Gearbox Twitter** ✅ (already configured)
2. **Borderlands Official Site** ✅ (already configured)
3. **2K Games Twitter**: `https://twitter.com/2K`
4. **Randy Pitchford Twitter**: `https://twitter.com/DuvalMagic`

### Community Sources:
1. **r/borderlands3** (configured but disabled)
2. **r/borderlands4** (add when available)
3. **r/Borderlands** (main subreddit)

### Gaming News:
1. **IGN Borderlands**: `https://www.ign.com/games/borderlands`
2. **GameSpot**: `https://www.gamespot.com/`
3. **PC Gamer**: `https://www.pcgamer.com/`

## Reddit API Setup (Required for Reddit Sources)

To enable Reddit sources, you need to:

1. **Create Reddit App**: https://www.reddit.com/prefs/apps
2. **Get Credentials**: Client ID and Client Secret
3. **Add to GitHub Secrets**:
   - `REDDIT_CLIENT_ID`
   - `REDDIT_CLIENT_SECRET`

## Testing Sources

After adding sources, test with:
```bash
python main.py --run-once --config config/production.json
```