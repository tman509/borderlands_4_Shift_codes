"""
Retry utilities with exponential backoff and advanced resilience patterns.
"""

import time
import logging
import functools
import random
import threading
from typing import Callable, Any, Type, Tuple, Optional, Dict, List
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class CircuitBreakerState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class RetryAttempt:
    """Information about a retry attempt."""
    attempt_number: int
    exception: Exception
    delay: float
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class RetryResult:
    """Result of a retry operation."""
    success: bool
    attempts: List[RetryAttempt] = field(default_factory=list)
    final_result: Any = None
    final_exception: Optional[Exception] = None
    total_time: float = 0.0


class CircuitBreaker:
    """Circuit breaker implementation for preventing cascading failures."""
    
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        expected_exception: Type[Exception] = Exception
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        
        self.failure_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.state = CircuitBreakerState.CLOSED
        self._lock = threading.Lock()
    
    def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with circuit breaker protection."""
        with self._lock:
            if self.state == CircuitBreakerState.OPEN:
                if self._should_attempt_reset():
                    self.state = CircuitBreakerState.HALF_OPEN
                    logger.info("Circuit breaker moving to HALF_OPEN state")
                else:
                    raise Exception("Circuit breaker is OPEN - calls are blocked")
        
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except self.expected_exception as e:
            self._on_failure()
            raise
    
    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset."""
        if not self.last_failure_time:
            return True
        
        return datetime.now() - self.last_failure_time > timedelta(seconds=self.recovery_timeout)
    
    def _on_success(self) -> None:
        """Handle successful execution."""
        with self._lock:
            if self.state == CircuitBreakerState.HALF_OPEN:
                self.state = CircuitBreakerState.CLOSED
                logger.info("Circuit breaker reset to CLOSED state")
            
            self.failure_count = 0
    
    def _on_failure(self) -> None:
        """Handle failed execution."""
        with self._lock:
            self.failure_count += 1
            self.last_failure_time = datetime.now()
            
            if self.failure_count >= self.failure_threshold:
                self.state = CircuitBreakerState.OPEN
                logger.warning(f"Circuit breaker opened after {self.failure_count} failures")
    
    def get_state(self) -> Dict[str, Any]:
        """Get current circuit breaker state."""
        return {
            "state": self.state.value,
            "failure_count": self.failure_count,
            "failure_threshold": self.failure_threshold,
            "last_failure_time": self.last_failure_time.isoformat() if self.last_failure_time else None,
            "recovery_timeout": self.recovery_timeout
        }


def retry_with_backoff(
    max_attempts: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    max_delay: float = 60.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    jitter: bool = True,
    on_retry: Optional[Callable[[RetryAttempt], None]] = None
):
    """
    Enhanced decorator that retries a function with exponential backoff.
    
    Args:
        max_attempts: Maximum number of retry attempts
        initial_delay: Initial delay between retries in seconds
        backoff_factor: Factor to multiply delay by after each failure
        max_delay: Maximum delay between retries
        exceptions: Tuple of exception types to catch and retry on
        jitter: Whether to add random jitter to delays
        on_retry: Optional callback function called on each retry attempt
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            start_time = time.time()
            delay = initial_delay
            attempts = []
            last_exception = None
            
            for attempt in range(max_attempts):
                try:
                    result = func(*args, **kwargs)
                    
                    # Log successful retry if there were previous failures
                    if attempts:
                        total_time = time.time() - start_time
                        logger.info(
                            f"Function {func.__name__} succeeded on attempt {attempt + 1} "
                            f"after {total_time:.2f}s"
                        )
                    
                    return result
                    
                except exceptions as e:
                    last_exception = e
                    
                    retry_attempt = RetryAttempt(
                        attempt_number=attempt + 1,
                        exception=e,
                        delay=delay
                    )
                    attempts.append(retry_attempt)
                    
                    # Call retry callback if provided
                    if on_retry:
                        try:
                            on_retry(retry_attempt)
                        except Exception as callback_error:
                            logger.warning(f"Retry callback failed: {callback_error}")
                    
                    if attempt == max_attempts - 1:
                        total_time = time.time() - start_time
                        logger.error(
                            f"Function {func.__name__} failed after {max_attempts} attempts "
                            f"in {total_time:.2f}s. Last error: {e}"
                        )
                        raise
                    
                    # Calculate delay with optional jitter
                    actual_delay = delay
                    if jitter:
                        # Add ±25% jitter to prevent thundering herd
                        jitter_range = delay * 0.25
                        actual_delay = delay + random.uniform(-jitter_range, jitter_range)
                        actual_delay = max(0.1, actual_delay)  # Minimum 100ms delay
                    
                    logger.warning(
                        f"Attempt {attempt + 1}/{max_attempts} failed for {func.__name__}: {e}. "
                        f"Retrying in {actual_delay:.2f}s..."
                    )
                    
                    time.sleep(actual_delay)
                    delay = min(delay * backoff_factor, max_delay)
            
            # This should never be reached, but just in case
            if last_exception:
                raise last_exception
                
        return wrapper
    return decorator


def retry_with_circuit_breaker(
    circuit_breaker: CircuitBreaker,
    max_attempts: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    max_delay: float = 60.0
):
    """
    Decorator that combines retry logic with circuit breaker pattern.
    
    Args:
        circuit_breaker: CircuitBreaker instance to use
        max_attempts: Maximum number of retry attempts
        initial_delay: Initial delay between retries
        backoff_factor: Exponential backoff factor
        max_delay: Maximum delay between retries
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            @retry_with_backoff(
                max_attempts=max_attempts,
                initial_delay=initial_delay,
                backoff_factor=backoff_factor,
                max_delay=max_delay,
                exceptions=(circuit_breaker.expected_exception,)
            )
            def retry_func():
                return circuit_breaker.call(func, *args, **kwargs)
            
            return retry_func()
        
        return wrapper
    return decorator


class BulkheadPattern:
    """Bulkhead pattern implementation for resource isolation."""
    
    def __init__(self, max_concurrent: int = 10):
        self.max_concurrent = max_concurrent
        self.semaphore = threading.Semaphore(max_concurrent)
        self.active_count = 0
        self._lock = threading.Lock()
    
    def execute(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with bulkhead protection."""
        if not self.semaphore.acquire(blocking=False):
            raise Exception(f"Bulkhead limit reached: {self.max_concurrent} concurrent operations")
        
        try:
            with self._lock:
                self.active_count += 1
            
            return func(*args, **kwargs)
        finally:
            with self._lock:
                self.active_count -= 1
            self.semaphore.release()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get bulkhead statistics."""
        return {
            "max_concurrent": self.max_concurrent,
            "active_count": self.active_count,
            "available_slots": self.max_concurrent - self.active_count
        }


def bulkhead_protected(max_concurrent: int = 10):
    """Decorator for bulkhead pattern protection."""
    bulkhead = BulkheadPattern(max_concurrent)
    
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            return bulkhead.execute(func, *args, **kwargs)
        
        # Attach bulkhead instance for monitoring
        wrapper._bulkhead = bulkhead
        return wrapper
    
    return decorator


class TimeoutError(Exception):
    """Exception raised when operation times out."""
    pass


def timeout(seconds: float):
    """Decorator that adds timeout to function execution."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            result = None
            exception = None
            
            def target():
                nonlocal result, exception
                try:
                    result = func(*args, **kwargs)
                except Exception as e:
                    exception = e
            
            thread = threading.Thread(target=target)
            thread.daemon = True
            thread.start()
            thread.join(timeout=seconds)
            
            if thread.is_alive():
                # Thread is still running - we can't kill it but we can timeout
                raise TimeoutError(f"Function {func.__name__} timed out after {seconds}s")
            
            if exception:
                raise exception
            
            return result
        
        return wrapper
    return decorator


class RateLimiter:
    """Token bucket rate limiter implementation."""
    
    def __init__(self, rate: float, burst: int = 1):
        """
        Initialize rate limiter.
        
        Args:
            rate: Tokens per second
            burst: Maximum burst size (bucket capacity)
        """
        self.rate = rate
        self.burst = burst
        self.tokens = burst
        self.last_update = time.time()
        self._lock = threading.Lock()
    
    def acquire(self, tokens: int = 1, blocking: bool = True) -> bool:
        """
        Acquire tokens from the bucket.
        
        Args:
            tokens: Number of tokens to acquire
            blocking: Whether to block if tokens not available
            
        Returns:
            True if tokens acquired, False otherwise
        """
        with self._lock:
            now = time.time()
            
            # Add tokens based on elapsed time
            elapsed = now - self.last_update
            self.tokens = min(self.burst, self.tokens + elapsed * self.rate)
            self.last_update = now
            
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            elif blocking:
                # Calculate wait time
                wait_time = (tokens - self.tokens) / self.rate
                time.sleep(wait_time)
                self.tokens = max(0, self.tokens - tokens)
                return True
            else:
                return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get rate limiter statistics."""
        return {
            "rate": self.rate,
            "burst": self.burst,
            "available_tokens": self.tokens,
            "last_update": self.last_update
        }


def rate_limited(rate: float, burst: int = 1):
    """Decorator for rate limiting function calls."""
    limiter = RateLimiter(rate, burst)
    
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            limiter.acquire()
            return func(*args, **kwargs)
        
        # Attach limiter for monitoring
        wrapper._rate_limiter = limiter
        return wrapper
    
    return decorator


class ResilienceManager:
    """Manager for coordinating multiple resilience patterns."""
    
    def __init__(self):
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}
        self.bulkheads: Dict[str, BulkheadPattern] = {}
        self.rate_limiters: Dict[str, RateLimiter] = {}
    
    def get_circuit_breaker(self, name: str, **kwargs) -> CircuitBreaker:
        """Get or create a circuit breaker."""
        if name not in self.circuit_breakers:
            self.circuit_breakers[name] = CircuitBreaker(**kwargs)
        return self.circuit_breakers[name]
    
    def get_bulkhead(self, name: str, **kwargs) -> BulkheadPattern:
        """Get or create a bulkhead."""
        if name not in self.bulkheads:
            self.bulkheads[name] = BulkheadPattern(**kwargs)
        return self.bulkheads[name]
    
    def get_rate_limiter(self, name: str, **kwargs) -> RateLimiter:
        """Get or create a rate limiter."""
        if name not in self.rate_limiters:
            self.rate_limiters[name] = RateLimiter(**kwargs)
        return self.rate_limiters[name]
    
    def get_all_stats(self) -> Dict[str, Any]:
        """Get statistics for all resilience components."""
        return {
            "circuit_breakers": {
                name: cb.get_state() for name, cb in self.circuit_breakers.items()
            },
            "bulkheads": {
                name: bh.get_stats() for name, bh in self.bulkheads.items()
            },
            "rate_limiters": {
                name: rl.get_stats() for name, rl in self.rate_limiters.items()
            }
        }


# Global resilience manager instance
resilience_manager = ResilienceManager()