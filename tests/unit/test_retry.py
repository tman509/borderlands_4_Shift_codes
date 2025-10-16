"""
Unit tests for retry mechanisms and resilience patterns.
"""

import pytest
import time
from unittest.mock import Mock, patch
from src.utils.retry import (
    retry_with_backoff, CircuitBreaker, CircuitBreakerState,
    BulkheadPattern, RateLimiter, TimeoutError, timeout
)


class TestRetryWithBackoff:
    """Test cases for retry with backoff decorator."""
    
    def test_successful_execution(self):
        """Test successful execution without retries."""
        call_count = 0
        
        @retry_with_backoff(max_attempts=3)
        def successful_function():
            nonlocal call_count
            call_count += 1
            return "success"
        
        result = successful_function()
        assert result == "success"
        assert call_count == 1
    
    def test_retry_on_failure(self):
        """Test retry behavior on failures."""
        call_count = 0
        
        @retry_with_backoff(max_attempts=3, initial_delay=0.01)
        def failing_function():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("Temporary failure")
            return "success"
        
        result = failing_function()
        assert result == "success"
        assert call_count == 3
    
    def test_max_attempts_exceeded(self):
        """Test behavior when max attempts are exceeded."""
        call_count = 0
        
        @retry_with_backoff(max_attempts=2, initial_delay=0.01)
        def always_failing_function():
            nonlocal call_count
            call_count += 1
            raise ValueError("Always fails")
        
        with pytest.raises(ValueError, match="Always fails"):
            always_failing_function()
        
        assert call_count == 2
    
    def test_specific_exceptions(self):
        """Test retry only on specific exceptions."""
        call_count = 0
        
        @retry_with_backoff(max_attempts=3, exceptions=(ValueError,))
        def mixed_exceptions():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("Retryable")
            elif call_count == 2:
                raise TypeError("Not retryable")
        
        with pytest.raises(TypeError, match="Not retryable"):
            mixed_exceptions()
        
        assert call_count == 2
    
    def test_backoff_timing(self):
        """Test exponential backoff timing."""
        call_times = []
        
        @retry_with_backoff(max_attempts=3, initial_delay=0.1, backoff_factor=2.0, jitter=False)
        def timing_test():
            call_times.append(time.time())
            if len(call_times) < 3:
                raise ValueError("Fail")
            return "success"
        
        start_time = time.time()
        result = timing_test()
        
        assert result == "success"
        assert len(call_times) == 3
        
        # Check approximate timing (allowing for some variance)
        delay1 = call_times[1] - call_times[0]
        delay2 = call_times[2] - call_times[1]
        
        assert 0.08 <= delay1 <= 0.15  # ~0.1s ±50%
        assert 0.15 <= delay2 <= 0.25  # ~0.2s ±25%


class TestCircuitBreaker:
    """Test cases for circuit breaker pattern."""
    
    def test_closed_state_success(self):
        """Test circuit breaker in closed state with successful calls."""
        cb = CircuitBreaker(failure_threshold=3)
        
        def successful_function():
            return "success"
        
        result = cb.call(successful_function)
        assert result == "success"
        assert cb.state == CircuitBreakerState.CLOSED
        assert cb.failure_count == 0
    
    def test_failure_counting(self):
        """Test failure counting and state transitions."""
        cb = CircuitBreaker(failure_threshold=2)
        
        def failing_function():
            raise ValueError("Test failure")
        
        # First failure
        with pytest.raises(ValueError):
            cb.call(failing_function)
        assert cb.failure_count == 1
        assert cb.state == CircuitBreakerState.CLOSED
        
        # Second failure - should open circuit
        with pytest.raises(ValueError):
            cb.call(failing_function)
        assert cb.failure_count == 2
        assert cb.state == CircuitBreakerState.OPEN
    
    def test_open_state_blocking(self):
        """Test that open circuit breaker blocks calls."""
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=1.0)
        
        def failing_function():
            raise ValueError("Test failure")
        
        # Trigger circuit opening
        with pytest.raises(ValueError):
            cb.call(failing_function)
        
        assert cb.state == CircuitBreakerState.OPEN
        
        # Subsequent calls should be blocked
        with pytest.raises(Exception, match="Circuit breaker is OPEN"):
            cb.call(lambda: "should not execute")
    
    def test_half_open_recovery(self):
        """Test half-open state and recovery."""
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.1)
        
        def failing_function():
            raise ValueError("Test failure")
        
        def successful_function():
            return "success"
        
        # Open the circuit
        with pytest.raises(ValueError):
            cb.call(failing_function)
        assert cb.state == CircuitBreakerState.OPEN
        
        # Wait for recovery timeout
        time.sleep(0.15)
        
        # Next call should succeed and close circuit
        result = cb.call(successful_function)
        assert result == "success"
        assert cb.state == CircuitBreakerState.CLOSED
        assert cb.failure_count == 0
    
    def test_get_state(self):
        """Test getting circuit breaker state information."""
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=60.0)
        
        state_info = cb.get_state()
        
        assert state_info["state"] == "closed"
        assert state_info["failure_count"] == 0
        assert state_info["failure_threshold"] == 3
        assert state_info["recovery_timeout"] == 60.0


class TestBulkheadPattern:
    """Test cases for bulkhead pattern."""
    
    def test_concurrent_execution(self):
        """Test concurrent execution within limits."""
        bulkhead = BulkheadPattern(max_concurrent=2)
        
        def test_function():
            return "success"
        
        # Should succeed within limit
        result1 = bulkhead.execute(test_function)
        result2 = bulkhead.execute(test_function)
        
        assert result1 == "success"
        assert result2 == "success"
    
    def test_limit_enforcement(self):
        """Test that bulkhead enforces concurrency limits."""
        import threading
        bulkhead = BulkheadPattern(max_concurrent=1)
        
        execution_order = []
        barrier = threading.Barrier(2)
        
        def blocking_function(name):
            execution_order.append(f"{name}_start")
            barrier.wait()  # Wait for both threads
            execution_order.append(f"{name}_end")
            return name
        
        def thread1():
            try:
                bulkhead.execute(blocking_function, "thread1")
            except Exception as e:
                execution_order.append(f"thread1_error: {e}")
        
        def thread2():
            try:
                bulkhead.execute(blocking_function, "thread2")
            except Exception as e:
                execution_order.append(f"thread2_error: {e}")
        
        t1 = threading.Thread(target=thread1)
        t2 = threading.Thread(target=thread2)
        
        t1.start()
        time.sleep(0.01)  # Small delay to ensure t1 starts first
        t2.start()
        
        t1.join()
        t2.join()
        
        # One should succeed, one should fail due to limit
        assert len(execution_order) >= 2
        assert any("error" in item for item in execution_order)
    
    def test_get_stats(self):
        """Test getting bulkhead statistics."""
        bulkhead = BulkheadPattern(max_concurrent=5)
        
        stats = bulkhead.get_stats()
        
        assert stats["max_concurrent"] == 5
        assert stats["active_count"] == 0
        assert stats["available_slots"] == 5


class TestRateLimiter:
    """Test cases for rate limiter."""
    
    def test_token_acquisition(self):
        """Test basic token acquisition."""
        limiter = RateLimiter(rate=10.0, burst=5)  # 10 tokens/sec, burst of 5
        
        # Should be able to acquire tokens up to burst limit
        assert limiter.acquire(tokens=3, blocking=False) is True
        assert limiter.acquire(tokens=2, blocking=False) is True
        
        # Should fail to acquire more tokens
        assert limiter.acquire(tokens=1, blocking=False) is False
    
    def test_token_replenishment(self):
        """Test token replenishment over time."""
        limiter = RateLimiter(rate=5.0, burst=2)  # 5 tokens/sec, burst of 2
        
        # Exhaust tokens
        assert limiter.acquire(tokens=2, blocking=False) is True
        assert limiter.acquire(tokens=1, blocking=False) is False
        
        # Wait for replenishment
        time.sleep(0.5)  # Should add ~2.5 tokens
        
        # Should be able to acquire again
        assert limiter.acquire(tokens=2, blocking=False) is True
    
    def test_blocking_acquisition(self):
        """Test blocking token acquisition."""
        limiter = RateLimiter(rate=10.0, burst=1)
        
        # Exhaust tokens
        assert limiter.acquire(tokens=1, blocking=False) is True
        
        # This should block briefly then succeed
        start_time = time.time()
        result = limiter.acquire(tokens=1, blocking=True)
        end_time = time.time()
        
        assert result is True
        assert end_time - start_time >= 0.05  # Should have waited at least 50ms
    
    def test_get_stats(self):
        """Test getting rate limiter statistics."""
        limiter = RateLimiter(rate=5.0, burst=10)
        
        stats = limiter.get_stats()
        
        assert stats["rate"] == 5.0
        assert stats["burst"] == 10
        assert "available_tokens" in stats
        assert "last_update" in stats


class TestTimeoutDecorator:
    """Test cases for timeout decorator."""
    
    def test_successful_execution_within_timeout(self):
        """Test successful execution within timeout."""
        @timeout(1.0)
        def quick_function():
            time.sleep(0.1)
            return "success"
        
        result = quick_function()
        assert result == "success"
    
    def test_timeout_exceeded(self):
        """Test timeout when execution takes too long."""
        @timeout(0.1)
        def slow_function():
            time.sleep(0.5)
            return "should not reach here"
        
        with pytest.raises(TimeoutError, match="timed out after 0.1s"):
            slow_function()
    
    def test_exception_propagation(self):
        """Test that exceptions are properly propagated."""
        @timeout(1.0)
        def failing_function():
            raise ValueError("Test exception")
        
        with pytest.raises(ValueError, match="Test exception"):
            failing_function()