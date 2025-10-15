"""
Performance tracking and analysis for the Shift Code Bot.
"""

import time
import threading
from typing import Dict, List, Any, Optional, Callable
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from collections import defaultdict, deque
import logging

logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetric:
    """Individual performance measurement."""
    operation: str
    duration_seconds: float
    timestamp: datetime
    success: bool
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "operation": self.operation,
            "duration_seconds": self.duration_seconds,
            "timestamp": self.timestamp.isoformat(),
            "success": self.success,
            "metadata": self.metadata
        }


@dataclass
class PerformanceStats:
    """Aggregated performance statistics."""
    operation: str
    total_calls: int
    successful_calls: int
    failed_calls: int
    success_rate: float
    avg_duration: float
    min_duration: float
    max_duration: float
    p50_duration: float
    p95_duration: float
    p99_duration: float
    total_duration: float
    calls_per_second: float
    last_updated: datetime


class PerformanceTracker:
    """Comprehensive performance tracking with statistical analysis."""
    
    def __init__(self, retention_hours: int = 24, max_samples_per_operation: int = 10000):
        self.retention_hours = retention_hours
        self.max_samples_per_operation = max_samples_per_operation
        
        # Thread safety
        self._lock = threading.RLock()
        
        # Performance data storage
        self._metrics: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=max_samples_per_operation)
        )
        
        # Cached statistics (updated periodically)
        self._cached_stats: Dict[str, PerformanceStats] = {}
        self._stats_cache_time: Dict[str, datetime] = {}
        self._cache_ttl_seconds = 60  # Cache stats for 1 minute
        
        # Global statistics
        self._global_stats = {
            "total_operations": 0,
            "total_duration": 0.0,
            "start_time": datetime.now(timezone.utc)
        }
        
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    def record_operation(self, 
                        operation: str, 
                        duration_seconds: float, 
                        success: bool = True,
                        metadata: Optional[Dict[str, Any]] = None) -> None:
        """Record a performance metric for an operation."""
        
        metric = PerformanceMetric(
            operation=operation,
            duration_seconds=duration_seconds,
            timestamp=datetime.now(timezone.utc),
            success=success,
            metadata=metadata or {}
        )
        
        with self._lock:
            self._metrics[operation].append(metric)
            
            # Update global stats
            self._global_stats["total_operations"] += 1
            self._global_stats["total_duration"] += duration_seconds
            
            # Invalidate cached stats for this operation
            if operation in self._cached_stats:
                del self._cached_stats[operation]
                del self._stats_cache_time[operation]
    
    def get_operation_stats(self, operation: str, force_refresh: bool = False) -> Optional[PerformanceStats]:
        """Get performance statistics for a specific operation."""
        
        with self._lock:
            if operation not in self._metrics or not self._metrics[operation]:
                return None
            
            # Check cache
            if not force_refresh and operation in self._cached_stats:
                cache_time = self._stats_cache_time[operation]
                if (datetime.now(timezone.utc) - cache_time).total_seconds() < self._cache_ttl_seconds:
                    return self._cached_stats[operation]
            
            # Calculate fresh statistics
            metrics = list(self._metrics[operation])
            
            if not metrics:
                return None
            
            # Basic counts
            total_calls = len(metrics)
            successful_calls = sum(1 for m in metrics if m.success)
            failed_calls = total_calls - successful_calls
            success_rate = successful_calls / total_calls if total_calls > 0 else 0.0
            
            # Duration statistics
            durations = [m.duration_seconds for m in metrics]
            total_duration = sum(durations)
            avg_duration = total_duration / len(durations)
            min_duration = min(durations)
            max_duration = max(durations)
            
            # Percentiles
            sorted_durations = sorted(durations)
            p50_duration = self._percentile(sorted_durations, 50)
            p95_duration = self._percentile(sorted_durations, 95)
            p99_duration = self._percentile(sorted_durations, 99)
            
            # Rate calculation (calls per second over the time window)
            if len(metrics) > 1:
                time_span = (metrics[-1].timestamp - metrics[0].timestamp).total_seconds()
                calls_per_second = len(metrics) / max(time_span, 1.0)
            else:
                calls_per_second = 0.0
            
            stats = PerformanceStats(
                operation=operation,
                total_calls=total_calls,
                successful_calls=successful_calls,
                failed_calls=failed_calls,
                success_rate=success_rate,
                avg_duration=avg_duration,
                min_duration=min_duration,
                max_duration=max_duration,
                p50_duration=p50_duration,
                p95_duration=p95_duration,
                p99_duration=p99_duration,
                total_duration=total_duration,
                calls_per_second=calls_per_second,
                last_updated=datetime.now(timezone.utc)
            )
            
            # Cache the results
            self._cached_stats[operation] = stats
            self._stats_cache_time[operation] = datetime.now(timezone.utc)
            
            return stats
    
    def get_all_operations_stats(self) -> Dict[str, PerformanceStats]:
        """Get performance statistics for all tracked operations."""
        with self._lock:
            stats = {}
            for operation in self._metrics:
                operation_stats = self.get_operation_stats(operation)
                if operation_stats:
                    stats[operation] = operation_stats
            return stats
    
    def get_recent_metrics(self, operation: str, minutes: int = 5) -> List[PerformanceMetric]:
        """Get recent metrics for a specific operation."""
        with self._lock:
            if operation not in self._metrics:
                return []
            
            cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
            return [m for m in self._metrics[operation] if m.timestamp > cutoff]
    
    def get_slow_operations(self, threshold_seconds: float = 1.0, limit: int = 10) -> List[PerformanceMetric]:
        """Get the slowest operations above the threshold."""
        slow_ops = []
        
        with self._lock:
            for operation_metrics in self._metrics.values():
                for metric in operation_metrics:
                    if metric.duration_seconds > threshold_seconds:
                        slow_ops.append(metric)
        
        # Sort by duration (slowest first) and limit results
        slow_ops.sort(key=lambda x: x.duration_seconds, reverse=True)
        return slow_ops[:limit]
    
    def get_failed_operations(self, hours: int = 1, limit: int = 50) -> List[PerformanceMetric]:
        """Get recent failed operations."""
        failed_ops = []
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        
        with self._lock:
            for operation_metrics in self._metrics.values():
                for metric in operation_metrics:
                    if not metric.success and metric.timestamp > cutoff:
                        failed_ops.append(metric)
        
        # Sort by timestamp (most recent first) and limit results
        failed_ops.sort(key=lambda x: x.timestamp, reverse=True)
        return failed_ops[:limit]
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """Get overall performance summary."""
        with self._lock:
            now = datetime.now(timezone.utc)
            uptime_seconds = (now - self._global_stats["start_time"]).total_seconds()
            
            # Calculate overall statistics
            all_stats = self.get_all_operations_stats()
            
            total_calls = sum(stats.total_calls for stats in all_stats.values())
            total_successful = sum(stats.successful_calls for stats in all_stats.values())
            total_failed = sum(stats.failed_calls for stats in all_stats.values())
            
            overall_success_rate = total_successful / total_calls if total_calls > 0 else 0.0
            overall_calls_per_second = total_calls / max(uptime_seconds, 1.0)
            
            # Find top operations by various metrics
            top_by_calls = sorted(all_stats.values(), key=lambda x: x.total_calls, reverse=True)[:5]
            top_by_duration = sorted(all_stats.values(), key=lambda x: x.avg_duration, reverse=True)[:5]
            
            return {
                "uptime_seconds": uptime_seconds,
                "total_operations_tracked": len(all_stats),
                "total_calls": total_calls,
                "total_successful_calls": total_successful,
                "total_failed_calls": total_failed,
                "overall_success_rate": overall_success_rate,
                "overall_calls_per_second": overall_calls_per_second,
                "total_duration_seconds": self._global_stats["total_duration"],
                "top_operations_by_calls": [
                    {"operation": s.operation, "calls": s.total_calls} for s in top_by_calls
                ],
                "top_operations_by_avg_duration": [
                    {"operation": s.operation, "avg_duration": s.avg_duration} for s in top_by_duration
                ],
                "last_updated": now.isoformat()
            }
    
    def cleanup_old_metrics(self) -> None:
        """Clean up old performance metrics beyond retention period."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=self.retention_hours)
        
        with self._lock:
            for operation in list(self._metrics.keys()):
                old_deque = self._metrics[operation]
                
                # Filter out old metrics
                new_metrics = [m for m in old_deque if m.timestamp > cutoff]
                
                if new_metrics:
                    # Create new deque with filtered metrics
                    new_deque = deque(new_metrics, maxlen=self.max_samples_per_operation)
                    self._metrics[operation] = new_deque
                else:
                    # Remove empty operation
                    del self._metrics[operation]
                
                # Invalidate cached stats
                if operation in self._cached_stats:
                    del self._cached_stats[operation]
                    del self._stats_cache_time[operation]
            
            self.logger.debug("Completed performance metrics cleanup")
    
    def _percentile(self, sorted_values: List[float], percentile: int) -> float:
        """Calculate percentile of sorted values."""
        if not sorted_values:
            return 0.0
        
        index = int((percentile / 100.0) * len(sorted_values))
        index = min(index, len(sorted_values) - 1)
        return sorted_values[index]
    
    def export_performance_data(self, format_type: str = "json") -> Dict[str, Any]:
        """Export performance data for external analysis."""
        with self._lock:
            if format_type == "json":
                return {
                    "summary": self.get_performance_summary(),
                    "operations": {
                        name: {
                            "stats": stats.__dict__,
                            "recent_metrics": [
                                m.to_dict() for m in self.get_recent_metrics(name, minutes=60)
                            ]
                        }
                        for name, stats in self.get_all_operations_stats().items()
                    },
                    "slow_operations": [m.to_dict() for m in self.get_slow_operations()],
                    "failed_operations": [m.to_dict() for m in self.get_failed_operations()],
                    "export_timestamp": datetime.now(timezone.utc).isoformat()
                }
            else:
                raise ValueError(f"Unsupported export format: {format_type}")
    
    def reset_metrics(self) -> None:
        """Reset all performance metrics (useful for testing)."""
        with self._lock:
            self._metrics.clear()
            self._cached_stats.clear()
            self._stats_cache_time.clear()
            
            self._global_stats = {
                "total_operations": 0,
                "total_duration": 0.0,
                "start_time": datetime.now(timezone.utc)
            }
    
    def get_operation_trend(self, operation: str, hours: int = 24, bucket_minutes: int = 60) -> List[Dict[str, Any]]:
        """Get performance trend for an operation over time."""
        with self._lock:
            if operation not in self._metrics:
                return []
            
            cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
            recent_metrics = [m for m in self._metrics[operation] if m.timestamp > cutoff]
            
            if not recent_metrics:
                return []
            
            # Create time buckets
            bucket_size = timedelta(minutes=bucket_minutes)
            start_time = cutoff
            buckets = []
            
            current_time = start_time
            while current_time < datetime.now(timezone.utc):
                bucket_end = current_time + bucket_size
                
                # Get metrics in this bucket
                bucket_metrics = [
                    m for m in recent_metrics 
                    if current_time <= m.timestamp < bucket_end
                ]
                
                if bucket_metrics:
                    durations = [m.duration_seconds for m in bucket_metrics]
                    successful = sum(1 for m in bucket_metrics if m.success)
                    
                    buckets.append({
                        "timestamp": current_time.isoformat(),
                        "count": len(bucket_metrics),
                        "successful": successful,
                        "failed": len(bucket_metrics) - successful,
                        "success_rate": successful / len(bucket_metrics),
                        "avg_duration": sum(durations) / len(durations),
                        "min_duration": min(durations),
                        "max_duration": max(durations)
                    })
                else:
                    buckets.append({
                        "timestamp": current_time.isoformat(),
                        "count": 0,
                        "successful": 0,
                        "failed": 0,
                        "success_rate": 0.0,
                        "avg_duration": 0.0,
                        "min_duration": 0.0,
                        "max_duration": 0.0
                    })
                
                current_time = bucket_end
            
            return buckets


# Context manager for automatic performance tracking
class PerformanceContext:
    """Context manager for tracking operation performance."""
    
    def __init__(self, tracker: PerformanceTracker, operation: str, metadata: Optional[Dict[str, Any]] = None):
        self.tracker = tracker
        self.operation = operation
        self.metadata = metadata or {}
        self.start_time = None
        self.success = True
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self.start_time
        
        # Mark as failed if exception occurred
        if exc_type is not None:
            self.success = False
            self.metadata["error_type"] = exc_type.__name__
            self.metadata["error_message"] = str(exc_val)
        
        self.tracker.record_operation(
            operation=self.operation,
            duration_seconds=duration,
            success=self.success,
            metadata=self.metadata
        )
    
    def mark_failed(self, reason: str = "Manual failure") -> None:
        """Manually mark the operation as failed."""
        self.success = False
        self.metadata["failure_reason"] = reason


# Decorator for automatic performance tracking
def track_performance(tracker: PerformanceTracker, operation_name: Optional[str] = None):
    """Decorator to automatically track function performance."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            op_name = operation_name or f"{func.__module__}.{func.__name__}"
            
            with PerformanceContext(tracker, op_name) as ctx:
                try:
                    result = func(*args, **kwargs)
                    return result
                except Exception as e:
                    # Exception will be automatically recorded by context manager
                    raise
        
        return wrapper
    return decorator