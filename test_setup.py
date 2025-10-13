#!/usr/bin/env python3
"""
Simple test script to verify the bot setup works
Run this locally before pushing to GitHub
"""

import sys
import os

def test_imports():
    """Test that all modules can be imported"""
    print("🧪 Testing imports...")
    
    try:
        # Test standard library
        import sqlite3
        import json
        import time
        import logging
        print("✅ Standard library imports OK")
        
        # Test external dependencies
        import requests
        from bs4 import BeautifulSoup
        from dotenv import load_dotenv
        print("✅ External dependencies OK")
        
        # Test our modules
        import main_improved
        print("✅ main_improved.py imports OK")
        
        import health_check
        print("✅ health_check.py imports OK")
        
        import migrate_db
        print("✅ migrate_db.py imports OK")
        
        return True
        
    except Exception as e:
        print(f"❌ Import failed: {e}")
        return False

def test_database():
    """Test basic database functionality"""
    print("\n🗄️ Testing database...")
    
    try:
        from main_improved import init_db, normalize_code
        import tempfile
        
        # Create temporary database
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        
        try:
            # Test database initialization
            conn = init_db(db_path)
            print("✅ Database initialization OK")
            
            # Test code normalization
            normalized = normalize_code('TEST-CODE-12345')
            assert normalized == 'TESTCODE12345'
            print("✅ Code normalization OK")
            
            conn.close()
            return True
            
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)
                
    except Exception as e:
        print(f"❌ Database test failed: {e}")
        return False

def test_health_check():
    """Test health check functionality"""
    print("\n🏥 Testing health check...")
    
    try:
        from health_check import check_configuration
        
        # Set minimal environment
        os.environ['HTML_SOURCES'] = 'https://example.com'
        
        result = check_configuration()
        assert 'status' in result
        print("✅ Health check OK")
        
        return True
        
    except Exception as e:
        print(f"❌ Health check failed: {e}")
        return False

def main():
    """Run all tests"""
    print("🚀 Testing Borderlands 4 SHiFT Bot Setup")
    print("=" * 50)
    
    tests = [
        ("Imports", test_imports),
        ("Database", test_database),
        ("Health Check", test_health_check)
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            success = test_func()
            results.append((test_name, success))
        except Exception as e:
            print(f"❌ {test_name} test crashed: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "=" * 50)
    print("📊 Test Results Summary:")
    
    all_passed = True
    for test_name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"  {test_name}: {status}")
        if not success:
            all_passed = False
    
    if all_passed:
        print("\n🎉 All tests passed! Your setup is ready for GitHub Actions.")
        return 0
    else:
        print("\n⚠️ Some tests failed. Please fix the issues before deploying.")
        return 1

if __name__ == "__main__":
    sys.exit(main())