#!/usr/bin/env python3
"""
Main entry point for the Shift Code Bot.
"""

import sys
import os
import argparse
import logging
from pathlib import Path

# Add src directory to Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.core.config_manager import ConfigManager
from src.core.orchestrator import Orchestrator
from src.utils.logging_config import setup_logging


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Shift Code Bot")
    parser.add_argument(
        "--config", 
        default="config.json",
        help="Path to configuration file"
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level"
    )
    parser.add_argument(
        "--log-format",
        default="text",
        choices=["json", "text"],
        help="Log format"
    )
    parser.add_argument(
        "--log-file",
        help="Log file path (optional)"
    )
    parser.add_argument(
        "--health-check",
        action="store_true",
        help="Perform health check and exit"
    )
    
    args = parser.parse_args()
    
    # Set up logging
    setup_logging(
        level=args.log_level,
        format_type=args.log_format,
        log_file=args.log_file
    )
    
    logger = logging.getLogger(__name__)
    
    try:
        # Initialize components
        config_manager = ConfigManager(args.config)
        orchestrator = Orchestrator(config_manager)
        orchestrator.initialize()
        
        if args.health_check:
            # Perform health check
            health = orchestrator.health_check()
            print(f"Health Status: {health['status']}")
            if health["status"] != "healthy":
                sys.exit(1)
            return
        
        # Run bot cycle
        logger.info("=" * 50)
        logger.info("Shift Code Bot Starting")
        logger.info("=" * 50)
        
        metrics = orchestrator.run_once()
        
        logger.info("=" * 50)
        logger.info("Execution Summary:")
        logger.info(f"  Sources processed: {metrics['sources_processed']}")
        logger.info(f"  Codes found: {metrics['codes_found']}")
        logger.info(f"  Execution time: {metrics['execution_time_seconds']:.2f}s")
        if metrics['errors']:
            logger.warning(f"  Errors: {len(metrics['errors'])}")
        logger.info("=" * 50)
        
    except KeyboardInterrupt:
        logger.info("Bot execution interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Bot execution failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()