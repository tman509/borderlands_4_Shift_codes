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
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    
    def __post_init__(self):
        """Validate source configuration after initialization."""
        if not self.name or not self.name.strip():
            raise ValueError("Source name cannot be empty")
        
        if not self.url or not self.url.strip():
            raise ValueError("Source URL cannot be empty")
        
        if self.id <= 0:
            raise ValueError("Source ID must be positive")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "name": self.name,
            "url": self.url,
            "type": self.type.value,
            "enabled": self.enabled,
            "parser_hints": self.parser_hints,
            "rate_limit": {
                "requests_per_minute": self.rate_limit.requests_per_minute,
                "delay_between_requests": self.rate_limit.delay_between_requests,
                "burst_limit": self.rate_limit.burst_limit
            },
            "last_crawl_at": self.last_crawl_at,
            "last_content_hash": self.last_content_hash,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SourceConfig':
        """Create from dictionary."""
        rate_limit = RateLimit()
        if "rate_limit" in data:
            rl_data = data["rate_limit"]
            rate_limit = RateLimit(
                requests_per_minute=rl_data.get("requests_per_minute", 60),
                delay_between_requests=rl_data.get("delay_between_requests", 1.0),
                burst_limit=rl_data.get("burst_limit", 10)
            )
        
        return cls(
            id=data["id"],
            name=data["name"],
            url=data["url"],
            type=SourceType(data["type"]),
            enabled=data.get("enabled", True),
            parser_hints=data.get("parser_hints", {}),
            rate_limit=rate_limit,
            last_crawl_at=data.get("last_crawl_at"),
            last_content_hash=data.get("last_content_hash"),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at")
        )


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