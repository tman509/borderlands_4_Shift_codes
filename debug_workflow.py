#!/usr/bin/env python3
"""
Debug script to help troubleshoot GitHub Actions workflow issues.
This script simulates the workflow steps locally to identify problems.
"""

import os
import sys
import json
import subprocess
from pathlib import Path

def run_command(cmd, description, continue_on_error=False):
    """Run a command and return the result."""
    print(f"\n{'='*50}")
    print(f"Running: {description}")
    print(f"Command: {cmd}")
    print(f"{'='*50}")
    
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )
        
        print(f"Exit code: {result.returncode}")
        
        if result.stdout:
            print("STDOUT:")
            print(result.stdout)
        
        if result.stderr:
            print("STDERR:")
            print(result.stderr)
        
        if result.returncode != 0 and not continue_on_error:
            print(f"❌ Command failed with exit code {result.returncode}")
            return False
        else:
            print("✅ Command completed successfully")
            return True
            
    except subprocess.TimeoutExpired:
        print("❌ Command timed out")
        return False
    except Exception as e:
        print(f"❌ Command failed with exception: {e}")
        return False

def check_environment():
    """Check the environment setup."""
    print("🔍 Checking environment...")
    
    # Check Python version
    print(f"Python version: {sys.version}")
    
    # Check current directory
    print(f"Current directory: {os.getcwd()}")
    
    # Check if key files exist
    key_files = [
        "main.py",
        "src/main.py",
        "migrate.py",
        "health_check.py",
        "requirements.txt",
        "config/production.json"
    ]
    
    for file_path in key_files:
        if Path(file_path).exists():
            print(f"✅ {file_path} exists")
        else:
            print(f"❌ {file_path} missing")
    
    # Check data directory
    data_dir = Path("data")
    if data_dir.exists():
        print(f"✅ data/ directory exists")
        db_file = data_dir / "shift_codes.db"
        if db_file.exists():
            print(f"✅ Database file exists ({db_file.stat().st_size} bytes)")
        else:
            print(f"⚠️  Database file does not exist")
    else:
        print(f"⚠️  data/ directory does not exist")

def main():
    """Main debug function."""
    print("🚀 Starting workflow debug simulation...")
    
    # Check environment
    check_environment()
    
    # Set environment variables (simulate GitHub Actions)
    os.environ.update({
        "DATABASE_URL": "sqlite:///data/shift_codes.db",
        "ENVIRONMENT": "production",
        "LOG_LEVEL": "INFO"
    })
    
    # Step 1: Create data directory
    if not run_command("mkdir -p data", "Create data directory"):
        return False
    
    # Step 2: Check if database exists
    db_exists = Path("data/shift_codes.db").exists()
    print(f"\n📊 Database exists: {db_exists}")
    
    # Step 3: Run migrations
    if not run_command("python migrate.py migrate", "Run database migrations"):
        return False
    
    # Step 4: Run health check
    if not run_command("python health_check.py --json", "Run health check", continue_on_error=True):
        print("⚠️  Health check had issues, but continuing...")
    
    # Step 5: Run bot (single cycle)
    if not run_command("python main.py --run-once --config config/production.json --json", "Run bot single cycle", continue_on_error=True):
        print("⚠️  Bot execution had issues")
    
    # Step 6: Final health check
    if not run_command("python health_check.py --json", "Final health check", continue_on_error=True):
        print("⚠️  Final health check had issues")
    
    # Check final database state
    db_file = Path("data/shift_codes.db")
    if db_file.exists():
        print(f"\n✅ Final database size: {db_file.stat().st_size} bytes")
    else:
        print(f"\n❌ Database file missing after execution")
    
    print("\n🏁 Debug simulation completed!")
    return True

if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n⚠️  Debug interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Debug failed with error: {e}")
        sys.exit(1)