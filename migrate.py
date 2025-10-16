#!/usr/bin/env python3
"""
Database migration CLI tool for the Shift Code Bot.
"""

import argparse
import sys
import json
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from storage.database import Database
from storage.migration_system import MigrationEngine
from storage.migrations import MigrationManager


def setup_database(database_url: str) -> Database:
    """Setup database connection."""
    database = Database(database_url)
    return database


def migrate_command(args):
    """Run migrations."""
    database = setup_database(args.database_url)
    engine = MigrationEngine(database)
    
    print(f"Running migrations to version: {args.target or 'latest'}")
    
    result = engine.migrate(args.target)
    
    if result["success"]:
        print(f"✅ Migration completed successfully")
        print(f"Applied {len(result['migrations_applied'])} migrations")
        
        for migration in result["migrations_applied"]:
            status = "✅" if migration["success"] else "❌"
            print(f"  {status} {migration['version']}: {migration['name']} ({migration['execution_time_ms']:.2f}ms)")
    else:
        print(f"❌ Migration failed")
        for error in result["errors"]:
            print(f"  Error: {error}")
        sys.exit(1)


def rollback_command(args):
    """Rollback migrations."""
    database = setup_database(args.database_url)
    engine = MigrationEngine(database)
    
    print(f"Rolling back to version: {args.target}")
    
    result = engine.rollback(args.target)
    
    if result["success"]:
        print(f"✅ Rollback completed successfully")
        print(f"Rolled back {len(result['migrations_rolled_back'])} migrations")
        
        for migration in result["migrations_rolled_back"]:
            status = "✅" if migration["success"] else "❌"
            print(f"  {status} {migration['version']}: {migration['name']} ({migration['execution_time_ms']:.2f}ms)")
    else:
        print(f"❌ Rollback failed")
        for error in result["errors"]:
            print(f"  Error: {error}")
        sys.exit(1)


def status_command(args):
    """Show migration status."""
    database = setup_database(args.database_url)
    engine = MigrationEngine(database)
    
    status = engine.get_migration_status()
    
    print(f"Migration Status:")
    print(f"  Current Version: {status['current_version']}")
    print(f"  Latest Version:  {status['latest_version']}")
    print(f"  Applied:         {status['applied_count']}")
    print(f"  Pending:         {status['pending_count']}")
    
    if status["applied_migrations"]:
        print(f"\nApplied Migrations:")
        for migration in status["applied_migrations"]:
            rollback_indicator = " (rollback available)" if migration["rollback_available"] else ""
            status_indicator = "✅" if migration["success"] else "❌"
            print(f"  {status_indicator} {migration['version']}: {migration['name']}{rollback_indicator}")
    
    if status["pending_migrations"]:
        print(f"\nPending Migrations:")
        for migration in status["pending_migrations"]:
            rollback_indicator = " (rollback available)" if migration["rollback_available"] else ""
            print(f"  📋 {migration['version']}: {migration['name']}{rollback_indicator}")
    
    if args.json:
        print(f"\nJSON Output:")
        print(json.dumps(status, indent=2))


def migrate_from_old_command(args):
    """Migrate from old database format."""
    database = setup_database(args.database_url)
    
    # First run schema migrations
    engine = MigrationEngine(database)
    migrate_result = engine.migrate()
    
    if not migrate_result["success"]:
        print(f"❌ Schema migration failed")
        for error in migrate_result["errors"]:
            print(f"  Error: {error}")
        sys.exit(1)
    
    print(f"✅ Schema migration completed")
    
    # Then migrate data from old database
    if args.old_database:
        print(f"Migrating data from old database: {args.old_database}")
        
        migration_manager = MigrationManager(args.old_database, database)
        
        # Check if old database exists
        if not migration_manager.check_old_database_exists():
            print(f"❌ Old database not found: {args.old_database}")
            sys.exit(1)
        
        # Get old database info
        old_info = migration_manager.get_old_database_info()
        print(f"Old database info:")
        print(f"  Tables: {old_info.get('tables', [])}")
        print(f"  Codes: {old_info.get('code_count', 0)}")
        print(f"  Size: {old_info.get('file_size', 0)} bytes")
        
        # Perform migration
        try:
            result = migration_manager.migrate_from_old_schema()
            
            print(f"✅ Data migration completed")
            print(f"  Codes migrated: {result['codes_migrated']}")
            print(f"  Sources created: {result['sources_created']}")
            
            if result["errors"]:
                print(f"⚠️  Warnings:")
                for error in result["errors"]:
                    print(f"    {error}")
        
        except Exception as e:
            print(f"❌ Data migration failed: {e}")
            sys.exit(1)
    
    print(f"✅ Migration from old database completed successfully")


def create_migration_command(args):
    """Create a new migration template."""
    migration_name = args.name.replace(" ", "_").lower()
    
    # Find next version number
    database = setup_database(args.database_url)
    engine = MigrationEngine(database)
    
    status = engine.get_migration_status()
    current_version = int(status["latest_version"])
    next_version = f"{current_version + 1:03d}"
    
    class_name = "".join(word.capitalize() for word in migration_name.split("_"))
    
    template = f'''"""
Migration: {migration_name}
"""

from storage.migration_system import Migration
import sqlite3


class {class_name}(Migration):
    """TODO: Describe what this migration does."""
    
    def __init__(self):
        super().__init__("{next_version}", "{migration_name}")
    
    def up(self, connection: sqlite3.Connection) -> None:
        """Apply the migration."""
        # TODO: Implement migration logic
        pass
    
    def down(self, connection: sqlite3.Connection) -> None:
        """Rollback the migration."""
        # TODO: Implement rollback logic (optional)
        raise NotImplementedError("Rollback not implemented")
'''
    
    migration_file = Path(f"src/storage/migrations/migration_{next_version}_{migration_name}.py")
    migration_file.parent.mkdir(parents=True, exist_ok=True)
    
    migration_file.write_text(template)
    
    print(f"✅ Created migration: {migration_file}")
    print(f"   Version: {next_version}")
    print(f"   Name: {migration_name}")
    print(f"\nDon't forget to:")
    print(f"1. Implement the up() method")
    print(f"2. Optionally implement the down() method for rollback support")
    print(f"3. Register the migration in MigrationEngine._register_migrations()")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="Database migration tool for Shift Code Bot")
    parser.add_argument(
        "--database-url",
        default="sqlite:///shift_codes.db",
        help="Database URL (default: sqlite:///shift_codes.db)"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Migrate command
    migrate_parser = subparsers.add_parser("migrate", help="Run pending migrations")
    migrate_parser.add_argument("--target", help="Target migration version")
    migrate_parser.set_defaults(func=migrate_command)
    
    # Rollback command
    rollback_parser = subparsers.add_parser("rollback", help="Rollback migrations")
    rollback_parser.add_argument("target", help="Target migration version to rollback to")
    rollback_parser.set_defaults(func=rollback_command)
    
    # Status command
    status_parser = subparsers.add_parser("status", help="Show migration status")
    status_parser.add_argument("--json", action="store_true", help="Output as JSON")
    status_parser.set_defaults(func=status_command)
    
    # Migrate from old command
    migrate_old_parser = subparsers.add_parser("migrate-from-old", help="Migrate from old database format")
    migrate_old_parser.add_argument("--old-database", help="Path to old database file")
    migrate_old_parser.set_defaults(func=migrate_from_old_command)
    
    # Create migration command
    create_parser = subparsers.add_parser("create", help="Create new migration template")
    create_parser.add_argument("name", help="Migration name")
    create_parser.set_defaults(func=create_migration_command)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    try:
        args.func(args)
    except KeyboardInterrupt:
        print("\n❌ Operation cancelled")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()