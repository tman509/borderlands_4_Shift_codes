"""
Comprehensive metrics collection system for monitoring bot performance.
"""

import time
import threading
from typing import Dict, List, Any, Optional, Union, Callable
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict, deque
import logging

logger = logging.getLogger(__name__)


class MetricType(Enum):
    """Types of metrics that can be collected."""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    TIMER = "timer"
    RATE = "rate"


@dataclass
class Metric:
    """Individual metric data point."""
    name: str
    value: Union[int, float]
    metric_type: MetricType
    timestamp: datetime
    tags: Dict[str, str] = field(default_factory=dict)
    labels: Dict[str, str] = field(default_factory=dict)


@dataclass
class MetricSummary:
    """Summary statistics for a metric."""
    name: str
    metric_type: MetricType
    count: int
    sum: float
    min: float
    max: float
    avg: float
    last_value: float
    last_updated: datetime
    tags: Dict[str, str] = field(default_factory=dict)


class MetricsCollector:
    """Thread-safe metrics collector with aggregation and export capabilities."""
    
    def __init__(self, retention_hours: int = 24, max_metrics_per_type: int = 10000):
        self.retention_hours = retention_hours
        self.max_metrics_per_type = max_metrics_per_type
        
        # Thread-safe storage
        self._lock = threading.RLock()
        self._metrics: Dict[str, deque] = defaultdict(lambda: deque(maxlen=max_metrics_per_type))
        self._counters: Dict[str, float] = defaultdict(float)
        self._gauges: Dict[str, float] = defaultdict(float)
        self._timers: Dict[str, List[float]] = defaultdict(list)
        self._rates: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        
        # Metric metadata
        self._metric_types: Dict[str, MetricType] = {}
        self._metric_tags: Dict[str, Dict[str, str]] = defaultdict(dict)
        
        # Performance tracking
        self._collection_stats = {
            "metrics_collected": 0,
            "collection_errors": 0,
            "last_cleanup": datetime.now(timezone.utc)
        }
        
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    def increment(self, name: str, value: float = 1.0, tags: Optional[Dict[str, str]] = None) -> None:
        """Increment a counter metric."""
        with self._lock:
            self._counters[name] += value
            self._metric_types[name] = MetricType.COUNTER
            if tags:
                self._metric_tags[name].update(tags)
            
            self._record_metric(name, self._counters[name], MetricType.COUNTER, tags)
    
    def set_gauge(self, name: str, value: float, tags: Optional[Dict[str, str]] = None) -> None:
        """Set a gauge metric value."""
        with self._lock:
            self._gauges[name] = value
            self._metric_types[name] = MetricType.GAUGE
            if tags:
                self._metric_tags[name].update(tags)
            
            self._record_metric(name, value, MetricType.GAUGE, tags)
    
    def record_timer(self, name: str, duration: float, tags: Optional[Dict[str, str]] = None) -> None:
        """Record a timer metric (duration in seconds)."""
        with self._lock:
            self._timers[name].append(duration)
            # Keep only recent timer values
            if len(self._timers[name]) > 1000:
                self._timers[name] = self._timers[name][-1000:]
            
            self._metric_types[name] = MetricType.TIMER
            if tags:
                self._metric_tags[name].update(tags)
            
            self._record_metric(name, duration, MetricType.TIMER, tags)
    
    def record_histogram(self, name: str, value: float, tags: Optional[Dict[str, str]] = None) -> None:
        """Record a histogram metric."""
        with self._lock:
            # Store histogram values similar to timers
            if name not in self._timers:
                self._timers[name] = []
            self._timers[name].append(value)
            
            # Keep only recent values
            if len(self._timers[name]) > 1000:
                self._timers[name] = self._timers[name][-1000:]
            
            self._metric_types[name] = MetricType.HISTOGRAM
            if tags:
                self._metric_tags[name].update(tags)
            
            self._record_metric(name, value, MetricType.HISTOGRAM, tags)
    
    def record_rate(self, name: str, count: float = 1.0, tags: Optional[Dict[str, str]] = None) -> None:
        """Record a rate metric (events per second)."""
        with self._lock:
            now = time.time()
            self._rates[name].append((now, count))
            
            self._metric_types[name] = MetricType.RATE
            if tags:
                self._metric_tags[name].update(tags)
            
            # Calculate current rate (events per second over last minute)
            cutoff = now - 60  # Last minute
            recent_events = [(ts, cnt) for ts, cnt in self._rates[name] if ts > cutoff]
            
            if recent_events:
                total_count = sum(cnt for _, cnt in recent_events)
                time_span = max(1.0, now - recent_events[0][0])  # Avoid division by zero
                current_rate = total_count / time_span
            else:
                current_rate = 0.0
            
            self._record_metric(name, current_rate, MetricType.RATE, tags)
    
    def _record_metric(self, name: str, value: float, metric_type: MetricType, 
                      tags: Optional[Dict[str, str]]) -> None:
        """Record a metric data point."""
        try:
            metric = Metric(
                name=name,
                value=value,
                metric_type=metric_type,
                timestamp=datetime.now(timezone.utc),
                tags=tags or {}
            )
            
            self._metrics[name].append(metric)
            self._collection_stats["metrics_collected"] += 1
            
        except Exception as e:
            self.logger.error(f"Failed to record metric {name}: {e}")
            self._collection_stats["collection_errors"] += 1
    
    def get_metric_summary(self, name: str) -> Optional[MetricSummary]:
        """Get summary statistics for a metric."""
        with self._lock:
            if name not in self._metrics or not self._metrics[name]:
                return None
            
            metrics = list(self._metrics[name])
            values = [m.value for m in metrics]
            
            if not values:
                return None
            
            return MetricSummary(
                name=name,
                metric_type=self._metric_types.get(name, MetricType.GAUGE),
                count=len(values),
                sum=sum(values),
                min=min(values),
                max=max(values),
                avg=sum(values) / len(values),
                last_value=values[-1],
                last_updated=metrics[-1].timestamp,
                tags=self._metric_tags.get(name, {})
            )
    
    def get_all_metrics_summary(self) -> Dict[str, MetricSummary]:
        """Get summary for all metrics."""
        with self._lock:
            summaries = {}
            for name in self._metrics:
                summary = self.get_metric_summary(name)
                if summary:
                    summaries[name] = summary
            return summaries
    
    def get_recent_metrics(self, name: str, minutes: int = 5) -> List[Metric]:
        """Get recent metrics for a specific metric name."""
        with self._lock:
            if name not in self._metrics:
                return []
            
            cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
            return [m for m in self._metrics[name] if m.timestamp > cutoff]
    
    def get_counter_value(self, name: str) -> float:
        """Get current counter value."""
        with self._lock:
            return self._counters.get(name, 0.0)
    
    def get_gauge_value(self, name: str) -> float:
        """Get current gauge value."""
        with self._lock:
            return self._gauges.get(name, 0.0)
    
    def get_timer_stats(self, name: str) -> Dict[str, float]:
        """Get timer statistics."""
        with self._lock:
            if name not in self._timers or not self._timers[name]:
                return {}
            
            values = self._timers[name]
            return {
                "count": len(values),
                "sum": sum(values),
                "min": min(values),
                "max": max(values),
                "avg": sum(values) / len(values),
                "p50": self._percentile(values, 50),
                "p95": self._percentile(values, 95),
                "p99": self._percentile(values, 99)
            }
    
    def get_rate_value(self, name: str, window_seconds: int = 60) -> float:
        """Get current rate (events per second)."""
        with self._lock:
            if name not in self._rates:
                return 0.0
            
            now = time.time()
            cutoff = now - window_seconds
            recent_events = [(ts, cnt) for ts, cnt in self._rates[name] if ts > cutoff]
            
            if not recent_events:
                return 0.0
            
            total_count = sum(cnt for _, cnt in recent_events)
            time_span = max(1.0, now - recent_events[0][0])
            return total_count / time_span
    
    def _percentile(self, values: List[float], percentile: int) -> float:
        """Calculate percentile of values."""
        if not values:
            return 0.0
        
        sorted_values = sorted(values)
        index = int((percentile / 100.0) * len(sorted_values))
        index = min(index, len(sorted_values) - 1)
        return sorted_values[index]
    
    def cleanup_old_metrics(self) -> None:
        """Clean up old metrics beyond retention period."""
        with self._lock:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=self.retention_hours)
            
            for name in list(self._metrics.keys()):
                # Filter out old metrics
                old_deque = self._metrics[name]
                new_deque = deque(
                    (m for m in old_deque if m.timestamp > cutoff),
                    maxlen=self.max_metrics_per_type
                )
                self._metrics[name] = new_deque
                
                # Remove empty metric collections
                if not new_deque:
                    del self._metrics[name]
                    self._metric_types.pop(name, None)
                    self._metric_tags.pop(name, None)
            
            # Clean up timer data
            for name in list(self._timers.keys()):
                if name not in self._metrics:
                    del self._timers[name]
            
            # Clean up rate data
            rate_cutoff = time.time() - (self.retention_hours * 3600)
            for name in list(self._rates.keys()):
                old_deque = self._rates[name]
                new_deque = deque(
                    ((ts, cnt) for ts, cnt in old_deque if ts > rate_cutoff),
                    maxlen=1000
                )
                self._rates[name] = new_deque
                
                if not new_deque and name not in self._metrics:
                    del self._rates[name]
            
            self._collection_stats["last_cleanup"] = datetime.now(timezone.utc)
            self.logger.debug("Completed metrics cleanup")
    
    def export_metrics(self, format_type: str = "json") -> Union[str, Dict[str, Any]]:
        """Export metrics in specified format."""
        with self._lock:
            if format_type == "json":
                return self._export_json()
            elif format_type == "prometheus":
                return self._export_prometheus()
            else:
                raise ValueError(f"Unsupported export format: {format_type}")
    
    def _export_json(self) -> Dict[str, Any]:
        """Export metrics as JSON."""
        export_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "collection_stats": self._collection_stats.copy(),
            "metrics": {}
        }
        
        # Export summaries
        for name, summary in self.get_all_metrics_summary().items():
            export_data["metrics"][name] = {
                "type": summary.metric_type.value,
                "count": summary.count,
                "sum": summary.sum,
                "min": summary.min,
                "max": summary.max,
                "avg": summary.avg,
                "last_value": summary.last_value,
                "last_updated": summary.last_updated.isoformat(),
                "tags": summary.tags
            }
            
            # Add type-specific data
            if summary.metric_type == MetricType.TIMER:
                timer_stats = self.get_timer_stats(name)
                export_data["metrics"][name]["percentiles"] = {
                    "p50": timer_stats.get("p50", 0),
                    "p95": timer_stats.get("p95", 0),
                    "p99": timer_stats.get("p99", 0)
                }
            elif summary.metric_type == MetricType.RATE:
                export_data["metrics"][name]["rate_per_second"] = self.get_rate_value(name)
        
        return export_data
    
    def _export_prometheus(self) -> str:
        """Export metrics in Prometheus format."""
        lines = []
        
        for name, summary in self.get_all_metrics_summary().items():
            # Sanitize metric name for Prometheus
            prom_name = name.replace("-", "_").replace(".", "_")
            
            # Add help and type
            lines.append(f"# HELP {prom_name} {summary.metric_type.value} metric")
            lines.append(f"# TYPE {prom_name} {summary.metric_type.value}")
            
            # Add tags
            tag_str = ""
            if summary.tags:
                tag_pairs = [f'{k}="{v}"' for k, v in summary.tags.items()]
                tag_str = "{" + ",".join(tag_pairs) + "}"
            
            # Add metric value
            if summary.metric_type in [MetricType.COUNTER, MetricType.GAUGE]:
                lines.append(f"{prom_name}{tag_str} {summary.last_value}")
            elif summary.metric_type == MetricType.TIMER:
                # Export timer as histogram
                timer_stats = self.get_timer_stats(name)
                lines.append(f"{prom_name}_count{tag_str} {timer_stats.get('count', 0)}")
                lines.append(f"{prom_name}_sum{tag_str} {timer_stats.get('sum', 0)}")
                
                # Add percentiles
                for p in [50, 95, 99]:
                    pval = timer_stats.get(f"p{p}", 0)
                    lines.append(f"{prom_name}{{quantile=\"0.{p:02d}\"{tag_str[1:] if tag_str else ''}} {pval}")
        
        return "\n".join(lines)
    
    def reset_metrics(self) -> None:
        """Reset all metrics (useful for testing)."""
        with self._lock:
            self._metrics.clear()
            self._counters.clear()
            self._gauges.clear()
            self._timers.clear()
            self._rates.clear()
            self._metric_types.clear()
            self._metric_tags.clear()
            
            self._collection_stats = {
                "metrics_collected": 0,
                "collection_errors": 0,
                "last_cleanup": datetime.now(timezone.utc)
            }
    
    def get_collection_stats(self) -> Dict[str, Any]:
        """Get metrics collection statistics."""
        with self._lock:
            stats = self._collection_stats.copy()
            stats.update({
                "total_metric_types": len(self._metrics),
                "total_data_points": sum(len(deque_obj) for deque_obj in self._metrics.values()),
                "memory_usage_estimate": self._estimate_memory_usage()
            })
            return stats
    
    def _estimate_memory_usage(self) -> Dict[str, int]:
        """Estimate memory usage of stored metrics."""
        # Rough estimation
        metric_count = sum(len(deque_obj) for deque_obj in self._metrics.values())
        timer_count = sum(len(values) for values in self._timers.values())
        rate_count = sum(len(deque_obj) for deque_obj in self._rates.values())
        
        # Rough bytes per metric (very approximate)
        bytes_per_metric = 200  # JSON overhead, timestamp, etc.
        
        return {
            "metrics_bytes": metric_count * bytes_per_metric,
            "timers_bytes": timer_count * 8,  # float64
            "rates_bytes": rate_count * 16,   # timestamp + count
            "total_estimated_bytes": (metric_count * bytes_per_metric) + (timer_count * 8) + (rate_count * 16)
        }


# Decorator for automatic timing
def timed_metric(metrics_collector: MetricsCollector, metric_name: Optional[str] = None):
    """Decorator to automatically time function execution."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            name = metric_name or f"{func.__module__}.{func.__name__}"
            start_time = time.time()
            
            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time
                metrics_collector.record_timer(name, duration, tags={"status": "success"})
                return result
            except Exception as e:
                duration = time.time() - start_time
                metrics_collector.record_timer(name, duration, tags={"status": "error"})
                metrics_collector.increment(f"{name}.errors", tags={"error_type": type(e).__name__})
                raise
        
        return wrapper
    return decorator