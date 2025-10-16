"""
Unit tests for error handling and resilience systems.
"""

import pytest
import time
from datetime import datetime, timezone
from unittest.mock import Mock, patch

from src.utils.error_handling import (
    ErrorHandler, ErrorContext, ErrorRecord, ErrorSeverity, ErrorCategory,
    ErrorClassifier, RetryRecoveryStrategy, FallbackRecoveryStrategy,
    error_context, handle_error_with_recovery
)
from src.utils.component_errors import (
    FetcherErrorHandler, ParserErrorHandler, DatabaseErrorHandler,
    NotificationErrorHandler, ComponentErrorManager
)


class TestErrorClassifier:
    """Test cases for error classification."""
    
    def test_network_error_classification(self):
        """Test classification of network errors."""
        context = ErrorContext(component="fetcher", operation="fetch")
        
        # Test different network exceptions
        connection_error = ConnectionError("Connection failed")
        category, severity = ErrorClassifier.classify_error(connection_error, context)
        assert category == ErrorCategory.NETWORK
        
        timeout_error = TimeoutError("Request timed out")
        category, severity = ErrorClassifier.classify_error(timeout_error, context)
        assert category == ErrorCategory.TIMEOUT
    
    def test_database_error_classification(self):
        """Test classification of database errors."""
        context = ErrorContext(component="database", operation="query")
        
        # Mock database error
        class DatabaseError(Exception):
            pass
        
        db_error = DatabaseError("Database connection failed")
        category, severity = ErrorClassifier.classify_error(db_error, context)
        assert category == ErrorCategory.DATABASE
    
    def test_parsing_error_classification(self):
        """Test classification of parsing errors."""
        context = ErrorContext(component="parser", operation="parse")
        
        import json
        json_error = json.JSONDecodeError("Invalid JSON", "test", 0)
        category, severity = ErrorClassifier.classify_error(json_error, context)
        assert category == ErrorCategory.PARSING
    
    def test_severity_determination(self):
        """Test severity determination based on error patterns."""
        context = ErrorContext(component="database", operation="connect")
        
        # Critical error
        critical_error = Exception("database connection failed")
        category, severity = ErrorClassifier.classify_error(critical_error, context)
        assert severity in [ErrorSeverity.HIGH, ErrorSeverity.CRITICAL]
        
        # Low severity error
        minor_error = Exception("minor validation issue")
        category, severity = ErrorClassifier.classify_error(minor_error, context)
        # Severity should be reasonable for the error type


class TestErrorHandler:
    """Test cases for the main error handler."""
    
    @pytest.fixture
    def error_handler(self):
        """Create an ErrorHandler instance for testing."""
        return ErrorHandler()
    
    def test_error_handling_basic(self, error_handler):
        """Test basic error handling functionality."""
        context = ErrorContext(
            component="test_component",
            operation="test_operation"
        )
        
        test_exception = ValueError("Test error message")
        
        error_record = error_handler.handle_error(test_exception, context)
        
        assert error_record.exception_type == "ValueError"
        assert error_record.message == "Test error message"
        assert error_record.context.component == "test_component"
        assert error_record.context.operation == "test_operation"
        assert isinstance(error_record.timestamp, datetime)
    
    def test_error_recovery_attempt(self, error_handler):
        """Test error recovery attempts."""
        context = ErrorContext(
            component="fetcher",
            operation="fetch",
            url="https://example.com"
        )
        
        # Mock recovery function
        recovery_called = False
        def mock_retry():
            nonlocal recovery_called
            recovery_called = True
        
        recovery_context = {"retry_func": mock_retry}
        
        # Create a network error that should trigger retry
        network_error = ConnectionError("Network failure")
        
        error_record = error_handler.handle_error(
            network_error, context, recovery_context
        )
        
        assert error_record.recovery_attempted is True
        # Recovery might or might not succeed depending on implementation
    
    def test_error_statistics(self, error_handler):
        """Test error statistics collection."""
        context = ErrorContext(component="test", operation="test")
        
        # Generate some test errors
        for i in range(5):
            error = ValueError(f"Test error {i}")
            error_handler.handle_error(error, context)
        
        stats = error_handler.get_error_statistics(hours=24)
        
        assert stats["total_errors"] == 5
        assert "by_category" in stats
        assert "by_severity" in stats
        assert "by_component" in stats
        assert "recovery_rate" in stats
    
    def test_error_callbacks(self, error_handler):
        """Test error callback functionality."""
        callback_called = False
        callback_error_record = None
        
        def test_callback(error_record):
            nonlocal callback_called, callback_error_record
            callback_called = True
            callback_error_record = error_record
        
        error_handler.add_error_callback(test_callback)
        
        context = ErrorContext(component="test", operation="test")
        test_error = ValueError("Callback test")
        
        error_record = error_handler.handle_error(test_error, context)
        
        assert callback_called is True
        assert callback_error_record == error_record
    
    def test_error_record_storage(self, error_handler):
        """Test error record storage and retrieval."""
        context = ErrorContext(component="test", operation="test")
        
        # Add some errors
        errors = []
        for i in range(3):
            error = ValueError(f"Test error {i}")
            record = error_handler.handle_error(error, context)
            errors.append(record)
        
        # Test retrieval
        recent_errors = error_handler.get_recent_errors(count=2)
        assert len(recent_errors) == 2
        
        # Should get the most recent errors
        assert recent_errors[-1].message == "Test error 2"
        assert recent_errors[-2].message == "Test error 1"


class TestRecoveryStrategies:
    """Test cases for error recovery strategies."""
    
    def test_retry_recovery_strategy(self):
        """Test retry recovery strategy."""
        strategy = RetryRecoveryStrategy(max_retries=2, delay=0.01)
        
        # Create error record for network error (should be retryable)
        context = ErrorContext(component="fetcher", operation="fetch")
        error_record = ErrorRecord(
            id="test_error",
            timestamp=datetime.now(timezone.utc),
            exception_type="ConnectionError",
            message="Network error",
            severity=ErrorSeverity.MEDIUM,
            category=ErrorCategory.NETWORK,
            context=context,
            traceback_str="test traceback"
        )
        
        assert strategy.can_recover(error_record) is True
        
        # Test recovery with mock function
        retry_called = False
        def mock_retry():
            nonlocal retry_called
            retry_called = True
        
        recovery_context = {"retry_func": mock_retry}
        result = strategy.recover(error_record, recovery_context)
        
        assert retry_called is True
    
    def test_fallback_recovery_strategy(self):
        """Test fallback recovery strategy."""
        strategy = FallbackRecoveryStrategy()
        
        # Create error record for parsing error (should have fallback)
        context = ErrorContext(component="parser", operation="parse")
        error_record = ErrorRecord(
            id="test_error",
            timestamp=datetime.now(timezone.utc),
            exception_type="JSONDecodeError",
            message="Parse error",
            severity=ErrorSeverity.MEDIUM,
            category=ErrorCategory.PARSING,
            context=context,
            traceback_str="test traceback"
        )
        
        assert strategy.can_recover(error_record) is True
        
        # Test recovery with mock fallback
        fallback_called = False
        def mock_fallback():
            nonlocal fallback_called
            fallback_called = True
        
        recovery_context = {"fallback_func": mock_fallback}
        result = strategy.recover(error_record, recovery_context)
        
        assert fallback_called is True


class TestErrorContext:
    """Test cases for error context manager."""
    
    def test_error_context_success(self):
        """Test error context with successful operation."""
        with error_context("test_component", "test_operation") as ctx:
            # Successful operation
            result = "success"
        
        assert ctx.component == "test_component"
        assert ctx.operation == "test_operation"
    
    def test_error_context_with_exception(self):
        """Test error context with exception handling."""
        with pytest.raises(ValueError):
            with error_context("test_component", "test_operation", reraise=True):
                raise ValueError("Test exception")
    
    def test_error_context_no_reraise(self):
        """Test error context without reraising exceptions."""
        with error_context("test_component", "test_operation", reraise=False):
            raise ValueError("Test exception")
        # Should not raise exception


class TestComponentErrorHandlers:
    """Test cases for component-specific error handlers."""
    
    def test_fetcher_error_handler(self):
        """Test fetcher-specific error handling."""
        base_handler = ErrorHandler()
        fetcher_handler = FetcherErrorHandler(base_handler)
        
        # Test source error tracking
        source_id = 1
        source_name = "Test Source"
        url = "https://example.com"
        
        # Simulate multiple errors
        for i in range(3):
            error = ConnectionError(f"Network error {i}")
            fetcher_handler.handle_fetch_error(error, source_id, source_name, url)
        
        # Check source health
        health = fetcher_handler.get_source_health(source_id)
        assert health["consecutive_errors"] == 3
        assert health["health_status"] in ["degraded", "unhealthy"]
    
    def test_parser_error_handler(self):
        """Test parser-specific error handling."""
        base_handler = ErrorHandler()
        parser_handler = ParserErrorHandler(base_handler)
        
        # Test parse failure pattern tracking
        url = "https://example.com/content"
        content_type = "text/html"
        
        # Simulate similar parse errors
        for i in range(3):
            error = ValueError("Invalid format in content")
            parser_handler.handle_parse_error(error, url, content_type)
        
        # Check for common failure patterns
        patterns = parser_handler.get_common_failure_patterns(min_occurrences=2)
        assert len(patterns) > 0
    
    def test_database_error_handler(self):
        """Test database-specific error handling."""
        base_handler = ErrorHandler()
        db_handler = DatabaseErrorHandler(base_handler)
        
        # Test connection failure tracking
        for i in range(2):
            error = Exception("database connection failed")
            db_handler.handle_database_error(error, "connect", "codes")
        
        # Check database health
        health = db_handler.get_database_health()
        assert health["connection_failures"] == 2
        assert health["is_healthy"] is False
    
    def test_notification_error_handler(self):
        """Test notification-specific error handling."""
        base_handler = ErrorHandler()
        notification_handler = NotificationErrorHandler(base_handler)
        
        channel_id = "123456789"
        message_type = "code_announcement"
        
        # Test rate limit handling
        rate_limit_error = Exception("rate limit exceeded, retry after 60 seconds")
        notification_handler.handle_notification_error(
            rate_limit_error, channel_id, message_type
        )
        
        # Check if channel is rate limited
        assert notification_handler.is_channel_rate_limited(channel_id) is True
        
        # Check channel health
        health = notification_handler.get_channel_health(channel_id)
        assert health["is_rate_limited"] is True
        assert health["rate_limited_until"] is not None


class TestComponentErrorManager:
    """Test cases for the component error manager."""
    
    def test_system_health_assessment(self):
        """Test overall system health assessment."""
        base_handler = ErrorHandler()
        manager = ComponentErrorManager(base_handler)
        
        # Get system health
        health = manager.get_system_health()
        
        assert "timestamp" in health
        assert "database" in health
        assert "error_statistics" in health
    
    def test_operations_pause_decision(self):
        """Test decision to pause operations based on system health."""
        base_handler = ErrorHandler()
        manager = ComponentErrorManager(base_handler)
        
        # Initially should not pause
        assert manager.should_pause_operations() is False
        
        # Simulate database issues
        manager.database_handler.connection_failures = 5
        
        # Now should pause
        assert manager.should_pause_operations() is True
    
    def test_recovery_recommendations(self):
        """Test generation of recovery recommendations."""
        base_handler = ErrorHandler()
        manager = ComponentErrorManager(base_handler)
        
        # Simulate various issues
        manager.database_handler.connection_failures = 3
        
        # Generate some errors to increase error rate
        context = ErrorContext(component="test", operation="test")
        for i in range(35):
            error = ValueError(f"Test error {i}")
            base_handler.handle_error(error, context)
        
        recommendations = manager.get_recovery_recommendations()
        
        assert len(recommendations) > 0
        assert any("database" in rec.lower() for rec in recommendations)
        assert any("error rate" in rec.lower() for rec in recommendations)


class TestErrorHandlingDecorator:
    """Test cases for error handling decorators."""
    
    def test_handle_error_with_recovery_decorator(self):
        """Test the error handling decorator."""
        retry_called = False
        
        def retry_func():
            nonlocal retry_called
            retry_called = True
            return "retry_result"
        
        @handle_error_with_recovery(
            component="test",
            operation="test_op",
            retry_func=retry_func
        )
        def failing_function():
            raise ConnectionError("Network failure")
        
        # This should trigger retry recovery
        result = failing_function()
        
        # The decorator should handle the error and attempt recovery
        assert retry_called is True