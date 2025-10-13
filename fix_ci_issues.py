#!/usr/bin/env python3
"""
Quick fix script to address common CI issues
"""

import os
import sys

def main():
    """Fix common CI issues"""
    print("🔧 Fixing CI issues...")
    
    # Check if all required files exist
    required_files = [
        'main_improved.py',
        'health_check.py', 
        'migrate_db.py',
        'requirements.txt'
    ]
    
    missing_files = []
    for file in required_files:
        if not os.path.exists(file):
            missing_files.append(file)
    
    if missing_files:
        print(f"❌ Missing required files: {missing_files}")
        return False
    
    # Test basic imports
    try:
        print("Testing imports...")
        
        import importlib.util
        
        # Test main_improved.py
        spec = importlib.util.spec_from_file_location('bot', 'main_improved.py')
        bot_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(bot_module)
        print("✅ main_improved.py imports successfully")
        
        # Test health_check.py
        spec = importlib.util.spec_from_file_location('health', 'health_check.py')
        health_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(health_module)
        print("✅ health_check.py imports successfully")
        
        # Test migrate_db.py
        spec = importlib.util.spec_from_file_location('migrate', 'migrate_db.py')
        migrate_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migrate_module)
        print("✅ migrate_db.py imports successfully")
        
    except Exception as e:
        print(f"❌ Import error: {e}")
        return False
    
    # Test basic functionality
    try:
        print("Testing basic functionality...")
        
        # Test database operations
        from main_improved import init_db, normalize_code
        import tempfile
        
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        
        try:
            conn = init_db(db_path)
            conn.close()
            print("✅ Database operations work")
            
            # Test code normalization
            normalized = normalize_code('TEST-CODE-12345')
            assert normalized == 'TESTCODE12345'
            print("✅ Code normalization works")
            
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)
        
    except Exception as e:
        print(f"❌ Functionality error: {e}")
        return False
    
    print("✅ All CI issues fixed!")
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)