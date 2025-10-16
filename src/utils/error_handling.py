"""
Comprehensive error handling system for the Shift Code Bot.
"""

import logging
import traceback
import sys
from typing import Dict, Any, Optional, List, Type, Callable, Union
from datetime import datetime, timezone
from dataclasses import dataclass, field
from enum import Enum
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class ErrorSeverity(Enum):
    """Error severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ErrorCategory(Enum):
    """Error categories for classification."""
    NETWORK = "network"
    PARSING = "parsing"
    DATABASE = "database"
    VALIDATION = "validation"
    CONFIGURATION = "configuration"
    AUTHENTICATION = "authentication"
    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    RESOURCE = "resource"
    BUSINESS_LOGIC = "business_logic"
    EXTERNAL_SERVICE = "external_service"
    UNKNOWN = "unknown"


@dataclass
class ErrorContext:
    """Context information for an error."""
    component: str
    operation: str
    source_id: Optional[int] = None
    source_name: Optional[str] = None
    url: Optional[str] = None
    user_data: Dict[str, Any] = field(default_factory=dict)
    system_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ErrorRecord:
    """Detailed error record for tracking and analysis."""
    id: str
    timestamp: datetime
    exception_type: str
    message: str
    severity: ErrorSeverity
    category: ErrorCategory
    context: ErrorContext
    traceback_str: str
    recovery_attempted: bool = False
    recovery_successful: bool = False
    recovery_actions: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert error record to dictionary."""
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "exception_type": self.exception_type,
            "message": self.message,
            "severity": self.severity.value,
            "category": self.category.value,
            "context": {
                "component": self.context.component,
                "operation": self.context.operation,
                "source_id": self.context.source_id,
                "source_name": self.context.source_name,
                "url": self.context.url,
                "user_data": self.context.user_data,
                "system_data": self.context.system_data
            },
            "traceback": self.traceback_str,
            "recovery_attempted": self.recovery_attempted,
            "recovery_successful": self.recovery_successful,
            "recovery_actions": self.recovery_actions,
            "metadata": self.metadata
        }


class ErrorClassifier:
    """Classifies errors into categories and determines severity."""
    
    # Exception type to category mapping
    EXCEPTION_CATEGORIES = {
        # Network errors
        'ConnectionError': ErrorCategory.NETWORK,
        'TimeoutError': ErrorCategory.TIMEOUT,
        'HTTPError': ErrorCategory.NETWORK,
        'RequestException': ErrorCategory.NETWORK,
        'URLError': ErrorCategory.NETWORK,
        
        # Database errors
        'DatabaseError': ErrorCategory.DATABASE,
        'IntegrityError': ErrorCategory.DATABASE,
        'OperationalError': ErrorCategory.DATABASE,
        'ProgrammingError': ErrorCategory.DATABASE,
        
        # Parsing errors
        'JSONDecodeError': ErrorCategory.PARSING,
        'XMLSyntaxError': ErrorCategory.PARSING,
        'ParserError': ErrorCategory.PARSING,
        'UnicodeDecodeError': ErrorCategory.PARSING,
        
        # Validation errors
        'ValidationError': ErrorCategory.VALIDATION,
        'ValueError': ErrorCategory.VALIDATION,
        'TypeError': ErrorCategory.VALIDATION,
        
        # Configuration errors
        'ConfigurationError': ErrorCategory.CONFIGURATION,
        'KeyError': ErrorCategory.CONFIGURATION,
        'AttributeError': ErrorCategory.CONFIGURATION,
        
        # Authentication errors
        'AuthenticationError': ErrorCategory.AUTHENTICATION,
        'PermissionError': ErrorCategory.AUTHENTICATION,
        'Forbidden': ErrorCategory.AUTHENTICATION,
        
        # Rate limiting
        'TooManyRequests': ErrorCategory.RATE_LIMIT,
        'RateLimitExceeded': ErrorCategory.RATE_LIMIT,
        
        # Resource errors
        'MemoryError': ErrorCategory.RESOURCE,
        'OSError': ErrorCategory.RESOURCE,
        'IOError': ErrorCategory.RESOURCE,
    }
    
    # Severity rules based on category and message patterns
    SEVERITY_RULES = {
        ErrorCategory.CRITICAL: [
            'database.*connection.*failed',
            'authentication.*failed',
            'configuration.*missing',
            'memory.*error',
            'disk.*full'
        ],
        ErrorCategory.HIGH: [
            'network.*timeout',
            'rate.*limit.*exceeded',
            'parsing.*failed',
            'validation.*error'
        ],
        ErrorCategory.MEDIUM: [
            'retry.*exhausted',
            'temporary.*failure',
            'service.*unavailable'
        ]
    }
    
    @classmethod
    def classify_error(cls, exception: Exception, context: ErrorContext) -> tuple[ErrorCategory, ErrorSeverity]:
        """Classify error into category and severity."""
        exception_name = type(exception).__name__
        message = str(exception).lower()
        
        # Determine category
        category = cls.EXCEPTION_CATEGORIES.get(exception_name, ErrorCategory.UNKNOWN)
        
        # Determine severity
        severity = ErrorSeverity.LOW  # Default
        
        # Check severity rules
        import re
        for sev_level, patterns in cls.SEVERITY_RULES.items():
            for pattern in patterns:
                if re.search(pattern, message):
                    if sev_level == ErrorCategory.CRITICAL:
                        severity = ErrorSeverity.CRITICAL
                    elif sev_level == ErrorCategory.HIGH and severity != ErrorSeverity.CRITICAL:
                        severity = ErrorSeverity.HIGH
                    elif sev_level == ErrorCategory.MEDIUM and severity == ErrorSeverity.LOW:
                        severity = ErrorSeverity.MEDIUM
        
        # Special cases based on context
        if context.component in ['database', 'config_manager']:
            if severity == ErrorSeverity.LOW:
                severity = ErrorSeverity.MEDIUM
        
        if 'critical' in message or 'fatal' in message:
            severity = ErrorSeverity.CRITICAL
        
        return category, severity


class ErrorRecoveryStrategy:
    """Base class for error recovery strategies."""
    
    def can_recover(self, error_record: ErrorRecord) -> bool:
        """Check if this strategy can recover from the error."""
        raise NotImplementedError
    
    def recover(self, error_record: ErrorRecord, context: Dict[str, Any]) -> bool:
        """Attempt to recover from the error."""
        raise NotImplementedError
    
    def get_name(self) -> str:
        """Get strategy name."""
        return self.__class__.__name__


class RetryRecoveryStrategy(ErrorRecoveryStrategy):
    """Recovery strategy that retries the operation."""
    
    def __init__(self, max_retries: int = 3, delay: float = 1.0):
        self.max_retries = max_retries
        self.delay = delay
    
    def can_recover(self, error_record: ErrorRecord) -> bool:
        """Check if retry is appropriate for this error."""
        transient_categories = {
            ErrorCategory.NETWORK,
            ErrorCategory.TIMEOUT,
            ErrorCategory.RATE_LIMIT,
            ErrorCategory.EXTERNAL_SERVICE
        }
        
        return (
            error_record.category in transient_categories and
            error_record.severity != ErrorSeverity.CRITICAL
        )
    
    def recover(self, error_record: ErrorRecord, context: Dict[str, Any]) -> bool:
        """Attempt recovery by retrying."""
        retry_func = context.get('retry_func')
        if not retry_func:
            return False
        
        try:
            import time
            time.sleep(self.delay)
            retry_func()
            return True
        except Exception:
            return False


class FallbackRecoveryStrategy(ErrorRecoveryStrategy):
    """Recovery strategy that uses fallback mechanisms."""
    
    def can_recover(self, error_record: ErrorRecord) -> bool:
        """Check if fallback is available."""
        return error_record.category in {
            ErrorCategory.PARSING,
            ErrorCategory.EXTERNAL_SERVICE,
            ErrorCategory.NETWORK
        }
    
    def recover(self, error_record: ErrorRecord, context: Dict[str, Any]) -> bool:
        """Attempt recovery using fallback."""
        fallback_func = context.get('fallback_func')
        if not fallback_func:
            return False
        
        try:
            fallback_func()
            return True
        except Exception:
            return False


class ResetRecoveryStrategy(ErrorRecoveryStrategy):
    """Recovery strategy that resets component state."""
    
    def can_recover(self, error_record: ErrorRecord) -> bool:
        """Check if reset is appropriate."""
        return error_record.category in {
            ErrorCategory.RESOURCE,
            ErrorCategory.CONFIGURATION
        }
    
    def recover(self, error_record: ErrorRecord, context: Dict[str, Any]) -> bool:
        """Attempt recovery by resetting state."""
        reset_func = context.get('reset_func')
        if not reset_func:
            return False
        
        try:
            reset_func()
            return True
        except Exception:
            return False


class ErrorHandler:
    """Comprehensive error handling system."""
    
    def __init__(self):
        self.error_records: List[ErrorRecord] = []
        self.recovery_strategies: List[ErrorRecoveryStrategy] = [
            RetryRecoveryStrategy(),
            FallbackRecoveryStrategy(),
            ResetRecoveryStrategy()
        ]
        self.error_callbacks: List[Callable[[ErrorRecord], None]] = []
        self.max_records = 1000  # Keep last 1000 error records
    
    def add_recovery_strategy(self, strategy: ErrorRecoveryStrategy) -> None:
        """Add a recovery strategy."""
        self.recovery_strategies.append(strategy)
    
    def add_error_callback(self, callback: Callable[[ErrorRecord], None]) -> None:
        """Add callback to be called on errors."""
        self.error_callbacks.append(callback)
    
    def handle_error(
        self,
        exception: Exception,
        context: ErrorContext,
        recovery_context: Optional[Dict[str, Any]] = None
    ) -> ErrorRecord:
        """Handle an error with classification and recovery attempts."""
        
        # Generate unique error ID
        error_id = f"err_{int(datetime.now(timezone.utc).timestamp())}_{id(exception)}"
        
        # Classify error
        category, severity = ErrorClassifier.classify_error(exception, context)
        
        # Create error record
        error_record = ErrorRecord(
            id=error_id,
            timestamp=datetime.now(timezone.utc),
            exception_type=type(exception).__name__,
            message=str(exception),
            severity=severity,
            category=category,
            context=context,
            traceback_str=traceback.format_exc()
        )
        
        # Log error
        self._log_error(error_record)
        
        # Attempt recovery
        if recovery_context:
            self._attempt_recovery(error_record, recovery_context)
        
        # Store error record
        self._store_error_record(error_record)
        
        # Call error callbacks
        for callback in self.error_callbacks:
            try:
                callback(error_record)
            except Exception as e:
                logger.warning(f"Error callback failed: {e}")
        
        return error_record
    
    def _log_error(self, error_record: ErrorRecord) -> None:
        """Log error with appropriate level."""
        log_message = (
            f"[{error_record.category.value.upper()}] "
            f"{error_record.context.component}.{error_record.context.operation}: "
            f"{error_record.message}"
        )
        
        if error_record.severity == ErrorSeverity.CRITICAL:
            logger.critical(log_message)
        elif error_record.severity == ErrorSeverity.HIGH:
            logger.error(log_message)
        elif error_record.severity == ErrorSeverity.MEDIUM:
            logger.warning(log_message)
        else:
            logger.info(log_message)
    
    def _attempt_recovery(self, error_record: ErrorRecord, recovery_context: Dict[str, Any]) -> None:
        """Attempt to recover from error using available strategies."""
        error_record.recovery_attempted = True
        
        for strategy in self.recovery_strategies:
            if strategy.can_recover(error_record):
                try:
                    logger.info(f"Attempting recovery with {strategy.get_name()}")
                    
                    if strategy.recover(error_record, recovery_context):
                        error_record.recovery_successful = True
                        error_record.recovery_actions.append(strategy.get_name())
                        logger.info(f"Recovery successful with {strategy.get_name()}")
                        break
                    else:
                        error_record.recovery_actions.append(f"{strategy.get_name()}_failed")
                        
                except Exception as e:
                    logger.warning(f"Recovery strategy {strategy.get_name()} failed: {e}")
                    error_record.recovery_actions.append(f"{strategy.get_name()}_error")
    
    def _store_error_record(self, error_record: ErrorRecord) -> None:
        """Store error record with size limit."""
        self.error_records.append(error_record)
        
        # Maintain size limit
        if len(self.error_records) > self.max_records:
            self.error_records = self.error_records[-self.max_records:]
    
    def get_error_statistics(self, hours: int = 24) -> Dict[str, Any]:
        """Get error statistics for the specified time period."""
        cutoff_time = datetime.now(timezone.utc) - datetime.timedelta(hours=hours)
        recent_errors = [
            err for err in self.error_records
            if err.timestamp > cutoff_time
        ]
        
        if not recent_errors:
            return {
                "total_errors": 0,
                "by_category": {},
                "by_severity": {},
                "by_component": {},
                "recovery_rate": 0.0
            }
        
        # Count by category
        by_category = {}
        for error in recent_errors:
            category = error.category.value
            by_category[category] = by_category.get(category, 0) + 1
        
        # Count by severity
        by_severity = {}
        for error in recent_errors:
            severity = error.severity.value
            by_severity[severity] = by_severity.get(severity, 0) + 1
        
        # Count by component
        by_component = {}
        for error in recent_errors:
            component = error.context.component
            by_component[component] = by_component.get(component, 0) + 1
        
        # Calculate recovery rate
        recovery_attempted = sum(1 for err in recent_errors if err.recovery_attempted)
        recovery_successful = sum(1 for err in recent_errors if err.recovery_successful)
        recovery_rate = recovery_successful / max(recovery_attempted, 1)
        
        return {
            "total_errors": len(recent_errors),
            "by_category": by_category,
            "by_severity": by_severity,
            "by_component": by_component,
            "recovery_rate": recovery_rate,
            "recovery_attempted": recovery_attempted,
            "recovery_successful": recovery_successful
        }
    
    def get_recent_errors(self, count: int = 50) -> List[ErrorRecord]:
        """Get recent error records."""
        return self.error_records[-count:] if self.error_records else []
    
    def clear_old_errors(self, hours: int = 168) -> int:  # Default 1 week
        """Clear old error records."""
        cutoff_time = datetime.now(timezone.utc) - datetime.timedelta(hours=hours)
        initial_count = len(self.error_records)
        
        self.error_records = [
            err for err in self.error_records
            if err.timestamp > cutoff_time
        ]
        
        cleared_count = initial_count - len(self.error_records)
        if cleared_count > 0:
            logger.info(f"Cleared {cleared_count} old error records")
        
        return cleared_count


# Global error handler instance
error_handler = ErrorHandler()


@contextmanager
def error_context(
    component: str,
    operation: str,
    source_id: Optional[int] = None,
    source_name: Optional[str] = None,
    url: Optional[str] = None,
    recovery_context: Optional[Dict[str, Any]] = None,
    reraise: bool = True
):
    """Context manager for handling errors with automatic classification and recovery."""
    context = ErrorContext(
        component=component,
        operation=operation,
        source_id=source_id,
        source_name=source_name,
        url=url
    )
    
    try:
        yield context
    except Exception as e:
        error_record = error_handler.handle_error(e, context, recovery_context)
        
        if reraise and not error_record.recovery_successful:
            raise


def handle_error_with_recovery(
    component: str,
    operation: str,
    retry_func: Optional[Callable] = None,
    fallback_func: Optional[Callable] = None,
    reset_func: Optional[Callable] = None
):
    """Decorator for automatic error handling with recovery options."""
    def decorator(func: Callable) -> Callable:
        def wrapper(*args, **kwargs):
            context = ErrorContext(
                component=component,
                operation=operation
            )
            
            recovery_context = {}
            if retry_func:
                recovery_context['retry_func'] = lambda: retry_func(*args, **kwargs)
            if fallback_func:
                recovery_context['fallback_func'] = lambda: fallback_func(*args, **kwargs)
            if reset_func:
                recovery_context['reset_func'] = reset_func
            
            try:
                return func(*args, **kwargs)
            except Exception as e:
                error_record = error_handler.handle_error(e, context, recovery_context)
                
                if not error_record.recovery_successful:
                    raise
                
                # If recovery was successful, we might want to return a default value
                # or the result of the recovery operation
                return None
        
        return wrapper
    return decorator