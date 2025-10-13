#!/usr/bin/env python3
"""
Health check script for Borderlands 4 SHiFT Code Bot
Can be used for monitoring and alerting
"""

import json
import sys
import sqlite3
import requests
from datetime import datetime, timezone
from typing import Dict

def check_database(db_path: str = "./shift_codes.db") -> Dict:
    """Check database connectivity and basic stats"""
    try:
        import os
        if not os.path.exists(db_path):
            return {
                "status": "warning",
                "error": f"Database file not found at {db_path}",
                "total_codes": 0,
                "active_codes": 0,
                "last_code_date": None
            }
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Test basic connectivity
        cursor.execute("SELECT 1")
        
        # Check if codes table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='codes'")
        if not cursor.fetchone():
            conn.close()
            return {
                "status": "warning",
                "error": "Database exists but codes table not found",
                "total_codes": 0,
                "active_codes": 0,
                "last_code_date": None
            }
        
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
            "last_code_date": last_code_date
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }

def check_network() -> Dict:
    """Check network connectivity"""
    try:
        # Test basic internet connectivity with shorter timeout
        response = requests.get("https://httpbin.org/status/200", timeout=5)
        response.raise_for_status()
        
        # Test shift.gearboxsoftware.com with shorter timeout
        try:
            response = requests.get("https://shift.gearboxsoftware.com", timeout=5)
            shift_status = "reachable" if response.status_code < 500 else "degraded"
        except requests.exceptions.Timeout:
            shift_status = "timeout"
        except Exception:
            shift_status = "unreachable"
        
        return {
            "status": "healthy",
            "internet": "ok",
            "shift_site": shift_status
        }
    except requests.exceptions.Timeout:
        return {
            "status": "warning",
            "error": "Network timeout - connection may be slow"
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }

def check_configuration() -> Dict:
    """Check configuration validity"""
    try:
        import os
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            # python-dotenv not available, skip loading .env file
            pass
        
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
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
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
        exit_code = 1
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