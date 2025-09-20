# Borderlands 4 SHiFT Code Bot

Tracks new SHiFT codes, dedupes against a SQLite DB, infers the reward, and sends notifications to Discord/Slack.

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Fill .env, then:
python main.py
```

## Docker

```bash
docker build -t bl4-shift-bot .
docker run --rm -v $PWD/.env:/app/.env bl4-shift-bot
```

## Scheduling

Example cron (every 15 minutes):

```
*/15 * * * * cd /path/to/repo && /path/to/repo/.venv/bin/python main.py >> bot.log 2>&1
```

## Environment

See `.env.example`. Do **not** commit your real `.env`.

## GitHub Actions (optional)

This repo includes a basic CI workflow that runs a lint and a dry-run import test.
