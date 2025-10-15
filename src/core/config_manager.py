"""
Configuration management for the Shift Code Bot.
"""

import os
import json
import logging
from typing import Dict, List, Optional, Any
from pathlib import Path

from ..models.config import (
    Config, SourceConfig, ChannelConfig, NotificationSettings,
    SchedulerConfig, ObservabilityConfig, SourceType, RateLimit
)

logger = logging.getLogger(__name__)


class ConfigManager:
    """Manages configuration loading, validation, and hot-reload."""
    
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or os.getenv("CONFIG_PATH", "config.json")
        self._config: Optional[Config] = None
        self._env_overrides = self._load_env_overrides()
    
    def load_config(self) -> Config:
        """Load configuration from file and environment variables."""
        try:
            # Load from file if it exists
            config_data = {}
            if Path(self.config_path).exists():
                with open(self.config_path, 'r') as f:
                    config_data = json.load(f)
                logger.info(f"Loaded configuration from {self.config_path}")
            else:
                logger.info("No config file found, using environment variables and defaults")
            
            # Apply environment overrides
            config_data.update(self._env_overrides)
            
            # Build configuration object
            self._config = self._build_config(config_data)
            
            # Validate configuration
            if not self.validate_config(self._config):
                raise ValueError("Configuration validation failed")
            
            logger.info("Configuration loaded and validated successfully")
            return self._config
            
        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")
            raise
    
    def validate_config(self, config: Config) -> bool:
        """Validate configuration object."""
        try:
            # Validate database URL
            if not config.database_url:
                logger.error("Database URL is required")
                return False
            
            # Validate sources
            if not config.sources:
                logger.warning("No sources configured")
            
            for source in config.sources:
                if not source.url:
                    logger.error(f"Source {source.name} missing URL")
                    return False
                
                if source.type not in SourceType:
                    logger.error(f"Invalid source type: {source.type}")
                    return False
            
            # Validate Discord channels
            for channel in config.discord_channels:
                if not channel.webhook_url:
                    logger.error(f"Channel {channel.name} missing webhook URL")
                    return False
                
                if not channel.webhook_url.startswith('https://'):
                    logger.error(f"Invalid webhook URL format for channel {channel.name}")
                    return False
            
            logger.info("Configuration validation passed")
            return True
            
        except Exception as e:
            logger.error(f"Configuration validation error: {e}")
            return False
    
    def get_sources(self) -> List[SourceConfig]:
        """Get list of enabled sources."""
        if not self._config:
            raise RuntimeError("Configuration not loaded")
        
        return [source for source in self._config.sources if source.enabled]
    
    def get_discord_channels(self) -> List[ChannelConfig]:
        """Get list of enabled Discord channels."""
        if not self._config:
            raise RuntimeError("Configuration not loaded")
        
        return [channel for channel in self._config.discord_channels if channel.enabled]
    
    def reload_config(self) -> None:
        """Reload configuration from file with change detection."""
        logger.info("Reloading configuration")
        old_config = self._config
        
        try:
            new_config = self.load_config()
            
            # Detect changes
            changes = self._detect_config_changes(old_config, new_config)
            if changes:
                logger.info(f"Configuration changes detected: {changes}")
                self._notify_config_changes(changes)
            else:
                logger.info("No configuration changes detected")
                
        except Exception as e:
            logger.error(f"Failed to reload configuration: {e}")
            # Keep old configuration on reload failure
            self._config = old_config
            raise
    
    def _load_env_overrides(self) -> Dict[str, Any]:
        """Load configuration overrides from environment variables."""
        overrides = {}
        
        # Database configuration
        if db_url := os.getenv("DATABASE_URL"):
            overrides["database_url"] = db_url
        
        # Environment settings
        if env := os.getenv("ENVIRONMENT"):
            overrides["environment"] = env
        
        if debug := os.getenv("DEBUG"):
            overrides["debug"] = debug.lower() in ("true", "1", "yes")
        
        if timezone := os.getenv("TIMEZONE"):
            overrides["timezone"] = timezone
        
        # Notification settings
        notification_overrides = {}
        if max_codes := os.getenv("MAX_CODES_PER_NOTIFICATION"):
            notification_overrides["max_codes_per_notification"] = int(max_codes)
        
        if enable_reminders := os.getenv("ENABLE_EXPIRATION_REMINDERS"):
            notification_overrides["enable_expiration_reminders"] = enable_reminders.lower() in ("true", "1", "yes")
        
        if notification_overrides:
            overrides["notification_settings"] = notification_overrides
        
        # Observability settings
        observability_overrides = {}
        if log_level := os.getenv("LOG_LEVEL"):
            observability_overrides["log_level"] = log_level
        
        if alert_webhook := os.getenv("ALERT_WEBHOOK_URL"):
            observability_overrides["alert_webhook_url"] = alert_webhook
        
        if observability_overrides:
            overrides["observability_config"] = observability_overrides
        
        return overrides
    
    def _build_config(self, config_data: Dict[str, Any]) -> Config:
        """Build Config object from dictionary data."""
        # Build sources
        sources = []
        for source_data in config_data.get("sources", []):
            rate_limit = RateLimit(**source_data.get("rate_limit", {}))
            source = SourceConfig(
                id=source_data["id"],
                name=source_data["name"],
                url=source_data["url"],
                type=SourceType(source_data["type"]),
                enabled=source_data.get("enabled", True),
                parser_hints=source_data.get("parser_hints", {}),
                rate_limit=rate_limit,
                last_crawl_at=source_data.get("last_crawl_at"),
                last_content_hash=source_data.get("last_content_hash")
            )
            sources.append(source)
        
        # Build Discord channels
        channels = []
        for channel_data in config_data.get("discord_channels", []):
            channel = ChannelConfig(
                id=channel_data["id"],
                name=channel_data["name"],
                webhook_url=channel_data["webhook_url"],
                enabled=channel_data.get("enabled", True),
                message_template=channel_data.get("message_template"),
                source_filters=channel_data.get("source_filters", [])
            )
            channels.append(channel)
        
        # Build notification settings
        notification_data = config_data.get("notification_settings", {})
        notification_settings = NotificationSettings(**notification_data)
        
        # Build scheduler config
        scheduler_data = config_data.get("scheduler_config", {})
        scheduler_config = SchedulerConfig(**scheduler_data)
        
        # Build observability config
        observability_data = config_data.get("observability_config", {})
        observability_config = ObservabilityConfig(**observability_data)
        
        # Build main config
        return Config(
            database_url=config_data.get("database_url", "sqlite:///shift_codes.db"),
            sources=sources,
            discord_channels=channels,
            notification_settings=notification_settings,
            scheduler_config=scheduler_config,
            observability_config=observability_config,
            environment=config_data.get("environment", "development"),
            debug=config_data.get("debug", False),
            timezone=config_data.get("timezone", "UTC")
        )
    
    def _detect_config_changes(self, old_config: Optional[Config], new_config: Config) -> Dict[str, Any]:
        """Detect changes between old and new configuration."""
        if not old_config:
            return {"type": "initial_load"}
        
        changes = {}
        
        # Check database URL changes
        if old_config.database_url != new_config.database_url:
            changes["database_url"] = {
                "old": old_config.database_url,
                "new": new_config.database_url
            }
        
        # Check source changes
        old_sources = {s.id: s for s in old_config.sources}
        new_sources = {s.id: s for s in new_config.sources}
        
        source_changes = {}
        
        # Added sources
        added_sources = set(new_sources.keys()) - set(old_sources.keys())
        if added_sources:
            source_changes["added"] = [new_sources[sid].name for sid in added_sources]
        
        # Removed sources
        removed_sources = set(old_sources.keys()) - set(new_sources.keys())
        if removed_sources:
            source_changes["removed"] = [old_sources[sid].name for sid in removed_sources]
        
        # Modified sources
        modified_sources = []
        for sid in set(old_sources.keys()) & set(new_sources.keys()):
            if self._source_changed(old_sources[sid], new_sources[sid]):
                modified_sources.append(new_sources[sid].name)
        
        if modified_sources:
            source_changes["modified"] = modified_sources
        
        if source_changes:
            changes["sources"] = source_changes
        
        # Check Discord channel changes
        old_channels = {c.id: c for c in old_config.discord_channels}
        new_channels = {c.id: c for c in new_config.discord_channels}
        
        channel_changes = {}
        
        # Added channels
        added_channels = set(new_channels.keys()) - set(old_channels.keys())
        if added_channels:
            channel_changes["added"] = [new_channels[cid].name for cid in added_channels]
        
        # Removed channels
        removed_channels = set(old_channels.keys()) - set(new_channels.keys())
        if removed_channels:
            channel_changes["removed"] = [old_channels[cid].name for cid in removed_channels]
        
        # Modified channels
        modified_channels = []
        for cid in set(old_channels.keys()) & set(new_channels.keys()):
            if self._channel_changed(old_channels[cid], new_channels[cid]):
                modified_channels.append(new_channels[cid].name)
        
        if modified_channels:
            channel_changes["modified"] = modified_channels
        
        if channel_changes:
            changes["discord_channels"] = channel_changes
        
        # Check notification settings changes
        if self._notification_settings_changed(old_config.notification_settings, new_config.notification_settings):
            changes["notification_settings"] = "modified"
        
        # Check scheduler config changes
        if self._scheduler_config_changed(old_config.scheduler_config, new_config.scheduler_config):
            changes["scheduler_config"] = "modified"
        
        # Check observability config changes
        if self._observability_config_changed(old_config.observability_config, new_config.observability_config):
            changes["observability_config"] = "modified"
        
        return changes
    
    def _source_changed(self, old_source: SourceConfig, new_source: SourceConfig) -> bool:
        """Check if source configuration has changed."""
        return (
            old_source.name != new_source.name or
            old_source.url != new_source.url or
            old_source.type != new_source.type or
            old_source.enabled != new_source.enabled or
            old_source.parser_hints != new_source.parser_hints or
            old_source.rate_limit.requests_per_minute != new_source.rate_limit.requests_per_minute or
            old_source.rate_limit.delay_between_requests != new_source.rate_limit.delay_between_requests
        )
    
    def _channel_changed(self, old_channel: ChannelConfig, new_channel: ChannelConfig) -> bool:
        """Check if channel configuration has changed."""
        return (
            old_channel.name != new_channel.name or
            old_channel.webhook_url != new_channel.webhook_url or
            old_channel.enabled != new_channel.enabled or
            old_channel.message_template != new_channel.message_template or
            old_channel.source_filters != new_channel.source_filters
        )
    
    def _notification_settings_changed(self, old_settings: NotificationSettings, new_settings: NotificationSettings) -> bool:
        """Check if notification settings have changed."""
        return (
            old_settings.max_codes_per_notification != new_settings.max_codes_per_notification or
            old_settings.enable_expiration_reminders != new_settings.enable_expiration_reminders or
            old_settings.reminder_hours_before != new_settings.reminder_hours_before or
            old_settings.rate_limit_delay != new_settings.rate_limit_delay or
            old_settings.max_retries != new_settings.max_retries
        )
    
    def _scheduler_config_changed(self, old_config: SchedulerConfig, new_config: SchedulerConfig) -> bool:
        """Check if scheduler configuration has changed."""
        return (
            old_config.cron_schedule != new_config.cron_schedule or
            old_config.enable_manual_trigger != new_config.enable_manual_trigger or
            old_config.max_execution_time != new_config.max_execution_time
        )
    
    def _observability_config_changed(self, old_config: ObservabilityConfig, new_config: ObservabilityConfig) -> bool:
        """Check if observability configuration has changed."""
        return (
            old_config.log_level != new_config.log_level or
            old_config.log_format != new_config.log_format or
            old_config.metrics_enabled != new_config.metrics_enabled or
            old_config.health_check_enabled != new_config.health_check_enabled or
            old_config.alert_webhook_url != new_config.alert_webhook_url
        )
    
    def _notify_config_changes(self, changes: Dict[str, Any]) -> None:
        """Notify registered listeners about configuration changes."""
        # This would notify other components about config changes
        # For now, just log the changes
        logger.info(f"Configuration changes: {changes}")
        
        # In a full implementation, this would:
        # 1. Notify fetchers about source changes
        # 2. Notify notification system about channel changes
        # 3. Notify scheduler about schedule changes
        # 4. Update logging configuration
        # 5. Update metrics collection
    
    def watch_config_file(self) -> None:
        """Watch configuration file for changes and auto-reload."""
        # This would implement file watching using watchdog or similar
        # For now, this is a placeholder
        logger.info(f"Config file watching not implemented yet for {self.config_path}")
    
    def export_config(self, include_secrets: bool = False) -> Dict[str, Any]:
        """Export current configuration to dictionary."""
        if not self._config:
            return {}
        
        config_dict = {
            "database_url": self._config.database_url if include_secrets else "[REDACTED]",
            "environment": self._config.environment,
            "debug": self._config.debug,
            "timezone": self._config.timezone,
            "sources": [],
            "discord_channels": [],
            "notification_settings": {
                "max_codes_per_notification": self._config.notification_settings.max_codes_per_notification,
                "enable_expiration_reminders": self._config.notification_settings.enable_expiration_reminders,
                "reminder_hours_before": self._config.notification_settings.reminder_hours_before,
                "rate_limit_delay": self._config.notification_settings.rate_limit_delay,
                "max_retries": self._config.notification_settings.max_retries
            },
            "scheduler_config": {
                "cron_schedule": self._config.scheduler_config.cron_schedule,
                "enable_manual_trigger": self._config.scheduler_config.enable_manual_trigger,
                "max_execution_time": self._config.scheduler_config.max_execution_time
            },
            "observability_config": {
                "log_level": self._config.observability_config.log_level,
                "log_format": self._config.observability_config.log_format,
                "metrics_enabled": self._config.observability_config.metrics_enabled,
                "health_check_enabled": self._config.observability_config.health_check_enabled,
                "alert_webhook_url": self._config.observability_config.alert_webhook_url if include_secrets else "[REDACTED]" if self._config.observability_config.alert_webhook_url else None
            }
        }
        
        # Export sources
        for source in self._config.sources:
            source_dict = {
                "id": source.id,
                "name": source.name,
                "url": source.url if include_secrets else "[REDACTED]",
                "type": source.type.value,
                "enabled": source.enabled,
                "parser_hints": source.parser_hints,
                "rate_limit": {
                    "requests_per_minute": source.rate_limit.requests_per_minute,
                    "delay_between_requests": source.rate_limit.delay_between_requests,
                    "burst_limit": source.rate_limit.burst_limit
                }
            }
            config_dict["sources"].append(source_dict)
        
        # Export Discord channels
        for channel in self._config.discord_channels:
            channel_dict = {
                "id": channel.id,
                "name": channel.name,
                "webhook_url": channel.webhook_url if include_secrets else "[REDACTED]",
                "enabled": channel.enabled,
                "message_template": channel.message_template,
                "source_filters": channel.source_filters
            }
            config_dict["discord_channels"].append(channel_dict)
        
        return config_dict
    
    def get_config_summary(self) -> Dict[str, Any]:
        """Get a summary of current configuration."""
        if not self._config:
            return {"status": "not_loaded"}
        
        return {
            "status": "loaded",
            "environment": self._config.environment,
            "debug": self._config.debug,
            "timezone": self._config.timezone,
            "sources": {
                "total": len(self._config.sources),
                "enabled": len([s for s in self._config.sources if s.enabled]),
                "by_type": {
                    source_type.value: len([s for s in self._config.sources if s.type == source_type])
                    for source_type in SourceType
                }
            },
            "discord_channels": {
                "total": len(self._config.discord_channels),
                "enabled": len([c for c in self._config.discord_channels if c.enabled])
            },
            "notification_settings": {
                "max_codes_per_notification": self._config.notification_settings.max_codes_per_notification,
                "reminders_enabled": self._config.notification_settings.enable_expiration_reminders
            },
            "scheduler": {
                "schedule": self._config.scheduler_config.cron_schedule,
                "manual_trigger": self._config.scheduler_config.enable_manual_trigger
            },
            "observability": {
                "log_level": self._config.observability_config.log_level,
                "metrics_enabled": self._config.observability_config.metrics_enabled,
                "health_check_enabled": self._config.observability_config.health_check_enabled
            }
        }