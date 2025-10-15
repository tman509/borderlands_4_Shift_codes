"""
Enhanced structured logging system with correlation IDs and contextual logging.
"""

import logging
import json
import uuid
import threading
from typing import Dict, Any, Optional, Union
from datetime import datetime, timezone
from contextvars import ContextVar
from functools import wraps

# Context variables for correlation tracking
correlation_id: ContextVar[Optional[str]] = ContextVar('correlation_id', default=None)
request_context: ContextVar[Dict[str, Any]] = ContextVar('request_context', default={})


class CorrelationIdFilter(logging.Filter):
    """Filter to add correlation ID to log records."""
    
    def filter(self, record):
        record.correlation_id = correlation_id.get() or 'none'
        
        # Add context information
        context = request_context.get()
        for key, value in context.items():
            setattr(record, f"ctx_{key}", value)
        
        return True


class EnhancedJSONFormatter(logging.Formatter):
    """Enhanced JSON formatter with structured fields and correlation tracking."""
    
    def __init__(self, include_extra_fields: bool = True):
        super().__init__()
        self.include_extra_fields = include_extra_fields
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as structured JSON."""
        
        # Base log entry
        log_entry = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "thread": record.thread,
            "thread_name": record.threadName,
            "process": record.process,
            "correlation_id": getattr(record, 'correlation_id', 'none')
        }
        
        # Add exception information if present
        if record.exc_info:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else None,
                "message": str(record.exc_info[1]) if record.exc_info[1] else None,
                "traceback": self.formatException(record.exc_info)
            }
        
        # Add stack info if present
        if record.stack_info:
            log_entry["stack_info"] = record.stack_info
        
        # Add extra fields from context
        if self.include_extra_fields:
            context_fields = {}
            for key, value in record.__dict__.items():
                if key.startswith('ctx_'):
                    context_fields[key[4:]] = value  # Remove 'ctx_' prefix
            
            if context_fields:
                log_entry["context"] = context_fields
        
        # Add custom fields (anything not in standard fields)
        standard_fields = {
            'name', 'msg', 'args', 'levelname', 'levelno', 'pathname',
            'filename', 'module', 'lineno', 'funcName', 'created',
            'msecs', 'relativeCreated', 'thread', 'threadName',
            'processName', 'process', 'getMessage', 'exc_info',
            'exc_text', 'stack_info', 'correlation_id'
        }
        
        extra_fields = {}
        for key, value in record.__dict__.items():
            if key not in standard_fields and not key.startswith('ctx_'):
                # Ensure value is JSON serializable
                try:
                    json.dumps(value)
                    extra_fields[key] = value
                except (TypeError, ValueError):
                    extra_fields[key] = str(value)
        
        if extra_fields:
            log_entry["extra"] = extra_fields
        
        return json.dumps(log_entry, ensure_ascii=False)


class ContextualLogger:
    """Logger wrapper that provides contextual logging with correlation IDs."""
    
    def __init__(self, logger: logging.Logger):
        self.logger = logger
    
    def with_context(self, **kwargs) -> 'ContextualLogger':
        """Create a new logger with additional context."""
        # Update the context for this logger instance
        current_context = request_context.get().copy()
        current_context.update(kwargs)
        
        # Create a new logger instance with updated context
        new_logger = ContextualLogger(self.logger)
        new_logger._context = current_context
        return new_logger
    
    def _log_with_context(self, level: int, msg: str, *args, **kwargs):
        """Log with current context."""
        # Set context if we have it
        if hasattr(self, '_context'):
            token = request_context.set(self._context)
            try:
                self.logger.log(level, msg, *args, **kwargs)
            finally:
                request_context.reset(token)
        else:
            self.logger.log(level, msg, *args, **kwargs)
    
    def debug(self, msg: str, *args, **kwargs):
        self._log_with_context(logging.DEBUG, msg, *args, **kwargs)
    
    def info(self, msg: str, *args, **kwargs):
        self._log_with_context(logging.INFO, msg, *args, **kwargs)
    
    def warning(self, msg: str, *args, **kwargs):
        self._log_with_context(logging.WARNING, msg, *args, **kwargs)
    
    def error(self, msg: str, *args, **kwargs):
        self._log_with_context(logging.ERROR, msg, *args, **kwargs)
    
    def critical(self, msg: str, *args, **kwargs):
        self._log_with_context(logging.CRITICAL, msg, *args, **kwargs)
    
    def exception(self, msg: str, *args, **kwargs):
        kwargs['exc_info'] = True
        self.error(msg, *args, **kwargs)


class LoggingManager:
    """Centralized logging management with correlation tracking."""
    
    def __init__(self):
        self.configured = False
        self.correlation_filter = CorrelationIdFilter()
    
    def setup_structured_logging(self,
                                level: str = "INFO",
                                format_type: str = "json",
                                log_file: Optional[str] = None,
                                include_extra_fields: bool = True) -> None:
        """Set up structured logging with correlation tracking."""
        
        # Configure formatters
        if format_type == "json":
            formatter = EnhancedJSONFormatter(include_extra_fields=include_extra_fields)
        else:
            formatter = logging.Formatter(
                fmt="%(asctime)s - %(correlation_id)s - %(name)s - %(levelname)s - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S"
            )
        
        # Configure handlers
        handlers = []
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(getattr(logging, level.upper()))
        console_handler.setFormatter(formatter)
        console_handler.addFilter(self.correlation_filter)
        handlers.append(console_handler)
        
        # File handler if specified
        if log_file:
            file_handler = logging.FileHandler(log_file, mode='a')
            file_handler.setLevel(getattr(logging, level.upper()))
            file_handler.setFormatter(formatter)
            file_handler.addFilter(self.correlation_filter)
            handlers.append(file_handler)
        
        # Configure root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(getattr(logging, level.upper()))
        
        # Remove existing handlers
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
        
        # Add new handlers
        for handler in handlers:
            root_logger.addHandler(handler)
        
        # Configure specific loggers to reduce noise
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        logging.getLogger("requests").setLevel(logging.WARNING)
        logging.getLogger("prawcore").setLevel(logging.WARNING)
        
        self.configured = True
        
        # Log configuration success
        logger = self.get_logger(__name__)
        logger.info("Structured logging configured", extra={
            "log_level": level,
            "format_type": format_type,
            "log_file": log_file,
            "include_extra_fields": include_extra_fields
        })
    
    def get_logger(self, name: str) -> ContextualLogger:
        """Get a contextual logger for the given name."""
        return ContextualLogger(logging.getLogger(name))
    
    def set_correlation_id(self, corr_id: Optional[str] = None) -> str:
        """Set correlation ID for current context."""
        if corr_id is None:
            corr_id = str(uuid.uuid4())
        
        correlation_id.set(corr_id)
        return corr_id
    
    def get_correlation_id(self) -> Optional[str]:
        """Get current correlation ID."""
        return correlation_id.get()
    
    def clear_correlation_id(self) -> None:
        """Clear correlation ID from current context."""
        correlation_id.set(None)
    
    def set_context(self, **kwargs) -> None:
        """Set context variables for logging."""
        current_context = request_context.get().copy()
        current_context.update(kwargs)
        request_context.set(current_context)
    
    def clear_context(self) -> None:
        """Clear all context variables."""
        request_context.set({})
    
    def get_context(self) -> Dict[str, Any]:
        """Get current context variables."""
        return request_context.get().copy()


# Global logging manager instance
logging_manager = LoggingManager()


def with_correlation_id(corr_id: Optional[str] = None):
    """Decorator to set correlation ID for function execution."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Set correlation ID
            old_corr_id = correlation_id.get()
            new_corr_id = corr_id or str(uuid.uuid4())
            correlation_id.set(new_corr_id)
            
            try:
                return func(*args, **kwargs)
            finally:
                # Restore old correlation ID
                correlation_id.set(old_corr_id)
        
        return wrapper
    return decorator


def with_logging_context(**context_kwargs):
    """Decorator to add context to function logging."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Set context
            old_context = request_context.get()
            new_context = old_context.copy()
            new_context.update(context_kwargs)
            
            # Add function info to context
            new_context.update({
                "function": func.__name__,
                "module": func.__module__
            })
            
            request_context.set(new_context)
            
            try:
                return func(*args, **kwargs)
            finally:
                # Restore old context
                request_context.set(old_context)
        
        return wrapper
    return decorator


def log_execution_time(logger: Optional[ContextualLogger] = None):
    """Decorator to log function execution time."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = datetime.now(timezone.utc)
            
            # Get logger
            if logger is None:
                log = logging_manager.get_logger(func.__module__)
            else:
                log = logger
            
            log.info(f"Starting execution of {func.__name__}")
            
            try:
                result = func(*args, **kwargs)
                
                # Calculate execution time
                end_time = datetime.now(timezone.utc)
                execution_time = (end_time - start_time).total_seconds()
                
                log.info(f"Completed execution of {func.__name__}", extra={
                    "execution_time_seconds": execution_time,
                    "function": func.__name__,
                    "success": True
                })
                
                return result
                
            except Exception as e:
                # Calculate execution time
                end_time = datetime.now(timezone.utc)
                execution_time = (end_time - start_time).total_seconds()
                
                log.error(f"Failed execution of {func.__name__}", extra={
                    "execution_time_seconds": execution_time,
                    "function": func.__name__,
                    "success": False,
                    "error": str(e)
                }, exc_info=True)
                
                raise
        
        return wrapper
    return decorator


class LoggingContext:
    """Context manager for logging with correlation ID and context."""
    
    def __init__(self, correlation_id: Optional[str] = None, **context):
        self.correlation_id = correlation_id or str(uuid.uuid4())
        self.context = context
        self.old_correlation_id = None
        self.old_context = None
    
    def __enter__(self):
        # Save old values
        self.old_correlation_id = correlation_id.get()
        self.old_context = request_context.get()
        
        # Set new values
        correlation_id.set(self.correlation_id)
        new_context = self.old_context.copy()
        new_context.update(self.context)
        request_context.set(new_context)
        
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        # Restore old values
        correlation_id.set(self.old_correlation_id)
        request_context.set(self.old_context)


# Convenience functions
def get_logger(name: str) -> ContextualLogger:
    """Get a contextual logger."""
    return logging_manager.get_logger(name)


def setup_logging(**kwargs) -> None:
    """Set up structured logging."""
    logging_manager.setup_structured_logging(**kwargs)


def new_correlation_id() -> str:
    """Generate and set a new correlation ID."""
    return logging_manager.set_correlation_id()


def logging_context(correlation_id: Optional[str] = None, **context) -> LoggingContext:
    """Create a logging context manager."""
    return LoggingContext(correlation_id, **context)