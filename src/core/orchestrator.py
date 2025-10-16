"""
Main orchestrator for the Shift Code Bot.
"""

import logging
import signal
import sys
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from contextlib import contextmanager

from models.config import Config
from models.content import RawContent
from models.code import ParsedCode, CodeStatus
from storage.database import Database
from storage.repositories import (
    CodeRepository, SourceRepository, AnnouncementRepository,
    CrawlHistoryRepository, MetricsRepository
)
from fetchers.base import BaseFetcher
from fetchers.html_fetcher import HtmlFetcher
from fetchers.rss_fetcher import RssFetcher
from fetchers.reddit_fetcher import RedditFetcher
from processing.parser import CodeParser
from processing.validator import CodeValidator
from processing.deduplication import DeduplicationEngine
from processing.batch_processor import BatchProcessor
from notifications.discord_notifier import DiscordNotifier
from notifications.queue import NotificationQueue
from monitoring.metrics_collector import MetricsCollector
from monitoring.health_monitor import HealthMonitor
from monitoring.alerting import AlertManager
from .config_manager import ConfigManager
from .scheduler import Scheduler, ScheduledJob, CronExpressions

logger = logging.getLogger(__name__)


class Orchestrator:
    """Main orchestrator that coordinates all bot components."""
    
    def __init__(self, config_manager: ConfigManager):
        self.config_manager = config_manager
        self.config: Optional[Config] = None
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        
        # Core components
        self.database: Optional[Database] = None
        self.scheduler: Optional[Scheduler] = None
        
        # Repositories
        self.code_repository: Optional[CodeRepository] = None
        self.source_repository: Optional[SourceRepository] = None
        self.announcement_repository: Optional[AnnouncementRepository] = None
        self.crawl_history_repository: Optional[CrawlHistoryRepository] = None
        self.metrics_repository: Optional[MetricsRepository] = None
        
        # Processing components
        self.code_parser: Optional[CodeParser] = None
        self.code_validator: Optional[CodeValidator] = None
        self.deduplication_engine: Optional[DeduplicationEngine] = None
        self.batch_processor: Optional[BatchProcessor] = None
        
        # Notification components
        self.discord_notifier: Optional[DiscordNotifier] = None
        self.notification_queue: Optional[NotificationQueue] = None
        
        # Monitoring components
        self.metrics_collector: Optional[MetricsCollector] = None
        self.health_monitor: Optional[HealthMonitor] = None
        self.alert_manager: Optional[AlertManager] = None
        
        # State tracking
        self.running = False
        self.initialized = False
        self.shutdown_requested = False
        
        # Setup signal handlers for graceful shutdown
        self._setup_signal_handlers()
    
    def _setup_signal_handlers(self) -> None:
        """Setup signal handlers for graceful shutdown."""
        def signal_handler(signum, frame):
            self.logger.info(f"Received signal {signum}, initiating graceful shutdown")
            self.shutdown_requested = True
            self.stop()
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    def initialize(self) -> None:
        """Initialize the orchestrator and all components."""
        try:
            self.logger.info("Initializing orchestrator...")
            
            # Load configuration
            self.config = self.config_manager.load_config()
            
            # Initialize database
            self._initialize_database()
            
            # Initialize repositories
            self._initialize_repositories()
            
            # Initialize processing components
            self._initialize_processing_components()
            
            # Initialize notification components
            self._initialize_notification_components()
            
            # Initialize monitoring components
            self._initialize_monitoring_components()
            
            # Initialize scheduler
            self._initialize_scheduler()
            
            self.initialized = True
            self.logger.info("Orchestrator initialized successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize orchestrator: {e}")
            raise
    
    def _initialize_database(self) -> None:
        """Initialize database connection and schema."""
        self.database = Database(self.config.database_url)
        self.database.initialize_schema()
        self.logger.info("Database initialized")
    
    def _initialize_repositories(self) -> None:
        """Initialize all repository instances."""
        self.code_repository = CodeRepository(self.database)
        self.source_repository = SourceRepository(self.database)
        self.announcement_repository = AnnouncementRepository(self.database)
        self.crawl_history_repository = CrawlHistoryRepository(self.database)
        self.metrics_repository = MetricsRepository(self.database)
        self.logger.info("Repositories initialized")
    
    def _initialize_processing_components(self) -> None:
        """Initialize code processing components."""
        self.code_parser = CodeParser()
        self.code_validator = CodeValidator()
        self.deduplication_engine = DeduplicationEngine(self.code_repository)
        self.batch_processor = BatchProcessor(
            self.code_repository,
            self.deduplication_engine
        )
        self.logger.info("Processing components initialized")
    
    def _initialize_notification_components(self) -> None:
        """Initialize notification components."""
        self.notification_queue = NotificationQueue()
        self.discord_notifier = DiscordNotifier(
            self.config.discord_channels,
            self.notification_queue
        )
        self.logger.info("Notification components initialized")
    
    def _initialize_monitoring_components(self) -> None:
        """Initialize monitoring and alerting components."""
        self.metrics_collector = MetricsCollector(self.metrics_repository)
        self.health_monitor = HealthMonitor()
        self.alert_manager = AlertManager(
            self.config.observability_config.alert_webhook_url
        )
        self.logger.info("Monitoring components initialized")
    
    def _initialize_scheduler(self) -> None:
        """Initialize scheduler and setup jobs."""
        self.scheduler = Scheduler()
        
        # Create main crawl job
        main_job = ScheduledJob(
            id="main_crawl",
            name="Main Crawl Job",
            cron_expression=self.config.scheduler_config.cron_schedule,
            callback=self.run_once,
            max_execution_time=self.config.scheduler_config.max_execution_time
        )
        
        self.scheduler.add_job(main_job)
        
        # Create maintenance jobs
        self._setup_maintenance_jobs()
        
        self.logger.info("Scheduler initialized")
    
    def _setup_maintenance_jobs(self) -> None:
        """Setup maintenance and cleanup jobs."""
        # Expired codes cleanup job
        cleanup_job = ScheduledJob(
            id="cleanup_expired",
            name="Cleanup Expired Codes",
            cron_expression=CronExpressions.EVERY_HOUR,
            callback=self._cleanup_expired_codes,
            max_execution_time=60
        )
        self.scheduler.add_job(cleanup_job)
        
        # Health check job
        health_job = ScheduledJob(
            id="health_check",
            name="System Health Check",
            cron_expression=CronExpressions.EVERY_15_MINUTES,
            callback=self._perform_health_check,
            max_execution_time=30
        )
        self.scheduler.add_job(health_job)
        
        # Metrics collection job
        metrics_job = ScheduledJob(
            id="collect_metrics",
            name="Collect System Metrics",
            cron_expression=CronExpressions.EVERY_5_MINUTES,
            callback=self._collect_system_metrics,
            max_execution_time=30
        )
        self.scheduler.add_job(metrics_job)
    
    def run_once(self) -> Dict[str, Any]:
        """Execute one complete bot cycle."""
        if not self.initialized:
            raise RuntimeError("Orchestrator not initialized")
        
        start_time = datetime.now(timezone.utc)
        self.logger.info("Starting bot execution cycle")
        
        # Initialize execution metrics
        execution_metrics = {
            "start_time": start_time.isoformat(),
            "sources_processed": 0,
            "codes_found": 0,
            "new_codes": 0,
            "duplicate_codes": 0,
            "notifications_sent": 0,
            "errors": [],
            "execution_id": f"exec_{int(start_time.timestamp())}"
        }
        
        try:
            # Record metrics start
            self.metrics_collector.record_execution_start(execution_metrics["execution_id"])
            
            # Get enabled sources
            sources = self.source_repository.get_enabled_sources()
            self.logger.info(f"Processing {len(sources)} enabled sources")
            
            all_raw_content = []
            all_parsed_codes = []
            
            # Process each source
            for source in sources:
                source_start_time = datetime.now(timezone.utc)
                crawl_id = None
                
                try:
                    self.logger.info(f"Processing source: {source.name}")
                    
                    # Start crawl tracking
                    crawl_id = self.crawl_history_repository.start_crawl(source.id)
                    
                    # Create appropriate fetcher
                    fetcher = self._create_fetcher(source)
                    if not fetcher:
                        raise ValueError(f"No fetcher available for source type: {source.type}")
                    
                    # Fetch content
                    raw_content_list = list(fetcher.fetch())
                    all_raw_content.extend(raw_content_list)
                    
                    # Parse codes from content
                    source_codes = []
                    for raw_content in raw_content_list:
                        parsed_codes = self._parse_codes(raw_content)
                        source_codes.extend(parsed_codes)
                    
                    all_parsed_codes.extend(source_codes)
                    
                    # Update source crawl info
                    if raw_content_list:
                        latest_hash = raw_content_list[-1].content_hash
                        self.source_repository.update_crawl_info(source.id, latest_hash)
                    
                    # Complete crawl tracking
                    if crawl_id:
                        self.crawl_history_repository.complete_crawl(crawl_id, len(source_codes))
                    
                    execution_metrics["sources_processed"] += 1
                    execution_metrics["codes_found"] += len(source_codes)
                    
                    self.logger.info(f"Source {source.name}: found {len(source_codes)} codes")
                    
                except Exception as e:
                    error_msg = f"Error processing source {source.name}: {e}"
                    self.logger.error(error_msg)
                    execution_metrics["errors"].append(error_msg)
                    
                    # Complete crawl with error
                    if crawl_id:
                        self.crawl_history_repository.complete_crawl(crawl_id, 0, str(e))
                    
                    # Record error metric
                    self.metrics_collector.record_source_error(source.id, str(e))
                
                finally:
                    # Clean up fetcher resources
                    if 'fetcher' in locals():
                        fetcher.cleanup()
            
            # Process all found codes
            if all_parsed_codes:
                processing_result = self._process_codes(all_parsed_codes)
                execution_metrics.update(processing_result)
            
            # Send notifications for new codes
            if execution_metrics["new_codes"] > 0:
                notification_result = self._send_notifications()
                execution_metrics["notifications_sent"] = notification_result.get("sent", 0)
            
            # Calculate execution time
            end_time = datetime.now(timezone.utc)
            execution_time = (end_time - start_time).total_seconds()
            
            execution_metrics.update({
                "end_time": end_time.isoformat(),
                "execution_time_seconds": execution_time,
                "success": True
            })
            
            # Record successful execution
            self.metrics_collector.record_execution_complete(
                execution_metrics["execution_id"],
                execution_time,
                execution_metrics["new_codes"]
            )
            
            self.logger.info(
                f"Bot cycle completed in {execution_time:.2f}s: "
                f"{execution_metrics['new_codes']} new codes, "
                f"{execution_metrics['notifications_sent']} notifications sent"
            )
            
            return execution_metrics
            
        except Exception as e:
            # Record failed execution
            execution_metrics["success"] = False
            execution_metrics["error"] = str(e)
            
            self.metrics_collector.record_execution_error(
                execution_metrics["execution_id"],
                str(e)
            )
            
            self.logger.error(f"Bot execution failed: {e}")
            
            # Send alert for critical failures
            self.alert_manager.send_alert(
                "Bot Execution Failed",
                f"Critical error in bot execution: {e}",
                severity="critical"
            )
            
            raise
    
    def _create_fetcher(self, source_config) -> Optional[BaseFetcher]:
        """Create appropriate fetcher for source type."""
        try:
            if source_config.type.value == "html":
                return HtmlFetcher(source_config)
            elif source_config.type.value == "rss":
                return RssFetcher(source_config)
            elif source_config.type.value == "reddit":
                return RedditFetcher(source_config)
            else:
                self.logger.error(f"Unknown source type: {source_config.type}")
                return None
        except Exception as e:
            self.logger.error(f"Failed to create fetcher for {source_config.name}: {e}")
            return None
    
    def _parse_codes(self, raw_content: RawContent) -> List[ParsedCode]:
        """Parse codes from raw content."""
        try:
            parse_result = self.code_parser.parse_codes(raw_content)
            
            # Validate parsed codes
            valid_codes = []
            for code in parse_result.codes_found:
                if self.code_validator.validate_code(code):
                    valid_codes.append(code)
                else:
                    self.logger.debug(f"Invalid code filtered out: {code.code_display}")
            
            return valid_codes
            
        except Exception as e:
            self.logger.error(f"Failed to parse codes from {raw_content.url}: {e}")
            return []
    
    def _process_codes(self, parsed_codes: List[ParsedCode]) -> Dict[str, Any]:
        """Process parsed codes through deduplication and storage."""
        try:
            result = self.batch_processor.process_codes(parsed_codes)
            
            return {
                "new_codes": result.get("new_codes", 0),
                "duplicate_codes": result.get("duplicates", 0),
                "updated_codes": result.get("updates", 0)
            }
            
        except Exception as e:
            self.logger.error(f"Failed to process codes: {e}")
            return {"new_codes": 0, "duplicate_codes": 0, "updated_codes": 0}
    
    def _send_notifications(self) -> Dict[str, Any]:
        """Send notifications for new codes."""
        try:
            # Get new codes that need notification
            new_codes = self.code_repository.get_codes_by_status(CodeStatus.NEW)
            
            if not new_codes:
                return {"sent": 0}
            
            # Queue notifications
            notifications_queued = 0
            for code in new_codes:
                for channel_config in self.config.discord_channels:
                    if self._should_notify_channel(code, channel_config):
                        self.notification_queue.queue_code_notification(code, channel_config.id)
                        notifications_queued += 1
            
            # Process notification queue
            sent_count = self.discord_notifier.process_queue()
            
            return {"sent": sent_count, "queued": notifications_queued}
            
        except Exception as e:
            self.logger.error(f"Failed to send notifications: {e}")
            return {"sent": 0}
    
    def _should_notify_channel(self, code: ParsedCode, channel_config) -> bool:
        """Determine if a code should be sent to a specific channel."""
        # Check if already announced to this channel
        if self.announcement_repository.announcement_exists(code.id, channel_config.id):
            return False
        
        # Check source filters
        if channel_config.source_filters:
            source = self.source_repository.get_source_by_id(code.source_id)
            if source and source.name not in channel_config.source_filters:
                return False
        
        return True
    
    def _cleanup_expired_codes(self) -> Dict[str, Any]:
        """Cleanup expired codes maintenance job."""
        try:
            expired_count = self.code_repository.mark_codes_as_expired()
            self.logger.info(f"Marked {expired_count} codes as expired")
            return {"expired_codes": expired_count}
        except Exception as e:
            self.logger.error(f"Failed to cleanup expired codes: {e}")
            return {"error": str(e)}
    
    def _perform_health_check(self) -> Dict[str, Any]:
        """Perform system health check maintenance job."""
        try:
            health_status = self.health_check()
            
            # Send alerts for unhealthy components
            if health_status["status"] != "healthy":
                self.alert_manager.send_alert(
                    "System Health Alert",
                    f"System health check failed: {health_status}",
                    severity="warning"
                )
            
            return health_status
        except Exception as e:
            self.logger.error(f"Health check failed: {e}")
            return {"error": str(e)}
    
    def _collect_system_metrics(self) -> Dict[str, Any]:
        """Collect system metrics maintenance job."""
        try:
            # Collect various system metrics
            metrics = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "database_stats": self.database.get_stats(),
                "scheduler_stats": self.scheduler.get_statistics() if self.scheduler else {},
                "notification_queue_size": self.notification_queue.size() if self.notification_queue else 0
            }
            
            # Record metrics
            for metric_name, value in metrics.items():
                if isinstance(value, (int, float)):
                    self.metrics_collector.record_metric(metric_name, value)
            
            return metrics
        except Exception as e:
            self.logger.error(f"Failed to collect metrics: {e}")
            return {"error": str(e)}
    
    def start(self) -> None:
        """Start the orchestrator and scheduler."""
        if not self.initialized:
            raise RuntimeError("Orchestrator not initialized")
        
        if self.running:
            self.logger.warning("Orchestrator is already running")
            return
        
        try:
            self.logger.info("Starting orchestrator...")
            
            # Start scheduler
            self.scheduler.start()
            
            # Start notification processing
            self.notification_queue.start()
            
            # Start health monitoring
            self.health_monitor.start()
            
            self.running = True
            self.logger.info("Orchestrator started successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to start orchestrator: {e}")
            raise
    
    def stop(self) -> None:
        """Stop the orchestrator and all components."""
        if not self.running:
            return
        
        self.logger.info("Stopping orchestrator...")
        
        try:
            # Stop scheduler
            if self.scheduler:
                self.scheduler.stop()
            
            # Stop notification processing
            if self.notification_queue:
                self.notification_queue.stop()
            
            # Stop health monitoring
            if self.health_monitor:
                self.health_monitor.stop()
            
            self.running = False
            self.logger.info("Orchestrator stopped successfully")
            
        except Exception as e:
            self.logger.error(f"Error stopping orchestrator: {e}")
    
    def run_manual_crawl(self) -> Dict[str, Any]:
        """Manually trigger a crawl cycle."""
        self.logger.info("Manual crawl triggered")
        return self.run_once()
    
    def health_check(self) -> Dict[str, Any]:
        """Perform comprehensive health check of all components."""
        health_status = {
            "status": "healthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "components": {},
            "overall_health": True
        }
        
        try:
            # Check configuration
            health_status["components"]["config"] = {
                "status": "ok" if self.config else "not_loaded",
                "sources_count": len(self.config.sources) if self.config else 0,
                "channels_count": len(self.config.discord_channels) if self.config else 0
            }
            
            # Check database
            if self.database:
                db_health = self.database.health_check()
                health_status["components"]["database"] = db_health
                if db_health["status"] != "healthy":
                    health_status["overall_health"] = False
            
            # Check scheduler
            if self.scheduler:
                scheduler_health = self.scheduler.health_check()
                health_status["components"]["scheduler"] = scheduler_health
                if scheduler_health["status"] not in ["healthy", "stopped"]:
                    health_status["overall_health"] = False
            
            # Check notification queue
            if self.notification_queue:
                queue_health = self.notification_queue.health_check()
                health_status["components"]["notification_queue"] = queue_health
            
            # Check fetchers for each source
            if self.config:
                fetcher_health = {}
                for source in self.config.sources[:5]:  # Check first 5 sources
                    try:
                        fetcher = self._create_fetcher(source)
                        if fetcher:
                            fetcher_health[source.name] = fetcher.health_check()
                        else:
                            fetcher_health[source.name] = {"status": "failed", "error": "Could not create fetcher"}
                    except Exception as e:
                        fetcher_health[source.name] = {"status": "failed", "error": str(e)}
                
                health_status["components"]["fetchers"] = fetcher_health
            
            # Set overall status
            if not health_status["overall_health"]:
                health_status["status"] = "unhealthy"
            elif not self.running:
                health_status["status"] = "stopped"
            
        except Exception as e:
            health_status["status"] = "error"
            health_status["error"] = str(e)
            health_status["overall_health"] = False
        
        return health_status
    
    @contextmanager
    def _execution_context(self, execution_id: str):
        """Context manager for tracking execution lifecycle."""
        try:
            self.logger.debug(f"Starting execution context: {execution_id}")
            yield
        except Exception as e:
            self.logger.error(f"Error in execution context {execution_id}: {e}")
            raise
        finally:
            self.logger.debug(f"Ending execution context: {execution_id}")
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get comprehensive system statistics."""
        stats = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "running": self.running,
            "initialized": self.initialized
        }
        
        try:
            if self.database:
                stats["database"] = self.database.get_stats()
            
            if self.scheduler:
                stats["scheduler"] = self.scheduler.get_statistics()
            
            if self.code_repository:
                stats["codes"] = self.code_repository.get_code_stats()
            
            if self.crawl_history_repository:
                stats["crawls"] = self.crawl_history_repository.get_crawl_stats()
            
        except Exception as e:
            stats["error"] = str(e)
        
        return stats