"""
Comprehensive health monitoring system for the Shift Code Bot.
"""

import time
import threading
from typing import Dict, List, Any, Optional, Callable, Union
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """Health status levels."""
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


@dataclass
class HealthCheck:
    """Individual health check result."""
    name: str
    status: HealthStatus
    message: str
    timestamp: datetime
    duration_ms: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "status": self.status.value,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "duration_ms": self.duration_ms,
            "metadata": self.metadata
        }


@dataclass
class HealthCheckConfig:
    """Configuration for a health check."""
    name: str
    check_function: Callable[[], HealthCheck]
    interval_seconds: int = 60
    timeout_seconds: int = 30
    enabled: bool = True
    critical: bool = False  # Whether failure makes overall system critical


class HealthMonitor:
    """Comprehensive health monitoring system with periodic checks and alerting."""
    
    def __init__(self, check_interval: int = 60, history_retention_hours: int = 24):
        self.check_interval = check_interval
        self.history_retention_hours = history_retention_hours
        
        # Thread safety
        self._lock = threading.RLock()
        
        # Health checks registry
        self._health_checks: Dict[str, HealthCheckConfig] = {}
        
        # Health check results
        self._current_status: Dict[str, HealthCheck] = {}
        self._health_history: Dict[str, List[HealthCheck]] = {}
        
        # Monitoring thread
        self._monitoring_thread: Optional[threading.Thread] = None
        self._stop_monitoring = threading.Event()
        self._running = False
        
        # Statistics
        self._stats = {
            "total_checks_run": 0,
            "failed_checks": 0,
            "last_check_time": None,
            "monitoring_started": None
        }
        
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    def register_health_check(self, 
                            name: str,
                            check_function: Callable[[], HealthCheck],
                            interval_seconds: int = 60,
                            timeout_seconds: int = 30,
                            enabled: bool = True,
                            critical: bool = False) -> None:
        """Register a health check."""
        with self._lock:
            config = HealthCheckConfig(
                name=name,
                check_function=check_function,
                interval_seconds=interval_seconds,
                timeout_seconds=timeout_seconds,
                enabled=enabled,
                critical=critical
            )
            
            self._health_checks[name] = config
            self.logger.info(f"Registered health check: {name}")
    
    def unregister_health_check(self, name: str) -> None:
        """Unregister a health check."""
        with self._lock:
            if name in self._health_checks:
                del self._health_checks[name]
                self._current_status.pop(name, None)
                self._health_history.pop(name, None)
                self.logger.info(f"Unregistered health check: {name}")
    
    def run_health_check(self, name: str) -> Optional[HealthCheck]:
        """Run a specific health check manually."""
        with self._lock:
            if name not in self._health_checks:
                self.logger.warning(f"Health check not found: {name}")
                return None
            
            config = self._health_checks[name]
            if not config.enabled:
                self.logger.debug(f"Health check disabled: {name}")
                return None
            
            return self._execute_health_check(config)
    
    def run_all_health_checks(self) -> Dict[str, HealthCheck]:
        """Run all enabled health checks."""
        results = {}
        
        with self._lock:
            for name, config in self._health_checks.items():
                if config.enabled:
                    try:
                        result = self._execute_health_check(config)
                        if result:
                            results[name] = result
                    except Exception as e:
                        self.logger.error(f"Failed to run health check {name}: {e}")
                        # Create error result
                        results[name] = HealthCheck(
                            name=name,
                            status=HealthStatus.CRITICAL,
                            message=f"Health check execution failed: {str(e)}",
                            timestamp=datetime.now(timezone.utc),
                            duration_ms=0.0
                        )
        
        return results
    
    def _execute_health_check(self, config: HealthCheckConfig) -> Optional[HealthCheck]:
        """Execute a single health check with timeout."""
        start_time = time.time()
        
        try:
            # Simple timeout implementation (could be enhanced with threading.Timer)
            result = config.check_function()
            
            # Ensure result has correct timestamp and duration
            if not result.timestamp:
                result.timestamp = datetime.now(timezone.utc)
            
            duration_ms = (time.time() - start_time) * 1000
            result.duration_ms = duration_ms
            
            # Store result
            self._current_status[config.name] = result
            
            # Add to history
            if config.name not in self._health_history:
                self._health_history[config.name] = []
            
            self._health_history[config.name].append(result)
            
            # Limit history size
            max_history = int((self.history_retention_hours * 3600) / config.interval_seconds)
            if len(self._health_history[config.name]) > max_history:
                self._health_history[config.name] = self._health_history[config.name][-max_history:]
            
            # Update statistics
            self._stats["total_checks_run"] += 1
            if result.status in [HealthStatus.CRITICAL, HealthStatus.WARNING]:
                self._stats["failed_checks"] += 1
            
            self.logger.debug(f"Health check {config.name}: {result.status.value} - {result.message}")
            return result
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            
            error_result = HealthCheck(
                name=config.name,
                status=HealthStatus.CRITICAL,
                message=f"Health check failed: {str(e)}",
                timestamp=datetime.now(timezone.utc),
                duration_ms=duration_ms
            )
            
            self._current_status[config.name] = error_result
            self._stats["total_checks_run"] += 1
            self._stats["failed_checks"] += 1
            
            self.logger.error(f"Health check {config.name} failed: {e}")
            return error_result
    
    def get_overall_health(self) -> Dict[str, Any]:
        """Get overall system health status."""
        with self._lock:
            if not self._current_status:
                return {
                    "status": HealthStatus.UNKNOWN.value,
                    "message": "No health checks have been run",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "checks": {},
                    "summary": {
                        "total": 0,
                        "healthy": 0,
                        "warning": 0,
                        "critical": 0,
                        "unknown": 0
                    }
                }
            
            # Calculate overall status
            statuses = [check.status for check in self._current_status.values()]
            
            # Count by status
            summary = {
                "total": len(statuses),
                "healthy": sum(1 for s in statuses if s == HealthStatus.HEALTHY),
                "warning": sum(1 for s in statuses if s == HealthStatus.WARNING),
                "critical": sum(1 for s in statuses if s == HealthStatus.CRITICAL),
                "unknown": sum(1 for s in statuses if s == HealthStatus.UNKNOWN)
            }
            
            # Determine overall status
            if summary["critical"] > 0:
                overall_status = HealthStatus.CRITICAL
                message = f"{summary['critical']} critical issue(s) detected"
            elif summary["warning"] > 0:
                overall_status = HealthStatus.WARNING
                message = f"{summary['warning']} warning(s) detected"
            elif summary["unknown"] > 0:
                overall_status = HealthStatus.WARNING
                message = f"{summary['unknown']} check(s) in unknown state"
            else:
                overall_status = HealthStatus.HEALTHY
                message = "All systems healthy"
            
            # Get latest timestamp
            latest_timestamp = max(
                (check.timestamp for check in self._current_status.values()),
                default=datetime.now(timezone.utc)
            )
            
            return {
                "status": overall_status.value,
                "message": message,
                "timestamp": latest_timestamp.isoformat(),
                "checks": {name: check.to_dict() for name, check in self._current_status.items()},
                "summary": summary,
                "monitoring_stats": self.get_monitoring_stats()
            }
    
    def get_health_check_status(self, name: str) -> Optional[HealthCheck]:
        """Get current status of a specific health check."""
        with self._lock:
            return self._current_status.get(name)
    
    def get_health_check_history(self, name: str, hours: int = 1) -> List[HealthCheck]:
        """Get health check history for a specific check."""
        with self._lock:
            if name not in self._health_history:
                return []
            
            cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
            return [
                check for check in self._health_history[name]
                if check.timestamp > cutoff
            ]
    
    def start_monitoring(self) -> None:
        """Start continuous health monitoring."""
        if self._running:
            self.logger.warning("Health monitoring is already running")
            return
        
        self._running = True
        self._stop_monitoring.clear()
        self._stats["monitoring_started"] = datetime.now(timezone.utc)
        
        self._monitoring_thread = threading.Thread(
            target=self._monitoring_loop,
            name="HealthMonitor",
            daemon=True
        )
        self._monitoring_thread.start()
        
        self.logger.info("Health monitoring started")
    
    def stop_monitoring(self) -> None:
        """Stop continuous health monitoring."""
        if not self._running:
            return
        
        self._running = False
        self._stop_monitoring.set()
        
        if self._monitoring_thread and self._monitoring_thread.is_alive():
            self._monitoring_thread.join(timeout=5.0)
        
        self.logger.info("Health monitoring stopped")
    
    def _monitoring_loop(self) -> None:
        """Main monitoring loop."""
        self.logger.info("Health monitoring loop started")
        
        while not self._stop_monitoring.is_set():
            try:
                # Run all health checks
                self.run_all_health_checks()
                self._stats["last_check_time"] = datetime.now(timezone.utc)
                
                # Clean up old history
                self._cleanup_old_history()
                
                # Wait for next check interval
                self._stop_monitoring.wait(self.check_interval)
                
            except Exception as e:
                self.logger.error(f"Error in health monitoring loop: {e}")
                # Continue monitoring even if there's an error
                self._stop_monitoring.wait(min(self.check_interval, 60))
        
        self.logger.info("Health monitoring loop stopped")
    
    def _cleanup_old_history(self) -> None:
        """Clean up old health check history."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=self.history_retention_hours)
        
        with self._lock:
            for name in list(self._health_history.keys()):
                old_history = self._health_history[name]
                new_history = [check for check in old_history if check.timestamp > cutoff]
                
                if new_history:
                    self._health_history[name] = new_history
                else:
                    # Keep at least the last check
                    if old_history:
                        self._health_history[name] = [old_history[-1]]
    
    def get_monitoring_stats(self) -> Dict[str, Any]:
        """Get health monitoring statistics."""
        with self._lock:
            stats = self._stats.copy()
            
            # Convert datetime objects to ISO strings
            if stats["last_check_time"]:
                stats["last_check_time"] = stats["last_check_time"].isoformat()
            if stats["monitoring_started"]:
                stats["monitoring_started"] = stats["monitoring_started"].isoformat()
            
            # Add current state info
            stats.update({
                "is_running": self._running,
                "registered_checks": len(self._health_checks),
                "enabled_checks": sum(1 for config in self._health_checks.values() if config.enabled),
                "current_results": len(self._current_status)
            })
            
            return stats
    
    def create_database_health_check(self, database) -> Callable[[], HealthCheck]:
        """Create a health check for database connectivity."""
        def check_database():
            try:
                health_info = database.health_check()
                
                if health_info.get("status") == "healthy":
                    return HealthCheck(
                        name="database",
                        status=HealthStatus.HEALTHY,
                        message="Database connection healthy",
                        timestamp=datetime.now(timezone.utc),
                        duration_ms=0.0,
                        metadata=health_info
                    )
                else:
                    return HealthCheck(
                        name="database",
                        status=HealthStatus.CRITICAL,
                        message=f"Database unhealthy: {health_info.get('error', 'Unknown error')}",
                        timestamp=datetime.now(timezone.utc),
                        duration_ms=0.0,
                        metadata=health_info
                    )
            
            except Exception as e:
                return HealthCheck(
                    name="database",
                    status=HealthStatus.CRITICAL,
                    message=f"Database check failed: {str(e)}",
                    timestamp=datetime.now(timezone.utc),
                    duration_ms=0.0
                )
        
        return check_database
    
    def create_fetcher_health_check(self, fetcher) -> Callable[[], HealthCheck]:
        """Create a health check for a fetcher."""
        def check_fetcher():
            try:
                health_info = fetcher.health_check()
                
                connectivity = health_info.get("connectivity", "unknown")
                
                if connectivity == "ok":
                    status = HealthStatus.HEALTHY
                    message = f"Fetcher {fetcher.name} healthy"
                elif connectivity == "failed":
                    status = HealthStatus.WARNING
                    message = f"Fetcher {fetcher.name} connectivity issues"
                elif connectivity == "disabled":
                    status = HealthStatus.WARNING
                    message = f"Fetcher {fetcher.name} disabled"
                else:
                    status = HealthStatus.UNKNOWN
                    message = f"Fetcher {fetcher.name} status unknown"
                
                return HealthCheck(
                    name=f"fetcher_{fetcher.name}",
                    status=status,
                    message=message,
                    timestamp=datetime.now(timezone.utc),
                    duration_ms=0.0,
                    metadata=health_info
                )
            
            except Exception as e:
                return HealthCheck(
                    name=f"fetcher_{fetcher.name}",
                    status=HealthStatus.CRITICAL,
                    message=f"Fetcher check failed: {str(e)}",
                    timestamp=datetime.now(timezone.utc),
                    duration_ms=0.0
                )
        
        return check_fetcher
    
    def create_memory_health_check(self, warning_mb: int = 500, critical_mb: int = 1000) -> Callable[[], HealthCheck]:
        """Create a health check for memory usage."""
        def check_memory():
            try:
                import psutil
                process = psutil.Process()
                memory_mb = process.memory_info().rss / 1024 / 1024
                
                if memory_mb > critical_mb:
                    status = HealthStatus.CRITICAL
                    message = f"High memory usage: {memory_mb:.1f}MB (critical threshold: {critical_mb}MB)"
                elif memory_mb > warning_mb:
                    status = HealthStatus.WARNING
                    message = f"Elevated memory usage: {memory_mb:.1f}MB (warning threshold: {warning_mb}MB)"
                else:
                    status = HealthStatus.HEALTHY
                    message = f"Memory usage normal: {memory_mb:.1f}MB"
                
                return HealthCheck(
                    name="memory",
                    status=status,
                    message=message,
                    timestamp=datetime.now(timezone.utc),
                    duration_ms=0.0,
                    metadata={"memory_mb": memory_mb, "warning_mb": warning_mb, "critical_mb": critical_mb}
                )
            
            except ImportError:
                return HealthCheck(
                    name="memory",
                    status=HealthStatus.UNKNOWN,
                    message="psutil not available for memory monitoring",
                    timestamp=datetime.now(timezone.utc),
                    duration_ms=0.0
                )
            except Exception as e:
                return HealthCheck(
                    name="memory",
                    status=HealthStatus.CRITICAL,
                    message=f"Memory check failed: {str(e)}",
                    timestamp=datetime.now(timezone.utc),
                    duration_ms=0.0
                )
        
        return check_memory