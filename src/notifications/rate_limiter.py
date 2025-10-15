"""
Rate limiting system with token bucket algorithm and adaptive limits.
"""

import logging
import time
import threading
from typing import Dict, Optional, Any
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting."""
    requests_per_second: float = 1.0
    burst_capacity: int = 5
    refill_rate: float = 1.0  # tokens per second
    adaptive: bool = True
    backoff_factor: float = 2.0
    max_backoff_seconds: float = 300.0  # 5 minutes


class TokenBucket:
    """Token bucket implementation for rate limiting."""
    
    def __init__(self, capacity: int, refill_rate: float):
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.tokens = float(capacity)
        self.last_refill = time.time()
        self._lock = threading.Lock()
    
    def consume(self, tokens: int = 1) -> bool:
        """Try to consume tokens from the bucket."""
        with self._lock:
            now = time.time()
            
            # Refill tokens based on elapsed time
            elapsed = now - self.last_refill
            self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
            self.last_refill = now
            
            # Check if we have enough tokens
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            
            return False
    
    def available_tokens(self) -> float:
        """Get number of available tokens."""
        with self._lock:
            now = time.time()
            elapsed = now - self.last_refill
            return min(self.capacity, self.tokens + elapsed * self.refill_rate)
    
    def time_until_available(self, tokens: int = 1) -> float:
        """Get time in seconds until specified tokens are available."""
        with self._lock:
            available = self.available_tokens()
            if available >= tokens:
                return 0.0
            
            needed = tokens - available
            return needed / self.refill_rate


class RateLimiter:
    """Advanced rate limiter with per-channel limits and adaptive behavior."""
    
    def __init__(self, default_config: Optional[RateLimitConfig] = None):
        self.default_config = default_config or RateLimitConfig()
        
        # Per-channel rate limiters
        self._buckets: Dict[str, TokenBucket] = {}
        self._configs: Dict[str, RateLimitConfig] = {}
        
        # Adaptive rate limiting state
        self._failure_counts: Dict[str, int] = {}
        self._last_failure_time: Dict[str, float] = {}
        self._backoff_until: Dict[str, float] = {}
        
        # Global statistics
        self.stats = {
            "requests_allowed": 0,
            "requests_denied": 0,
            "adaptive_slowdowns": 0,
            "channels_tracked": 0
        }
        
        self._lock = threading.RLock()
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    def can_send(self, channel_id: str, tokens: int = 1) -> bool:
        """Check if a request can be sent to the specified channel."""
        with self._lock:
            # Check if we're in backoff period
            if self._is_in_backoff(channel_id):
                self.stats["requests_denied"] += 1
                return False
            
            # Get or create bucket for channel
            bucket = self._get_bucket(channel_id)
            
            # Try to consume tokens
            if bucket.consume(tokens):
                self.stats["requests_allowed"] += 1
                return True
            else:
                self.stats["requests_denied"] += 1
                return False
    
    def wait_time(self, channel_id: str, tokens: int = 1) -> float:
        """Get wait time in seconds before next request can be sent."""
        with self._lock:
            # Check backoff time
            backoff_time = self._get_backoff_time(channel_id)
            if backoff_time > 0:
                return backoff_time
            
            # Get bucket wait time
            bucket = self._get_bucket(channel_id)
            return bucket.time_until_available(tokens)
    
    def record_success(self, channel_id: str) -> None:
        """Record a successful request."""
        with self._lock:
            # Reset failure count on success
            if channel_id in self._failure_counts:
                self._failure_counts[channel_id] = 0
            
            # Clear backoff if we were in one
            if channel_id in self._backoff_until:
                del self._backoff_until[channel_id]
    
    def record_failure(self, channel_id: str, error_code: Optional[int] = None) -> None:
        """Record a failed request and potentially trigger adaptive limiting."""
        with self._lock:
            config = self._get_config(channel_id)
            
            if not config.adaptive:
                return
            
            # Increment failure count
            self._failure_counts[channel_id] = self._failure_counts.get(channel_id, 0) + 1
            self._last_failure_time[channel_id] = time.time()
            
            # Check if we should trigger backoff
            failure_count = self._failure_counts[channel_id]
            
            # Different backoff strategies based on error type
            if error_code == 429:  # Rate limited by server
                backoff_seconds = min(
                    config.backoff_factor ** failure_count,
                    config.max_backoff_seconds
                )
                self._backoff_until[channel_id] = time.time() + backoff_seconds
                self.stats["adaptive_slowdowns"] += 1
                
                self.logger.warning(
                    f"Rate limited by server for channel {channel_id}, "
                    f"backing off for {backoff_seconds:.1f}s"
                )
            
            elif failure_count >= 3:  # Multiple failures
                backoff_seconds = min(
                    config.backoff_factor * failure_count,
                    config.max_backoff_seconds
                )
                self._backoff_until[channel_id] = time.time() + backoff_seconds
                self.stats["adaptive_slowdowns"] += 1
                
                self.logger.warning(
                    f"Multiple failures ({failure_count}) for channel {channel_id}, "
                    f"backing off for {backoff_seconds:.1f}s"
                )
    
    def set_channel_config(self, channel_id: str, config: RateLimitConfig) -> None:
        """Set custom rate limit configuration for a channel."""
        with self._lock:
            self._configs[channel_id] = config
            
            # Update existing bucket if it exists
            if channel_id in self._buckets:
                del self._buckets[channel_id]  # Will be recreated with new config
            
            self.logger.info(f"Updated rate limit config for channel {channel_id}")
    
    def get_channel_stats(self, channel_id: str) -> Dict[str, Any]:
        """Get statistics for a specific channel."""
        with self._lock:
            bucket = self._buckets.get(channel_id)
            config = self._get_config(channel_id)
            
            stats = {
                "channel_id": channel_id,
                "available_tokens": bucket.available_tokens() if bucket else config.burst_capacity,
                "capacity": config.burst_capacity,
                "refill_rate": config.refill_rate,
                "failure_count": self._failure_counts.get(channel_id, 0),
                "in_backoff": self._is_in_backoff(channel_id),
                "backoff_remaining": max(0, self._get_backoff_time(channel_id))
            }
            
            return stats
    
    def _get_bucket(self, channel_id: str) -> TokenBucket:
        """Get or create token bucket for channel."""
        if channel_id not in self._buckets:
            config = self._get_config(channel_id)
            self._buckets[channel_id] = TokenBucket(
                capacity=config.burst_capacity,
                refill_rate=config.refill_rate
            )
            self.stats["channels_tracked"] = len(self._buckets)
        
        return self._buckets[channel_id]
    
    def _get_config(self, channel_id: str) -> RateLimitConfig:
        """Get configuration for channel."""
        return self._configs.get(channel_id, self.default_config)
    
    def _is_in_backoff(self, channel_id: str) -> bool:
        """Check if channel is in backoff period."""
        if channel_id not in self._backoff_until:
            return False
        
        return time.time() < self._backoff_until[channel_id]
    
    def _get_backoff_time(self, channel_id: str) -> float:
        """Get remaining backoff time in seconds."""
        if channel_id not in self._backoff_until:
            return 0.0
        
        remaining = self._backoff_until[channel_id] - time.time()
        return max(0.0, remaining)
    
    def cleanup_old_channels(self, inactive_hours: int = 24) -> int:
        """Clean up rate limiters for inactive channels."""
        with self._lock:
            cutoff_time = time.time() - (inactive_hours * 3600)
            channels_to_remove = []
            
            for channel_id in list(self._buckets.keys()):
                # Check if channel has been inactive
                last_activity = self._last_failure_time.get(channel_id, 0)
                
                if last_activity < cutoff_time:
                    channels_to_remove.append(channel_id)
            
            # Remove inactive channels
            for channel_id in channels_to_remove:
                self._buckets.pop(channel_id, None)
                self._configs.pop(channel_id, None)
                self._failure_counts.pop(channel_id, None)
                self._last_failure_time.pop(channel_id, None)
                self._backoff_until.pop(channel_id, None)
            
            if channels_to_remove:
                self.logger.info(f"Cleaned up {len(channels_to_remove)} inactive channel rate limiters")
                self.stats["channels_tracked"] = len(self._buckets)
            
            return len(channels_to_remove)
    
    def get_global_stats(self) -> Dict[str, Any]:
        """Get global rate limiting statistics."""
        with self._lock:
            stats = self.stats.copy()
            
            # Calculate rates
            total_requests = stats["requests_allowed"] + stats["requests_denied"]
            if total_requests > 0:
                stats["success_rate"] = stats["requests_allowed"] / total_requests
                stats["denial_rate"] = stats["requests_denied"] / total_requests
            
            # Add current state
            stats["active_channels"] = len(self._buckets)
            stats["channels_in_backoff"] = sum(1 for ch in self._buckets.keys() if self._is_in_backoff(ch))
            
            return stats
    
    def reset_stats(self) -> None:
        """Reset global statistics."""
        with self._lock:
            for key in self.stats:
                if isinstance(self.stats[key], (int, float)):
                    self.stats[key] = 0
    
    def reset_channel(self, channel_id: str) -> bool:
        """Reset rate limiting state for a specific channel."""
        with self._lock:
            reset_items = []
            
            if channel_id in self._buckets:
                # Reset bucket to full capacity
                config = self._get_config(channel_id)
                self._buckets[channel_id] = TokenBucket(
                    capacity=config.burst_capacity,
                    refill_rate=config.refill_rate
                )
                reset_items.append("bucket")
            
            if channel_id in self._failure_counts:
                del self._failure_counts[channel_id]
                reset_items.append("failure_count")
            
            if channel_id in self._backoff_until:
                del self._backoff_until[channel_id]
                reset_items.append("backoff")
            
            if channel_id in self._last_failure_time:
                del self._last_failure_time[channel_id]
                reset_items.append("failure_time")
            
            if reset_items:
                self.logger.info(f"Reset rate limiter for channel {channel_id}: {', '.join(reset_items)}")
                return True
            
            return False