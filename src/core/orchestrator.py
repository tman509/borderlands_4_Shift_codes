"""
Main orchestrator for the Shift Code Bot.
"""

import logging
from typing import List, Optional
from datetime import datetime, timezone

from ..models.config import Config
from ..models.content import RawContent
from ..models.code import ParsedCode
from .config_manager import ConfigManager

logger = logging.getLogger(__name__)


class Orchestrator:
    """Main orchestrator that coordinates all bot components."""
    
    def __init__(self, config_manager: ConfigManager):
        self.config_manager = config_manager
        self.config: Optional[Config] = None
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    def initialize(self) -> None:
        """Initialize the orchestrator and load configuration."""
        try:
            self.config = self.config_manager.load_config()
            self.logger.info("Orchestrator initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize orchestrator: {e}")
            raise
    
    def run_once(self) -> dict:
        """Execute one complete bot cycle."""
        if not self.config:
            raise RuntimeError("Orchestrator not initialized")
        
        start_time = datetime.now(timezone.utc)
        self.logger.info("Starting bot execution cycle")
        
        try:
            # Initialize metrics
            metrics = {
                "start_time": start_time.isoformat(),
                "sources_processed": 0,
                "codes_found": 0,
                "codes_processed": 0,
                "notifications_sent": 0,
                "errors": []
            }
            
            # Get enabled sources
            sources = self.config_manager.get_sources()
            self.logger.info(f"Processing {len(sources)} enabled sources")
            
            # Process each source
            all_parsed_codes = []
            for source in sources:
                try:
                    self.logger.info(f"Processing source: {source.name}")
                    
                    # TODO: Implement fetcher creation and content fetching
                    # fetcher = self._create_fetcher(source)
                    # raw_content = list(fetcher.fetch())
                    
                    # TODO: Implement code parsing
                    # parsed_codes = self._parse_codes(raw_content)
                    # all_parsed_codes.extend(parsed_codes)
                    
                    metrics["sources_processed"] += 1
                    
                except Exception as e:
                    error_msg = f"Error processing source {source.name}: {e}"
                    self.logger.error(error_msg)
                    metrics["errors"].append(error_msg)
            
            # TODO: Implement deduplication, validation, and notification
            
            # Calculate execution time
            end_time = datetime.now(timezone.utc)
            execution_time = (end_time - start_time).total_seconds()
            
            metrics.update({
                "end_time": end_time.isoformat(),
                "execution_time_seconds": execution_time,
                "codes_found": len(all_parsed_codes)
            })
            
            self.logger.info(f"Bot cycle completed in {execution_time:.2f}s")
            return metrics
            
        except Exception as e:
            self.logger.error(f"Bot execution failed: {e}")
            raise
    
    def health_check(self) -> dict:
        """Perform health check of all components."""
        health_status = {
            "status": "healthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "components": {}
        }
        
        try:
            # Check configuration
            if self.config:
                health_status["components"]["config"] = "ok"
            else:
                health_status["components"]["config"] = "not_loaded"
                health_status["status"] = "unhealthy"
            
            # TODO: Add more component health checks
            
        except Exception as e:
            health_status["status"] = "unhealthy"
            health_status["error"] = str(e)
        
        return health_status