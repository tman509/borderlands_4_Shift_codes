#!/usr/bin/env python3
"""
Health check script for Borderlands 4 SHiFT Code Bot
Can be used for monitoring and alerting
"""

import json
import os
import sys
import sqlite3
import requests
from datetime import datetime, timezone
from typing import Dict

def check_database(db_path: str = "./shift_codes.db") -> Dict:
    """Check database connectivity and basic stats."""

    if not os.path.exists(db_path):
        return {
            "status": "warning",
            "error": "Database file not found",
            "total_codes": 0,
            "active_codes": 0,
            "last_code_date": None,
        }

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Test basic connectivity
        cursor.execute("SELECT 1")

        # Get stats
        cursor.execute("SELECT COUNT(*) FROM codes")
        total_codes = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM codes WHERE is_active = 1")
        active_codes = cursor.fetchone()[0]

        cursor.execute("SELECT MAX(date_found_utc) FROM codes")
        last_code_date = cursor.fetchone()[0]

        conn.close()

        return {
            "status": "healthy",
            "total_codes": total_codes,
            "active_codes": active_codes,
            "last_code_date": last_code_date,
        }
    except sqlite3.OperationalError as exc:
        # Missing tables or other schema problems should be surfaced as warnings so
        # the workflow can continue while still reporting the issue.
        return {
            "status": "warning",
            "error": str(exc),
            "total_codes": 0,
            "active_codes": 0,
            "last_code_date": None,
        }
    except Exception as exc:  # pragma: no cover - unexpected failure
        return {
            "status": "unhealthy",
            "error": str(exc),
        }

def check_network() -> Dict:
    """Check network connectivity."""
    try:
        # Test basic internet connectivity
        response = requests.get("https://httpbin.org/status/200", timeout=10)
        response.raise_for_status()

        # Test shift.gearboxsoftware.com
        response = requests.get("https://shift.gearboxsoftware.com", timeout=10)
        shift_status = "reachable" if response.status_code < 500 else "degraded"
        
        return {
            "status": "healthy",
            "internet": "ok",
            "shift_site": shift_status
        }
    except requests.RequestException as exc:
        # GitHub Actions environments occasionally restrict outbound network
        # access. Treat this as a warning so the workflow completes while still
        # flagging the degraded state.
        return {
            "status": "warning",
            "error": str(exc),
        }
    except Exception as exc:  # pragma: no cover - unexpected failure
        return {
            "status": "unhealthy",
            "error": str(exc),
        }

def check_configuration() -> Dict:
    """Check configuration validity."""
    try:
        from dotenv import load_dotenv

        load_dotenv()

        issues = []

        # Check required sources
        html_sources = [u.strip() for u in os.getenv("HTML_SOURCES", "").split(",") if u.strip()]
        reddit_configured = all([
            os.getenv("REDDIT_CLIENT_ID", "").strip(),
            os.getenv("REDDIT_CLIENT_SECRET", "").strip(),
            os.getenv("REDDIT_SUBS", "").strip()
        ])
        
        if not html_sources and not reddit_configured:
            issues.append("No data sources configured")
        
        # Check webhook URLs
        discord_url = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
        slack_url = os.getenv("SLACK_WEBHOOK_URL", "").strip()
        
        if discord_url and not discord_url.startswith('http'):
            issues.append("Invalid Discord webhook URL")
        
        if slack_url and not slack_url.startswith('http'):
            issues.append("Invalid Slack webhook URL")
        
        if not discord_url and not slack_url:
            issues.append("No notification methods configured")
        
        return {
            "status": "healthy" if not issues else "warning",
            "html_sources": len(html_sources),
            "reddit_configured": reddit_configured,
            "discord_configured": bool(discord_url),
            "slack_configured": bool(slack_url),
            "issues": issues
        }
    except Exception as exc:
        return {
            "status": "unhealthy",
            "error": str(exc)
        }

def main():
    """Run comprehensive health check"""
    print("Borderlands 4 SHiFT Code Bot - Health Check")
    print("=" * 50)
    
    results = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "database": check_database(),
        "network": check_network(),
        "configuration": check_configuration()
    }
    
    # Determine overall status
    statuses = [results[key]["status"] for key in ["database", "network", "configuration"]]
    
    if "unhealthy" in statuses:
        overall_status = "unhealthy"
        exit_code = 2
    elif "warning" in statuses:
        overall_status = "warning"
        # Warnings should still allow the workflow to succeed so we return a
        # success exit code while surfacing the degraded status in the report.
        exit_code = 0
    else:
        overall_status = "healthy"
        exit_code = 0
    
    results["overall_status"] = overall_status
    
    # Print results
    print(f"Overall Status: {overall_status.upper()}")
    print()
    
    for component, result in results.items():
        if component in ["timestamp", "overall_status"]:
            continue
        
        print(f"{component.title()}:")
        print(f"  Status: {result['status']}")
        
        if result["status"] == "unhealthy":
            print(f"  Error: {result.get('error', 'Unknown error')}")
        elif component == "database":
            print(f"  Total codes: {result.get('total_codes', 0)}")
            print(f"  Active codes: {result.get('active_codes', 0)}")
            if result.get('last_code_date'):
                print(f"  Last code: {result['last_code_date']}")
        elif component == "configuration":
            print(f"  HTML sources: {result.get('html_sources', 0)}")
            print(f"  Reddit: {'Yes' if result.get('reddit_configured') else 'No'}")
            print(f"  Discord: {'Yes' if result.get('discord_configured') else 'No'}")
            print(f"  Slack: {'Yes' if result.get('slack_configured') else 'No'}")
            if result.get('issues'):
                print(f"  Issues: {', '.join(result['issues'])}")
        
        print()
    
    # Output JSON for programmatic use
    if "--json" in sys.argv:
        print(json.dumps(results, indent=2))
    
    sys.exit(exit_code)

if __name__ == "__main__":
    main()
