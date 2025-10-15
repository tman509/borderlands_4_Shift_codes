"""
Comprehensive alerting system with failure detection and notification.
"""

import time
import threading
from typing import Dict, List, Any, Optional, Callable, Union
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from enum import Enum
import logging
import requests

from .health_monitor import HealthStatus, HealthCheck
from .metrics_collector import MetricsCollector

logger = logging.getLogger(__name__)


class AlertSeverity(Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertStatus(Enum):
    """Alert status."""
    ACTIVE = "active"
    RESOLVED = "resolved"
    SUPPRESSED = "suppressed"


@dataclass
class Alert:
    """Individual alert."""
    id: str
    name: str
    severity: AlertSeverity
    message: str
    timestamp: datetime
    status: AlertStatus = AlertStatus.ACTIVE
    metadata: Dict[str, Any] = field(default_factory=dict)
    resolved_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "name": self.name,
            "severity": self.severity.value,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "status": self.status.value,
            "metadata": self.metadata,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None
        }


@dataclass
class AlertRule:
    """Alert rule configuration."""
    name: str
    condition_function: Callable[[], bool]
    severity: AlertSeverity
    message_template: str
    cooldown_minutes: int = 60
    enabled: bool = True
    auto_resolve: bool = True
    resolve_condition: Optional[Callable[[], bool]] = None


class AlertManager:
    """Comprehensive alert management with deduplication and routing."""
    
    def __init__(self, 
                 webhook_url: Optional[str] = None,
                 default_cooldown_minutes: int = 60):
        
        self.webhook_url = webhook_url
        self.default_cooldown_minutes = default_cooldown_minutes
        
        # Thread safety
        self._lock = threading.RLock()
        
        # Alert storage
        self._active_alerts: Dict[str, Alert] = {}
        self._alert_history: List[Alert] = []
        self._alert_rules: Dict[str, AlertRule] = {}
        
        # Cooldown tracking
        self._last_alert_time: Dict[str, datetime] = {}
        
        # Notification handlers
        self._notification_handlers: List[Callable[[Alert], None]] = []
        
        # Statistics
        self._stats = {
            "total_alerts": 0,
            "active_alerts": 0,
            "resolved_alerts": 0,
            "suppressed_alerts": 0,
            "notifications_sent": 0,
            "notification_failures": 0
        }
        
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        
        # Add default webhook handler if URL provided
        if webhook_url:
            self.add_notification_handler(self._webhook_notification_handler)
    
    def add_alert_rule(self, rule: AlertRule) -> None:
        """Add an alert rule."""
        with self._lock:
            self._alert_rules[rule.name] = rule
            self.logger.info(f"Added alert rule: {rule.name}")
    
    def remove_alert_rule(self, name: str) -> None:
        """Remove an alert rule."""
        with self._lock:
            if name in self._alert_rules:
                del self._alert_rules[name]
                self.logger.info(f"Removed alert rule: {name}")
    
    def add_notification_handler(self, handler: Callable[[Alert], None]) -> None:
        """Add a notification handler."""
        self._notification_handlers.append(handler)
        self.logger.info(f"Added notification handler: {handler.__name__}")
    
    def check_alert_rules(self) -> List[Alert]:
        """Check all alert rules and generate alerts."""
        new_alerts = []
        
        with self._lock:
            for rule_name, rule in self._alert_rules.items():
                if not rule.enabled:
                    continue
                
                try:
                    # Check if we're in cooldown period
                    if self._is_in_cooldown(rule_name, rule.cooldown_minutes):
                        continue
                    
                    # Evaluate condition
                    if rule.condition_function():
                        alert = self._create_alert(rule)
                        if alert:
                            new_alerts.append(alert)
                    
                    # Check for auto-resolution
                    elif rule.auto_resolve and rule.resolve_condition:
                        if rule.resolve_condition():
                            self._resolve_alert(rule_name)
                
                except Exception as e:
                    self.logger.error(f"Error checking alert rule {rule_name}: {e}")
        
        return new_alerts
    
    def _create_alert(self, rule: AlertRule) -> Optional[Alert]:
        """Create a new alert from a rule."""
        alert_id = f"{rule.name}_{int(time.time())}"
        
        # Check if similar alert is already active
        existing_alert = self._active_alerts.get(rule.name)
        if existing_alert and existing_alert.status == AlertStatus.ACTIVE:
            self.logger.debug(f"Alert {rule.name} already active, skipping")
            return None
        
        alert = Alert(
            id=alert_id,
            name=rule.name,
            severity=rule.severity,
            message=rule.message_template,
            timestamp=datetime.now(timezone.utc)
        )
        
        # Store alert
        self._active_alerts[rule.name] = alert
        self._alert_history.append(alert)
        self._last_alert_time[rule.name] = alert.timestamp
        
        # Update statistics
        self._stats["total_alerts"] += 1
        self._stats["active_alerts"] += 1
        
        # Send notifications
        self._send_notifications(alert)
        
        self.logger.info(f"Created alert: {rule.name} - {alert.message}")
        return alert
    
    def _resolve_alert(self, alert_name: str) -> None:
        """Resolve an active alert."""
        if alert_name in self._active_alerts:
            alert = self._active_alerts[alert_name]
            if alert.status == AlertStatus.ACTIVE:
                alert.status = AlertStatus.RESOLVED
                alert.resolved_at = datetime.now(timezone.utc)
                
                # Update statistics
                self._stats["active_alerts"] -= 1
                self._stats["resolved_alerts"] += 1
                
                # Send resolution notification
                self._send_notifications(alert)
                
                self.logger.info(f"Resolved alert: {alert_name}")
    
    def resolve_alert_manually(self, alert_name: str) -> bool:
        """Manually resolve an alert."""
        with self._lock:
            if alert_name in self._active_alerts:
                self._resolve_alert(alert_name)
                return True
            return False
    
    def suppress_alert(self, alert_name: str, duration_minutes: int = 60) -> bool:
        """Suppress an alert for a specified duration."""
        with self._lock:
            if alert_name in self._active_alerts:
                alert = self._active_alerts[alert_name]
                alert.status = AlertStatus.SUPPRESSED
                alert.metadata["suppressed_until"] = (
                    datetime.now(timezone.utc) + timedelta(minutes=duration_minutes)
                ).isoformat()
                
                self._stats["suppressed_alerts"] += 1
                self.logger.info(f"Suppressed alert {alert_name} for {duration_minutes} minutes")
                return True
            return False
    
    def _is_in_cooldown(self, alert_name: str, cooldown_minutes: int) -> bool:
        """Check if alert is in cooldown period."""
        if alert_name not in self._last_alert_time:
            return False
        
        last_time = self._last_alert_time[alert_name]
        cooldown_period = timedelta(minutes=cooldown_minutes)
        
        return datetime.now(timezone.utc) - last_time < cooldown_period
    
    def _send_notifications(self, alert: Alert) -> None:
        """Send notifications for an alert."""
        for handler in self._notification_handlers:
            try:
                handler(alert)
                self._stats["notifications_sent"] += 1
            except Exception as e:
                self.logger.error(f"Notification handler failed: {e}")
                self._stats["notification_failures"] += 1
    
    def _webhook_notification_handler(self, alert: Alert) -> None:
        """Default webhook notification handler."""
        if not self.webhook_url:
            return
        
        # Determine color based on severity and status
        if alert.status == AlertStatus.RESOLVED:
            color = 0x00FF00  # Green
            title = f"🟢 Alert Resolved: {alert.name}"
        elif alert.severity == AlertSeverity.CRITICAL:
            color = 0xFF0000  # Red
            title = f"🔴 Critical Alert: {alert.name}"
        elif alert.severity == AlertSeverity.WARNING:
            color = 0xFFA500  # Orange
            title = f"🟡 Warning Alert: {alert.name}"
        else:
            color = 0x0099FF  # Blue
            title = f"🔵 Info Alert: {alert.name}"
        
        # Create Discord embed
        embed = {
            "title": title,
            "description": alert.message,
            "color": color,
            "timestamp": alert.timestamp.isoformat(),
            "fields": [
                {
                    "name": "Severity",
                    "value": alert.severity.value.upper(),
                    "inline": True
                },
                {
                    "name": "Status",
                    "value": alert.status.value.upper(),
                    "inline": True
                },
                {
                    "name": "Alert ID",
                    "value": alert.id,
                    "inline": True
                }
            ]
        }
        
        # Add resolution time if resolved
        if alert.resolved_at:
            duration = alert.resolved_at - alert.timestamp
            embed["fields"].append({
                "name": "Duration",
                "value": f"{duration.total_seconds():.1f} seconds",
                "inline": True
            })
        
        # Add metadata fields
        if alert.metadata:
            for key, value in alert.metadata.items():
                if key not in ["suppressed_until"]:  # Skip internal metadata
                    embed["fields"].append({
                        "name": key.replace("_", " ").title(),
                        "value": str(value),
                        "inline": True
                    })
        
        payload = {
            "embeds": [embed],
            "username": "Shift Code Bot Alerts"
        }
        
        try:
            response = requests.post(self.webhook_url, json=payload, timeout=10)
            response.raise_for_status()
            self.logger.debug(f"Sent webhook notification for alert {alert.name}")
        except Exception as e:
            self.logger.error(f"Failed to send webhook notification: {e}")
            raise
    
    def get_active_alerts(self) -> List[Alert]:
        """Get all active alerts."""
        with self._lock:
            return [alert for alert in self._active_alerts.values() 
                   if alert.status == AlertStatus.ACTIVE]
    
    def get_alert_history(self, hours: int = 24, limit: int = 100) -> List[Alert]:
        """Get alert history."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        
        with self._lock:
            recent_alerts = [
                alert for alert in self._alert_history 
                if alert.timestamp > cutoff
            ]
            
            # Sort by timestamp (most recent first) and limit
            recent_alerts.sort(key=lambda x: x.timestamp, reverse=True)
            return recent_alerts[:limit]
    
    def get_alert_stats(self) -> Dict[str, Any]:
        """Get alerting statistics."""
        with self._lock:
            stats = self._stats.copy()
            
            # Add current counts
            active_count = len([a for a in self._active_alerts.values() 
                              if a.status == AlertStatus.ACTIVE])
            suppressed_count = len([a for a in self._active_alerts.values() 
                                  if a.status == AlertStatus.SUPPRESSED])
            
            stats.update({
                "current_active_alerts": active_count,
                "current_suppressed_alerts": suppressed_count,
                "registered_rules": len(self._alert_rules),
                "enabled_rules": len([r for r in self._alert_rules.values() if r.enabled]),
                "notification_handlers": len(self._notification_handlers)
            })
            
            return stats
    
    def create_health_check_rules(self, health_monitor) -> None:
        """Create alert rules based on health check failures."""
        
        def create_health_rule(check_name: str, critical: bool = False):
            def condition():
                health_status = health_monitor.get_health_check_status(check_name)
                if not health_status:
                    return False
                
                if critical:
                    return health_status.status == HealthStatus.CRITICAL
                else:
                    return health_status.status in [HealthStatus.WARNING, HealthStatus.CRITICAL]
            
            def resolve_condition():
                health_status = health_monitor.get_health_check_status(check_name)
                return health_status and health_status.status == HealthStatus.HEALTHY
            
            severity = AlertSeverity.CRITICAL if critical else AlertSeverity.WARNING
            
            return AlertRule(
                name=f"health_check_{check_name}",
                condition_function=condition,
                severity=severity,
                message_template=f"Health check {check_name} is failing",
                cooldown_minutes=30,
                auto_resolve=True,
                resolve_condition=resolve_condition
            )
        
        # Add rules for common health checks
        common_checks = ["database", "memory"]
        for check_name in common_checks:
            rule = create_health_rule(check_name, critical=True)
            self.add_alert_rule(rule)
    
    def create_metrics_rules(self, metrics_collector: MetricsCollector) -> None:
        """Create alert rules based on metrics thresholds."""
        
        # High error rate rule
        def high_error_rate_condition():
            error_count = metrics_collector.get_counter_value("errors.total")
            success_count = metrics_collector.get_counter_value("operations.success")
            total = error_count + success_count
            
            if total < 10:  # Not enough data
                return False
            
            error_rate = error_count / total
            return error_rate > 0.1  # 10% error rate threshold
        
        error_rate_rule = AlertRule(
            name="high_error_rate",
            condition_function=high_error_rate_condition,
            severity=AlertSeverity.WARNING,
            message_template="High error rate detected (>10%)",
            cooldown_minutes=30
        )
        self.add_alert_rule(error_rate_rule)
        
        # Slow performance rule
        def slow_performance_condition():
            avg_duration = metrics_collector.get_gauge_value("performance.avg_duration")
            return avg_duration > 5.0  # 5 second threshold
        
        performance_rule = AlertRule(
            name="slow_performance",
            condition_function=slow_performance_condition,
            severity=AlertSeverity.WARNING,
            message_template="Average operation duration is high (>5s)",
            cooldown_minutes=15
        )
        self.add_alert_rule(performance_rule)
        
        # No codes found rule (might indicate fetching issues)
        def no_codes_found_condition():
            codes_found = metrics_collector.get_counter_value("codes.found")
            last_hour_codes = metrics_collector.get_rate_value("codes.found", window_seconds=3600)
            
            # Alert if no codes found in the last hour and we've been running
            return last_hour_codes == 0 and codes_found > 0
        
        no_codes_rule = AlertRule(
            name="no_codes_found",
            condition_function=no_codes_found_condition,
            severity=AlertSeverity.WARNING,
            message_template="No new codes found in the last hour",
            cooldown_minutes=60
        )
        self.add_alert_rule(no_codes_rule)
    
    def cleanup_old_alerts(self, days: int = 7) -> None:
        """Clean up old alert history."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        
        with self._lock:
            old_count = len(self._alert_history)
            self._alert_history = [
                alert for alert in self._alert_history 
                if alert.timestamp > cutoff
            ]
            
            cleaned_count = old_count - len(self._alert_history)
            if cleaned_count > 0:
                self.logger.info(f"Cleaned up {cleaned_count} old alerts")
    
    def export_alerts(self, format_type: str = "json") -> Union[str, Dict[str, Any]]:
        """Export alert data."""
        with self._lock:
            if format_type == "json":
                return {
                    "active_alerts": [alert.to_dict() for alert in self.get_active_alerts()],
                    "recent_history": [alert.to_dict() for alert in self.get_alert_history()],
                    "statistics": self.get_alert_stats(),
                    "export_timestamp": datetime.now(timezone.utc).isoformat()
                }
            else:
                raise ValueError(f"Unsupported export format: {format_type}")


# Convenience function to create a configured alert manager
def create_alert_manager(webhook_url: Optional[str] = None,
                        health_monitor=None,
                        metrics_collector=None) -> AlertManager:
    """Create and configure an alert manager with common rules."""
    
    alert_manager = AlertManager(webhook_url=webhook_url)
    
    # Add health check rules if health monitor provided
    if health_monitor:
        alert_manager.create_health_check_rules(health_monitor)
    
    # Add metrics rules if metrics collector provided
    if metrics_collector:
        alert_manager.create_metrics_rules(metrics_collector)
    
    return alert_manager