#!/usr/bin/env python3
"""
Maintenance CLI tool for the Shift Code Bot.
"""

import argparse
import sys
import json
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from storage.database import Database
from operations.maintenance import DatabaseMaintenance, PerformanceMonitor, BackupManager


def setup_database(database_url: str) -> Database:
    """Setup database connection."""
    database = Database(database_url)
    return database


def cleanup_command(args):
    """Run cleanup operations."""
    database = setup_database(args.database_url)
    maintenance = DatabaseMaintenance(database)
    
    results = []
    
    if args.expired_codes or args.all:
        print("🧹 Cleaning up expired codes...")
        result = maintenance.cleanup_expired_codes(args.days_old)
        results.append(result)
        
        if result.success:
            print(f"✅ Cleaned up {result.records_affected} expired codes ({result.execution_time_ms:.2f}ms)")
        else:
            print(f"❌ Failed to cleanup expired codes: {result.error_message}")
    
    if args.old_metrics or args.all:
        print("🧹 Cleaning up old metrics...")
        result = maintenance.cleanup_old_metrics(args.metrics_days)
        results.append(result)
        
        if result.success:
            print(f"✅ Cleaned up {result.records_affected} old metrics ({result.execution_time_ms:.2f}ms)")
        else:
            print(f"❌ Failed to cleanup old metrics: {result.error_message}")
    
    if args.crawl_history or args.all:
        print("🧹 Cleaning up old crawl history...")
        result = maintenance.cleanup_old_crawl_history(args.crawl_days)
        results.append(result)
        
        if result.success:
            print(f"✅ Cleaned up {result.records_affected} crawl history records ({result.execution_time_ms:.2f}ms)")
        else:
            print(f"❌ Failed to cleanup crawl history: {result.error_message}")
    
    if args.vacuum or args.all:
        print("🗜️  Vacuuming database...")
        result = maintenance.vacuum_database()
        results.append(result)
        
        if result.success:
            space_mb = result.details["space_reclaimed_bytes"] / (1024 * 1024)
            print(f"✅ Database vacuumed, reclaimed {space_mb:.2f}MB ({result.execution_time_ms:.2f}ms)")
        else:
            print(f"❌ Failed to vacuum database: {result.error_message}")
    
    if args.analyze or args.all:
        print("📊 Analyzing database...")
        result = maintenance.analyze_database()
        results.append(result)
        
        if result.success:
            print(f"✅ Database analyzed ({result.execution_time_ms:.2f}ms)")
        else:
            print(f"❌ Failed to analyze database: {result.error_message}")
    
    # Summary
    successful = sum(1 for r in results if r.success)
    total = len(results)
    
    print(f"\n📋 Maintenance Summary: {successful}/{total} operations successful")
    
    if args.json:
        print("\nJSON Output:")
        print(json.dumps([
            {
                "operation": r.operation,
                "success": r.success,
                "records_affected": r.records_affected,
                "execution_time_ms": r.execution_time_ms,
                "details": r.details,
                "error_message": r.error_message
            }
            for r in results
        ], indent=2))


def check_command(args):
    """Run database integrity check."""
    database = setup_database(args.database_url)
    maintenance = DatabaseMaintenance(database)
    
    print("🔍 Checking database integrity...")
    
    result = maintenance.check_database_integrity()
    
    if result.success:
        print(f"✅ Database integrity check passed ({result.execution_time_ms:.2f}ms)")
    else:
        print(f"❌ Database integrity issues found:")
        for issue in result.details.get("issues", []):
            print(f"  - {issue}")
        print(f"Execution time: {result.execution_time_ms:.2f}ms")
    
    if args.json:
        print("\nJSON Output:")
        print(json.dumps({
            "success": result.success,
            "execution_time_ms": result.execution_time_ms,
            "details": result.details,
            "error_message": result.error_message
        }, indent=2))


def report_command(args):
    """Generate performance report."""
    database = setup_database(args.database_url)
    monitor = PerformanceMonitor(database)
    
    print(f"📊 Generating performance report for last {args.hours} hours...")
    
    report = monitor.get_performance_report(args.hours)
    
    if "error" in report:
        print(f"❌ Failed to generate report: {report['error']}")
        sys.exit(1)
    
    # Display summary
    print(f"\n📈 Performance Report Summary:")
    print(f"  Time Period: {args.hours} hours")
    print(f"  Database Size: {report['database_stats']['database_size_mb']}MB")
    print(f"  Total Codes: {report['database_stats']['codes_count']}")
    print(f"  Total Crawls: {report['crawl_performance']['total_crawls']}")
    print(f"  Crawl Success Rate: {report['crawl_performance']['success_rate']:.2%}")
    print(f"  New Codes Discovered: {report['code_discovery']['new_codes_discovered']}")
    
    if args.detailed:
        print(f"\n📋 Detailed Statistics:")
        
        # Database stats
        print(f"\nDatabase Statistics:")
        for key, value in report['database_stats'].items():
            print(f"  {key}: {value}")
        
        # Crawl performance
        print(f"\nCrawl Performance:")
        for key, value in report['crawl_performance'].items():
            print(f"  {key}: {value}")
        
        # Code discovery
        print(f"\nCode Discovery:")
        for key, value in report['code_discovery'].items():
            if isinstance(value, dict):
                print(f"  {key}:")
                for subkey, subvalue in value.items():
                    print(f"    {subkey}: {subvalue}")
            else:
                print(f"  {key}: {value}")
        
        # System health
        print(f"\nSystem Health:")
        print(f"  Recent Errors: {report['system_health']['recent_errors']}")
        print(f"  Source Health:")
        for source, health in report['system_health']['source_health'].items():
            print(f"    {source}: {health['success_rate']:.2%} success rate ({health['crawl_count']} crawls)")
    
    if args.json:
        print(f"\nJSON Output:")
        print(json.dumps(report, indent=2))


def backup_command(args):
    """Create database backup."""
    database = setup_database(args.database_url)
    backup_manager = BackupManager(database)
    
    # Generate backup filename if not provided
    if not args.output:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        args.output = f"backup_shift_codes_{timestamp}.db"
    
    print(f"💾 Creating backup: {args.output}")
    
    result = backup_manager.create_backup(args.output)
    
    if result.success:
        size_mb = result.details["backup_size_bytes"] / (1024 * 1024)
        print(f"✅ Backup created successfully ({size_mb:.2f}MB, {result.execution_time_ms:.2f}ms)")
        print(f"   Backup file: {args.output}")
    else:
        print(f"❌ Backup failed: {result.error_message}")
        sys.exit(1)


def restore_command(args):
    """Restore database from backup."""
    database = setup_database(args.database_url)
    backup_manager = BackupManager(database)
    
    if not Path(args.backup_file).exists():
        print(f"❌ Backup file not found: {args.backup_file}")
        sys.exit(1)
    
    if not args.force:
        response = input(f"⚠️  This will overwrite the current database. Continue? (y/N): ")
        if response.lower() != 'y':
            print("❌ Restore cancelled")
            sys.exit(1)
    
    print(f"📥 Restoring from backup: {args.backup_file}")
    
    result = backup_manager.restore_backup(args.backup_file)
    
    if result.success:
        print(f"✅ Database restored successfully ({result.execution_time_ms:.2f}ms)")
        print(f"   Current database backed up to: {result.details['current_backup']}")
    else:
        print(f"❌ Restore failed: {result.error_message}")
        sys.exit(1)


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="Maintenance tool for Shift Code Bot")
    parser.add_argument(
        "--database-url",
        default="sqlite:///shift_codes.db",
        help="Database URL (default: sqlite:///shift_codes.db)"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Cleanup command
    cleanup_parser = subparsers.add_parser("cleanup", help="Run cleanup operations")
    cleanup_parser.add_argument("--expired-codes", action="store_true", help="Clean up expired codes")
    cleanup_parser.add_argument("--old-metrics", action="store_true", help="Clean up old metrics")
    cleanup_parser.add_argument("--crawl-history", action="store_true", help="Clean up old crawl history")
    cleanup_parser.add_argument("--vacuum", action="store_true", help="Vacuum database")
    cleanup_parser.add_argument("--analyze", action="store_true", help="Analyze database")
    cleanup_parser.add_argument("--all", action="store_true", help="Run all cleanup operations")
    cleanup_parser.add_argument("--days-old", type=int, default=30, help="Days old for expired codes cleanup")
    cleanup_parser.add_argument("--metrics-days", type=int, default=90, help="Days old for metrics cleanup")
    cleanup_parser.add_argument("--crawl-days", type=int, default=30, help="Days old for crawl history cleanup")
    cleanup_parser.add_argument("--json", action="store_true", help="Output as JSON")
    cleanup_parser.set_defaults(func=cleanup_command)
    
    # Check command
    check_parser = subparsers.add_parser("check", help="Check database integrity")
    check_parser.add_argument("--json", action="store_true", help="Output as JSON")
    check_parser.set_defaults(func=check_command)
    
    # Report command
    report_parser = subparsers.add_parser("report", help="Generate performance report")
    report_parser.add_argument("--hours", type=int, default=24, help="Hours to include in report")
    report_parser.add_argument("--detailed", action="store_true", help="Show detailed statistics")
    report_parser.add_argument("--json", action="store_true", help="Output as JSON")
    report_parser.set_defaults(func=report_command)
    
    # Backup command
    backup_parser = subparsers.add_parser("backup", help="Create database backup")
    backup_parser.add_argument("--output", help="Backup file path (auto-generated if not specified)")
    backup_parser.set_defaults(func=backup_command)
    
    # Restore command
    restore_parser = subparsers.add_parser("restore", help="Restore database from backup")
    restore_parser.add_argument("backup_file", help="Backup file to restore from")
    restore_parser.add_argument("--force", action="store_true", help="Skip confirmation prompt")
    restore_parser.set_defaults(func=restore_command)
    
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