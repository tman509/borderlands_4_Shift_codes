#!/usr/bin/env python3
"""
Main application entry point for the Shift Code Bot.
Integrates all components with proper dependency injection and lifecycle management.
"""

import sys
import os
import signal
import asyncio
import logging
import argparse
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone

# Ensure src is in path
sys.path.insert(0, str(Path(__file__).parent))

from core.config_manager import ConfigManager
from core.orchestrator import Orchestrator
from core.scheduler import Scheduler
from storage.database import Database
from storage.migration_system import MigrationEngine
from utils.logging_config import setup_logging
from utils.error_handling import error_handler
from utils.component_errors import ComponentErrorManager
from operations.maintenance import DatabaseMaintenance, PerformanceMonitor


class ShiftCodeBotApplication:
    """Main application class that manages the complete bot lifecycle."""
    
    def __init__(self, config_path: str, log_level: str = "INFO", log_format: str = "text"):
        self.config_path = config_path
        self.log_level = log_level
        self.log_format = log_format
        
        # Core components
        self.config_manager: Optional[ConfigManager] = None
        self.database: Optional[Database] = None
        self.orchestrator: Optional[Orchestrator] = None
        self.scheduler: Optional[Scheduler] = None
        self.error_manager: Optional[ComponentErrorManager] = None
        
        # State tracking
        self.initialized = False
        self.running = False
        self.shutdown_requested = False
        
        # Logger
        self.logger = logging.getLogger(__name__)
        
        # Setup signal handlers
        self._setup_signal_handlers()
    
    def _setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown."""
        def signal_handler(signum, frame):
            self.logger.info(f"Received signal {signum}, initiating graceful shutdown")
            self.shutdown_requested = True
            if self.running:
                self.stop()
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    def initialize(self) -> bool:
        """Initialize all application components in proper order."""
        try:
            self.logger.info("Initializing Shift Code Bot...")
            
            # 1. Setup logging
            setup_logging(
                level=self.log_level,
                format_type=self.log_format
            )
            
            # 2. Load configuration
            self.logger.info("Loading configuration...")
            self.config_manager = ConfigManager(self.config_path)
            config = self.config_manager.load_config()
            
            # 3. Initialize database
            self.logger.info("Initializing database...")
            self.database = Database(config.database_url)
            
            # 4. Run database migrations
            self.logger.info("Running database migrations...")
            migration_engine = MigrationEngine(self.database)
            migration_result = migration_engine.migrate()
            
            if not migration_result["success"]:
                self.logger.error(f"Database migration failed: {migration_result['errors']}")
                return False
            
            self.logger.info(f"Applied {len(migration_result['migrations_applied'])} migrations")
            
            # 5. Initialize error handling
            self.logger.info("Setting up error handling...")
            self.error_manager = ComponentErrorManager(error_handler)
            
            # 6. Initialize orchestrator
            self.logger.info("Initializing orchestrator...")
            self.orchestrator = Orchestrator(self.config_manager)
            self.orchestrator.initialize()
            
            # 7. Setup scheduler
            self.logger.info("Setting up scheduler...")
            self.scheduler = self.orchestrator.scheduler
            
            self.initialized = True
            self.logger.info("Shift Code Bot initialized successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to initialize application: {e}")
            return False
    
    def start(self) -> bool:
        """Start the bot in scheduled mode."""
        if not self.initialized:
            self.logger.error("Application not initialized")
            return False
        
        try:
            self.logger.info("Starting Shift Code Bot in scheduled mode...")
            
            # Start orchestrator
            self.orchestrator.start()
            
            self.running = True
            self.logger.info("Shift Code Bot started successfully")
            
            # Main loop
            self._run_main_loop()
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to start application: {e}")
            return False
    
    def _run_main_loop(self):
        """Main application loop."""
        self.logger.info("Entering main application loop...")
        
        try:
            while self.running and not self.shutdown_requested:
                # Check system health periodically
                if self.error_manager.should_pause_operations():
                    self.logger.warning("System health degraded, pausing operations")
                    recommendations = self.error_manager.get_recovery_recommendations()
                    for rec in recommendations:
                        self.logger.info(f"Recommendation: {rec}")
                    
                    # Wait before checking again
                    import time
                    time.sleep(60)
                    continue
                
                # Sleep and check for shutdown
                import time
                time.sleep(10)
                
        except KeyboardInterrupt:
            self.logger.info("Received keyboard interrupt")
            self.shutdown_requested = True
        except Exception as e:
            self.logger.error(f"Error in main loop: {e}")
        finally:
            self.stop()
    
    def stop(self):
        """Stop the bot gracefully."""
        if not self.running:
            return
        
        self.logger.info("Stopping Shift Code Bot...")
        
        try:
            # Stop orchestrator
            if self.orchestrator:
                self.orchestrator.stop()
            
            self.running = False
            self.logger.info("Shift Code Bot stopped successfully")
            
        except Exception as e:
            self.logger.error(f"Error during shutdown: {e}")
    
    def run_once(self) -> dict:
        """Run a single bot cycle."""
        if not self.initialized:
            raise RuntimeError("Application not initialized")
        
        self.logger.info("Running single bot cycle...")
        return self.orchestrator.run_once()
    
    def health_check(self) -> dict:
        """Perform comprehensive health check."""
        if not self.initialized:
            return {
                "status": "unhealthy",
                "error": "Application not initialized"
            }
        
        return self.orchestrator.health_check()
    
    def get_statistics(self) -> dict:
        """Get comprehensive system statistics."""
        if not self.initialized:
            return {"error": "Application not initialized"}
        
        stats = self.orchestrator.get_statistics()
        
        # Add application-level stats
        stats.update({
            "application": {
                "initialized": self.initialized,
                "running": self.running,
                "config_path": self.config_path,
                "log_level": self.log_level
            }
        })
        
        return stats
    
    def run_maintenance(self) -> dict:
        """Run maintenance operations."""
        if not self.initialized:
            return {"error": "Application not initialized"}
        
        self.logger.info("Running maintenance operations...")
        
        maintenance = DatabaseMaintenance(self.database)
        results = []
        
        # Run cleanup operations
        results.append(maintenance.cleanup_expired_codes())
        results.append(maintenance.cleanup_old_metrics())
        results.append(maintenance.cleanup_old_crawl_history())
        results.append(maintenance.vacuum_database())
        results.append(maintenance.analyze_database())
        
        successful = sum(1 for r in results if r.success)
        
        self.logger.info(f"Maintenance completed: {successful}/{len(results)} operations successful")
        
        return {
            "operations": len(results),
            "successful": successful,
            "results": [
                {
                    "operation": r.operation,
                    "success": r.success,
                    "records_affected": r.records_affected,
                    "execution_time_ms": r.execution_time_ms,
                    "error_message": r.error_message
                }
                for r in results
            ]
        }


def create_argument_parser() -> argparse.ArgumentParser:
    """Create command line argument parser."""
    parser = argparse.ArgumentParser(
        description="Shift Code Bot - Automated Borderlands Shift Code Discovery and Notification",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                          # Run in scheduled mode
  %(prog)s --run-once              # Run single cycle
  %(prog)s --health-check          # Check system health
  %(prog)s --maintenance           # Run maintenance operations
  %(prog)s --config prod.json      # Use specific config file
        """
    )
    
    # Configuration options
    parser.add_argument(
        "--config",
        default="config/production.json",
        help="Path to configuration file (default: config/production.json)"
    )
    
    # Logging options
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level (default: INFO)"
    )
    parser.add_argument(
        "--log-format",
        default="text",
        choices=["json", "text"],
        help="Log format (default: text)"
    )
    
    # Operation modes
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--run-once",
        action="store_true",
        help="Run single bot cycle and exit"
    )
    mode_group.add_argument(
        "--health-check",
        action="store_true",
        help="Perform health check and exit"
    )
    mode_group.add_argument(
        "--maintenance",
        action="store_true",
        help="Run maintenance operations and exit"
    )
    mode_group.add_argument(
        "--statistics",
        action="store_true",
        help="Show system statistics and exit"
    )
    
    # Output options
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON"
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress non-essential output"
    )
    
    return parser


def main():
    """Main entry point."""
    parser = create_argument_parser()
    args = parser.parse_args()
    
    # Adjust log level for quiet mode
    log_level = "WARNING" if args.quiet else args.log_level
    
    # Create application
    app = ShiftCodeBotApplication(
        config_path=args.config,
        log_level=log_level,
        log_format=args.log_format
    )
    
    # Initialize application
    if not app.initialize():
        print("Failed to initialize application", file=sys.stderr)
        sys.exit(1)
    
    try:
        if args.health_check:
            # Health check mode
            health = app.health_check()
            
            if args.json:
                import json
                print(json.dumps(health, indent=2))
            else:
                status = health["status"]
                print(f"Health Status: {status.upper()}")
                
                if status != "healthy":
                    print("Issues found:")
                    for component, details in health.get("components", {}).items():
                        if isinstance(details, dict) and details.get("status") != "ok":
                            error = details.get("error", "Unknown error")
                            print(f"  {component}: {error}")
            
            sys.exit(0 if health["status"] == "healthy" else 1)
        
        elif args.run_once:
            # Single run mode
            if not args.quiet:
                print("Running single bot cycle...")
            
            metrics = app.run_once()
            
            if args.json:
                import json
                print(json.dumps(metrics, indent=2))
            else:
                print(f"Execution completed:")
                print(f"  Sources processed: {metrics.get('sources_processed', 0)}")
                print(f"  New codes: {metrics.get('new_codes', 0)}")
                print(f"  Notifications sent: {metrics.get('notifications_sent', 0)}")
                print(f"  Execution time: {metrics.get('execution_time_seconds', 0):.2f}s")
                
                if metrics.get('errors'):
                    print(f"  Errors: {len(metrics['errors'])}")
                    for error in metrics['errors']:
                        print(f"    - {error}")
            
            # Exit successfully after single run (even if there were errors)
            # Errors in single run mode are typically expected (no new codes, etc.)
            sys.exit(0)
        
        elif args.maintenance:
            # Maintenance mode
            if not args.quiet:
                print("Running maintenance operations...")
            
            result = app.run_maintenance()
            
            if args.json:
                import json
                print(json.dumps(result, indent=2))
            else:
                print(f"Maintenance completed: {result['successful']}/{result['operations']} operations successful")
                
                for op_result in result['results']:
                    status = "✅" if op_result['success'] else "❌"
                    print(f"  {status} {op_result['operation']}: {op_result['records_affected']} records ({op_result['execution_time_ms']:.2f}ms)")
                    
                    if not op_result['success'] and op_result['error_message']:
                        print(f"    Error: {op_result['error_message']}")
        
        elif args.statistics:
            # Statistics mode
            stats = app.get_statistics()
            
            if args.json:
                import json
                print(json.dumps(stats, indent=2))
            else:
                print("System Statistics:")
                print(f"  Running: {stats['running']}")
                print(f"  Database Size: {stats.get('database', {}).get('database_size_mb', 0)}MB")
                print(f"  Total Codes: {stats.get('codes', {}).get('total', 0)}")
                print(f"  Active Jobs: {stats.get('scheduler', {}).get('enabled_jobs', 0)}")
        
        else:
            # Scheduled mode (default)
            if not args.quiet:
                print("Starting Shift Code Bot in scheduled mode...")
                print("Press Ctrl+C to stop")
            
            success = app.start()
            sys.exit(0 if success else 1)
    
    except KeyboardInterrupt:
        if not args.quiet:
            print("\nShutdown requested by user")
        sys.exit(0)
    except Exception as e:
        print(f"Application error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()