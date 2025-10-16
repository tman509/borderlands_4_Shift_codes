#!/usr/bin/env python3
"""
Minimal test script to verify migration imports work.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

def test_migration_imports():
    """Test only the imports needed for migration."""
    try:
        print("Testing minimal migration imports...")
        
        # Test database import
        import storage.database
        print("✅ storage.database module imported")
        
        # Test migration system import
        import storage.migration_system
        print("✅ storage.migration_system module imported")
        
        # Test migrations import
        import storage.migrations
        print("✅ storage.migrations module imported")
        
        # Test that we can access the classes
        Database = storage.database.Database
        MigrationEngine = storage.migration_system.MigrationEngine
        MigrationManager = storage.migrations.MigrationManager
        
        print("✅ All migration classes accessible")
        
        return True
        
    except Exception as e:
        print(f"❌ Migration import failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_migration_imports()
    if success:
        print("\n🎉 Migration imports working!")
    else:
        print("\n💥 Migration import issues detected")
    sys.exit(0 if success else 1)