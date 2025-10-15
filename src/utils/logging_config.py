"""
Logging configuration for the Shift Code Bot.
"""

import logging
import logging.config
import json
import sys
from typing import Dict, Any


class JSONFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging."""
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_entry = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno
        }
        
        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        
        # Add extra fields
        for key, value in record.__dict__.items():
            if key not in {
                'name', 'msg', 'args', 'levelname', 'levelno', 'pathname',
                'filename', 'module', 'lineno', 'funcName', 'created',
                'msecs', 'relativeCreated', 'thread', 'threadName',
                'processName', 'process', 'getMessage', 'exc_info',
                'exc_text', 'stack_info'
            }:
                log_entry[key] = value
        
        return json.dumps(log_entry)


def setup_logging(
    level: str = "INFO",
    format_type: str = "json",
    log_file: str = None
) -> None:
    """
    Set up logging configuration.
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        format_type: Format type ("json" or "text")
        log_file: Optional log file path
    """
    
    # Configure formatters
    formatters = {
        "json": {
            "()": JSONFormatter,
        },
        "text": {
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S"
        }
    }
    
    # Configure handlers
    handlers = {
        "console": {
            "class": "logging.StreamHandler",
            "level": level,
            "formatter": format_type,
            "stream": sys.stdout
        }
    }
    
    # Add file handler if log file specified
    if log_file:
        handlers["file"] = {
            "class": "logging.FileHandler",
            "level": level,
            "formatter": format_type,
            "filename": log_file,
            "mode": "a"
        }
    
    # Configure root logger
    root_config = {
        "level": level,
        "handlers": list(handlers.keys())
    }
    
    # Build logging configuration
    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": formatters,
        "handlers": handlers,
        "root": root_config,
        "loggers": {
            # Reduce noise from external libraries
            "urllib3": {"level": "WARNING"},
            "requests": {"level": "WARNING"},
            "prawcore": {"level": "WARNING"},
        }
    }
    
    # Apply configuration
    logging.config.dictConfig(config)
    
    # Log configuration success
    logger = logging.getLogger(__name__)
    logger.info(f"Logging configured: level={level}, format={format_type}")
    if log_file:
        logger.info(f"Log file: {log_file}")