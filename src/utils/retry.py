"""
Retry utilities with exponential backoff.
"""

import time
import logging
import functools
from typing import Callable, Any, Type, Tuple

logger = logging.getLogger(__name__)


def retry_with_backoff(
    max_attempts: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    max_delay: float = 60.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,)
):
    """
    Decorator that retries a function with exponential backoff.
    
    Args:
        max_attempts: Maximum number of retry attempts
        initial_delay: Initial delay between retries in seconds
        backoff_factor: Factor to multiply delay by after each failure
        max_delay: Maximum delay between retries
        exceptions: Tuple of exception types to catch and retry on
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            delay = initial_delay
            last_exception = None
            
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    
                    if attempt == max_attempts - 1:
                        logger.error(
                            f"Function {func.__name__} failed after {max_attempts} attempts. "
                            f"Last error: {e}"
                        )
                        raise
                    
                    logger.warning(
                        f"Attempt {attempt + 1}/{max_attempts} failed for {func.__name__}: {e}. "
                        f"Retrying in {delay:.2f}s..."
                    )
                    
                    time.sleep(delay)
                    delay = min(delay * backoff_factor, max_delay)
            
            # This should never be reached, but just in case
            if last_exception:
                raise last_exception
                
        return wrapper
    return decorator