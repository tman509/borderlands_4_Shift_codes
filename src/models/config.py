"""
Configuration data models for the Shift Code Bot.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum


class SourceType(Enum):
    """Types of sources that can be crawled."""
    HTML = "html"
    RSS = "rss"
    API = "api"
    REDDIT = "reddit"


@dataclass
class RateLimit:
    """Rate limiting configuration for sources."""
    requests_per_minute: int = 60
    delay_between_requests: float = 1.0
    burst_limit: int = 10


@dataclass
class SourceConfig:
    """Configuration for a single source."""
    id: int
    name: str
    url: str
    type: SourceType
    enabled: bool = True
    parser_hints: Dict[str, Any] = field(default_factory=dict)
    rate_limit: RateLimit = field(default_factory=RateLimit)
    last_crawl_at: Optional[str] = None
    last_content_hash: Optional[str] = None


@dataclass
class ChannelConfig:
    """Configuration for Discord channel notifications."""
    id: str
    name: str
    webhook_url: str
    enabled: bool = True
    message_template: Optional[str] = None
    source_filters: List[str] = field(default_factory=list)


@dataclass
class NotificationSettings:
    """Global notification settings."""
    max_codes_per_notification: int = 5
    enable_expiration_reminders: bool = True
    reminder_hours_before: int = 24
    rate_limit_delay: float = 0.5
    max_retries: int = 3


@dataclass
class SchedulerConfig:
    """Scheduler configuration."""
    cron_schedule: str = "*/10 * * * *"  # Every 10 minutes
    enable_manual_trigger: bool = True
    max_execution_time: int = 300  # 5 minutes


@dataclass
class ObservabilityConfig:
    """Observability and monitoring configuration."""
    log_level: str = "INFO"
    log_format: str = "json"
    metrics_enabled: bool = True
    health_check_enabled: bool = True
    alert_webhook_url: Optional[str] = None


@dataclass
class Config:
    """Main configuration object."""
    database_url: str
    sources: List[SourceConfig] = field(default_factory=list)
    discord_channels: List[ChannelConfig] = field(default_factory=list)
    notification_settings: NotificationSettings = field(default_factory=NotificationSettings)
    scheduler_config: SchedulerConfig = field(default_factory=SchedulerConfig)
    observability_config: ObservabilityConfig = field(default_factory=ObservabilityConfig)
    
    # Environment-specific settings
    environment: str = "development"
    debug: bool = False
    timezone: str = "UTC"