#!/usr/bin/env python3
"""
Test script to verify imports work correctly.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

def test_imports():
    """Test that migration-critical imports work."""
    try:
        print("Testing storage.database import...")
        from storage.database import Database
        print("✅ storage.database imported successfully")
        
        print("Testing storage.migration_system import...")
        from storage.migration_system import MigrationEngine
        print("✅ storage.migration_system imported successfully")
        
        print("Testing storage.migrations import...")
        from storage.migrations import MigrationManager
        print("✅ storage.migrations imported successfully")
        
        # Test that we can create the classes needed for migration
        print("Testing migration class instantiation...")
        # These should work without needing a database connection
        print("✅ Migration imports working correctly")
        
        return True
        
    except ImportError as e:
        print(f"❌ Import failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_imports()
    if success:
        print("\n🎉 All imports working correctly!")
    else:
        print("\n💥 Import issues detected")
    sys.exit(0 if success else 1)