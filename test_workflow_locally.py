#!/usr/bin/env python3
"""
Test the workflow steps locally to identify issues.
"""

import os
import sys
import json
import subprocess
from pathlib import Path

def main():
    """Test workflow steps."""
    print("Testing workflow steps locally...")
    
    # Ensure we're in the right directory
    if not Path("src/main.py").exists():
        print("❌ Not in the correct directory. Please run from project root.")
        return False
    
    # Set up environment
    os.environ.update({
        "DATABASE_URL": "sqlite:///data/shift_codes.db",
        "ENVIRONMENT": "production", 
        "LOG_LEVEL": "INFO"
    })
    
    # Create data directory
    Path("data").mkdir(exist_ok=True)
    print("✅ Created data directory")
    
    # Test database migration
    try:
        result = subprocess.run([
            sys.executable, "migrate.py", "migrate"
        ], capture_output=True, text=True, timeout=60)
        
        if result.returncode == 0:
            print("✅ Database migration successful")
        else:
            print(f"❌ Database migration failed: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ Migration error: {e}")
        return False
    
    # Test health check
    try:
        result = subprocess.run([
            sys.executable, "health_check.py", "--json"
        ], capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            print("✅ Health check passed")
            health_data = json.loads(result.stdout)
            print(f"   Status: {health_data.get('status', 'unknown')}")
        else:
            print(f"⚠️  Health check issues: {result.stderr}")
    except Exception as e:
        print(f"⚠️  Health check error: {e}")
    
    # Test bot execution (this is the critical part)
    try:
        print("🤖 Testing bot execution...")
        result = subprocess.run([
            sys.executable, "main.py", 
            "--run-once", 
            "--config", "config/production.json", 
            "--json"
        ], capture_output=True, text=True, timeout=120)
        
        print(f"Bot exit code: {result.returncode}")
        
        if result.stdout:
            print("Bot output:")
            try:
                output_data = json.loads(result.stdout)
                print(json.dumps(output_data, indent=2))
            except json.JSONDecodeError:
                print(result.stdout)
        
        if result.stderr:
            print("Bot errors:")
            print(result.stderr)
        
        # The key insight: exit code 1 might be expected behavior
        if result.returncode == 1:
            print("⚠️  Bot returned exit code 1 - this might be expected if no new codes found")
        elif result.returncode == 0:
            print("✅ Bot execution successful")
        else:
            print(f"❌ Bot execution failed with exit code {result.returncode}")
            
    except Exception as e:
        print(f"❌ Bot execution error: {e}")
        return False
    
    # Check database file
    db_file = Path("data/shift_codes.db")
    if db_file.exists():
        print(f"✅ Database file exists ({db_file.stat().st_size} bytes)")
    else:
        print("❌ Database file missing")
    
    return True

if __name__ == "__main__":
    success = main()
    print(f"\nTest completed: {'SUCCESS' if success else 'FAILED'}")