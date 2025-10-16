"""
Component-specific error handling and recovery strategies.
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

from .error_handling import (
    ErrorHandler, ErrorContext, ErrorRecoveryStrategy, ErrorRecord,
    ErrorCategory, ErrorSeverity
)

logger = logging.getLogger(__name__)


class FetcherErrorHandler:
    """Specialized error handler for fetcher components."""
    
    def __init__(self, error_handler: ErrorHandler):
        self.error_handler = error_handler
        self.source_error_counts: Dict[int, int] = {}
        self.source_last_success: Dict[int, datetime] = {}
        self.max_consecutive_errors = 5
    
    def handle_fetch_error(
        self,
        exception: Exception,
        source_id: int,
        source_name: str,
        url: str,
        retry_func: Optional[callable] = None
    ) -> ErrorRecord:
        """Handle fetcher-specific errors."""
        
        context = ErrorContext(
            component="fetcher",
            operation="fetch",
            source_id=source_id,
            source_name=source_name,
            url=url
        )
        
        recovery_context = {}
        if retry_func:
            recovery_context['retry_func'] = retry_func
        
        error_record = self.error_handler.handle_error(exception, context, recovery_context)
        
        # Track source-specific error counts
        self._update_source_error_tracking(source_id, error_record.recovery_successful)
        
        return error_record
    
    def _update_source_error_tracking(self, source_id: int, success: bool) -> None:
        """Update error tracking for a specific source."""
        if success:
            self.source_error_counts[source_id] = 0
            self.source_last_success[source_id] = datetime.now(timezone.utc)
        else:
            self.source_error_counts[source_id] = self.source_error_counts.get(source_id, 0) + 1
    
    def should_disable_source(self, source_id: int) -> bool:
        """Check if source should be temporarily disabled due to errors."""
        error_count = self.source_error_counts.get(source_id, 0)
        return error_count >= self.max_consecutive_errors
    
    def get_source_health(self, source_id: int) -> Dict[str, Any]:
        """Get health information for a specific source."""
        error_count = self.source_error_counts.get(source_id, 0)
        last_success = self.source_last_success.get(source_id)
        
        return {
            "consecutive_errors": error_count,
            "last_success": last_success.isoformat() if last_success else None,
            "should_disable": self.should_disable_source(source_id),
            "health_status": "healthy" if error_count == 0 else "degraded" if error_count < 3 else "unhealthy"
        }


class ParserErrorHandler:
    """Specialized error handler for parser components."""
    
    def __init__(self, error_handler: ErrorHandler):
        self.error_handler = error_handler
        self.parse_failure_patterns: Dict[str, int] = {}
    
    def handle_parse_error(
        self,
        exception: Exception,
        content_url: str,
        content_type: str,
        fallback_func: Optional[callable] = None
    ) -> ErrorRecord:
        """Handle parser-specific errors."""
        
        context = ErrorContext(
            component="parser",
            operation="parse_content",
            url=content_url,
            system_data={"content_type": content_type}
        )
        
        recovery_context = {}
        if fallback_func:
            recovery_context['fallback_func'] = fallback_func
        
        error_record = self.error_handler.handle_error(exception, context, recovery_context)
        
        # Track parse failure patterns
        self._track_parse_failure_pattern(str(exception))
        
        return error_record
    
    def _track_parse_failure_pattern(self, error_message: str) -> None:
        """Track common parse failure patterns."""
        # Extract key parts of error message for pattern analysis
        pattern_key = error_message[:100]  # First 100 chars
        self.parse_failure_patterns[pattern_key] = self.parse_failure_patterns.get(pattern_key, 0) + 1
    
    def get_common_failure_patterns(self, min_occurrences: int = 3) -> Dict[str, int]:
        """Get common parse failure patterns."""
        return {
            pattern: count for pattern, count in self.parse_failure_patterns.items()
            if count >= min_occurrences
        }


class DatabaseErrorHandler:
    """Specialized error handler for database components."""
    
    def __init__(self, error_handler: ErrorHandler):
        self.error_handler = error_handler
        self.connection_failures = 0
        self.last_connection_attempt: Optional[datetime] = None
    
    def handle_database_error(
        self,
        exception: Exception,
        operation: str,
        table: Optional[str] = None,
        retry_func: Optional[callable] = None,
        reset_func: Optional[callable] = None
    ) -> ErrorRecord:
        """Handle database-specific errors."""
        
        context = ErrorContext(
            component="database",
            operation=operation,
            system_data={"table": table} if table else {}
        )
        
        recovery_context = {}
        if retry_func:
            recovery_context['retry_func'] = retry_func
        if reset_func:
            recovery_context['reset_func'] = reset_func
        
        error_record = self.error_handler.handle_error(exception, context, recovery_context)
        
        # Track connection failures
        if "connection" in str(exception).lower():
            self.connection_failures += 1
            self.last_connection_attempt = datetime.now(timezone.utc)
        elif error_record.recovery_successful:
            self.connection_failures = 0
        
        return error_record
    
    def is_database_healthy(self) -> bool:
        """Check if database appears healthy."""
        return self.connection_failures < 3
    
    def get_database_health(self) -> Dict[str, Any]:
        """Get database health information."""
        return {
            "connection_failures": self.connection_failures,
            "last_connection_attempt": self.last_connection_attempt.isoformat() if self.last_connection_attempt else None,
            "is_healthy": self.is_database_healthy()
        }


class NotificationErrorHandler:
    """Specialized error handler for notification components."""
    
    def __init__(self, error_handler: ErrorHandler):
        self.error_handler = error_handler
        self.channel_failures: Dict[str, int] = {}
        self.rate_limit_until: Dict[str, datetime] = {}
    
    def handle_notification_error(
        self,
        exception: Exception,
        channel_id: str,
        message_type: str,
        retry_func: Optional[callable] = None
    ) -> ErrorRecord:
        """Handle notification-specific errors."""
        
        context = ErrorContext(
            component="notification",
            operation="send_message",
            user_data={"channel_id": channel_id, "message_type": message_type}
        )
        
        recovery_context = {}
        if retry_func:
            recovery_context['retry_func'] = retry_func
        
        error_record = self.error_handler.handle_error(exception, context, recovery_context)
        
        # Handle rate limiting
        if "rate limit" in str(exception).lower() or "429" in str(exception):
            self._handle_rate_limit(channel_id, exception)
        
        # Track channel failures
        if not error_record.recovery_successful:
            self.channel_failures[channel_id] = self.channel_failures.get(channel_id, 0) + 1
        else:
            self.channel_failures[channel_id] = 0
        
        return error_record
    
    def _handle_rate_limit(self, channel_id: str, exception: Exception) -> None:
        """Handle rate limiting for a specific channel."""
        # Try to extract rate limit duration from exception
        import re
        duration_match = re.search(r'(\d+)\s*seconds?', str(exception))
        if duration_match:
            duration = int(duration_match.group(1))
        else:
            duration = 60  # Default 1 minute
        
        self.rate_limit_until[channel_id] = datetime.now(timezone.utc) + datetime.timedelta(seconds=duration)
        logger.warning(f"Channel {channel_id} rate limited for {duration} seconds")
    
    def is_channel_rate_limited(self, channel_id: str) -> bool:
        """Check if channel is currently rate limited."""
        if channel_id not in self.rate_limit_until:
            return False
        
        return datetime.now(timezone.utc) < self.rate_limit_until[channel_id]
    
    def get_channel_health(self, channel_id: str) -> Dict[str, Any]:
        """Get health information for a specific channel."""
        failures = self.channel_failures.get(channel_id, 0)
        rate_limited_until = self.rate_limit_until.get(channel_id)
        
        return {
            "consecutive_failures": failures,
            "is_rate_limited": self.is_channel_rate_limited(channel_id),
            "rate_limited_until": rate_limited_until.isoformat() if rate_limited_until else None,
            "health_status": "healthy" if failures == 0 else "degraded" if failures < 3 else "unhealthy"
        }


class ComponentErrorManager:
    """Manager for all component-specific error handlers."""
    
    def __init__(self, error_handler: ErrorHandler):
        self.error_handler = error_handler
        self.fetcher_handler = FetcherErrorHandler(error_handler)
        self.parser_handler = ParserErrorHandler(error_handler)
        self.database_handler = DatabaseErrorHandler(error_handler)
        self.notification_handler = NotificationErrorHandler(error_handler)
    
    def get_system_health(self) -> Dict[str, Any]:
        """Get overall system health from all components."""
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "database": self.database_handler.get_database_health(),
            "error_statistics": self.error_handler.get_error_statistics(),
            "common_parse_failures": self.parser_handler.get_common_failure_patterns()
        }
    
    def get_source_health_summary(self, source_ids: List[int]) -> Dict[int, Dict[str, Any]]:
        """Get health summary for multiple sources."""
        return {
            source_id: self.fetcher_handler.get_source_health(source_id)
            for source_id in source_ids
        }
    
    def get_channel_health_summary(self, channel_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """Get health summary for multiple channels."""
        return {
            channel_id: self.notification_handler.get_channel_health(channel_id)
            for channel_id in channel_ids
        }
    
    def should_pause_operations(self) -> bool:
        """Determine if operations should be paused due to system health."""
        # Check if database is unhealthy
        if not self.database_handler.is_database_healthy():
            return True
        
        # Check error rate
        stats = self.error_handler.get_error_statistics(hours=1)
        if stats["total_errors"] > 50:  # More than 50 errors in last hour
            return True
        
        # Check critical error count
        critical_errors = stats["by_severity"].get("critical", 0)
        if critical_errors > 5:  # More than 5 critical errors
            return True
        
        return False
    
    def get_recovery_recommendations(self) -> List[str]:
        """Get recommendations for system recovery."""
        recommendations = []
        
        # Database recommendations
        if not self.database_handler.is_database_healthy():
            recommendations.append("Check database connection and restart if necessary")
        
        # Error rate recommendations
        stats = self.error_handler.get_error_statistics(hours=1)
        if stats["total_errors"] > 30:
            recommendations.append("High error rate detected - consider reducing operation frequency")
        
        # Parse failure recommendations
        common_failures = self.parser_handler.get_common_failure_patterns()
        if common_failures:
            recommendations.append("Common parse failures detected - review parser configurations")
        
        # Rate limiting recommendations
        if any(self.notification_handler.rate_limit_until.values()):
            recommendations.append("Rate limiting active - reduce notification frequency")
        
        return recommendations