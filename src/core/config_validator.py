"""
Comprehensive configuration validation system.
"""

import re
import logging
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse
from datetime import datetime

from ..models.config import Config, SourceConfig, ChannelConfig, SourceType

logger = logging.getLogger(__name__)


class ConfigValidationError(Exception):
    """Configuration validation error."""
    pass


class ConfigValidator:
    """Comprehensive configuration validator with detailed error reporting."""
    
    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        
        # Validation rules
        self.url_pattern = re.compile(
            r'^https?://'  # http:// or https://
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain...
            r'localhost|'  # localhost...
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
            r'(?::\d+)?'  # optional port
            r'(?:/?|[/?]\S+)$', re.IGNORECASE)
        
        self.discord_webhook_pattern = re.compile(
            r'^https://discord\.com/api/webhooks/\d+/[\w-]+$'
        )
        
        self.cron_pattern = re.compile(
            r'^(\*|([0-5]?\d)) (\*|([01]?\d|2[0-3])) (\*|([0-2]?\d|3[01])) (\*|([0]?\d|1[0-2])) (\*|([0-6]))$'
        )
    
    def validate_config(self, config: Config) -> List[str]:
        """Validate complete configuration and return list of errors."""
        errors = []
        
        try:
            # Validate basic settings
            errors.extend(self._validate_basic_settings(config))
            
            # Validate database configuration
            errors.extend(self._validate_database_config(config))
            
            # Validate sources
            errors.extend(self._validate_sources(config.sources))
            
            # Validate Discord channels
            errors.extend(self._validate_discord_channels(config.discord_channels))
            
            # Validate notification settings
            errors.extend(self._validate_notification_settings(config.notification_settings))
            
            # Validate scheduler configuration
            errors.extend(self._validate_scheduler_config(config.scheduler_config))
            
            # Validate observability configuration
            errors.extend(self._validate_observability_config(config.observability_config))
            
            # Cross-validation checks
            errors.extend(self._validate_cross_references(config))
            
        except Exception as e:
            errors.append(f"Configuration validation failed: {str(e)}")
        
        return errors
    
    def _validate_basic_settings(self, config: Config) -> List[str]:
        """Validate basic configuration settings."""
        errors = []
        
        # Environment validation
        valid_environments = ["development", "staging", "production", "test"]
        if config.environment not in valid_environments:
            errors.append(f"Invalid environment '{config.environment}'. Must be one of: {valid_environments}")
        
        # Timezone validation
        try:
            import zoneinfo
            zoneinfo.ZoneInfo(config.timezone)
        except Exception:
            try:
                import pytz
                pytz.timezone(config.timezone)
            except Exception:
                errors.append(f"Invalid timezone '{config.timezone}'")
        
        return errors
    
    def _validate_database_config(self, config: Config) -> List[str]:
        """Validate database configuration."""
        errors = []
        
        if not config.database_url:
            errors.append("Database URL is required")
            return errors
        
        # Basic URL validation
        if not config.database_url.startswith(('sqlite:///', 'postgresql://', 'mysql://')):
            errors.append("Database URL must start with sqlite:///, postgresql://, or mysql://")
        
        # SQLite specific validation
        if config.database_url.startswith('sqlite:///'):
            db_path = config.database_url[10:]  # Remove sqlite:///
            if not db_path:
                errors.append("SQLite database path cannot be empty")
            elif db_path.startswith('/') and config.environment == "development":
                errors.append("Absolute paths not recommended for development environment")
        
        return errors
    
    def _validate_sources(self, sources: List[SourceConfig]) -> List[str]:
        """Validate source configurations."""
        errors = []
        
        if not sources:
            errors.append("At least one source must be configured")
            return errors
        
        source_ids = set()
        source_names = set()
        
        for i, source in enumerate(sources):
            source_prefix = f"Source {i+1} ({source.name})"
            
            # ID validation
            if source.id <= 0:
                errors.append(f"{source_prefix}: ID must be positive")
            
            if source.id in source_ids:
                errors.append(f"{source_prefix}: Duplicate source ID {source.id}")
            source_ids.add(source.id)
            
            # Name validation
            if not source.name or not source.name.strip():
                errors.append(f"{source_prefix}: Name is required")
            elif len(source.name) > 100:
                errors.append(f"{source_prefix}: Name too long (max 100 characters)")
            
            if source.name in source_names:
                errors.append(f"{source_prefix}: Duplicate source name '{source.name}'")
            source_names.add(source.name)
            
            # URL validation
            if not source.url:
                errors.append(f"{source_prefix}: URL is required")
            elif not self.url_pattern.match(source.url):
                errors.append(f"{source_prefix}: Invalid URL format")
            
            # Type validation
            if source.type not in SourceType:
                errors.append(f"{source_prefix}: Invalid source type '{source.type}'")
            
            # Rate limit validation
            if source.rate_limit.requests_per_minute <= 0:
                errors.append(f"{source_prefix}: Requests per minute must be positive")
            elif source.rate_limit.requests_per_minute > 3600:
                errors.append(f"{source_prefix}: Requests per minute too high (max 3600)")
            
            if source.rate_limit.delay_between_requests < 0:
                errors.append(f"{source_prefix}: Delay between requests cannot be negative")
            elif source.rate_limit.delay_between_requests > 300:
                errors.append(f"{source_prefix}: Delay between requests too high (max 300s)")
            
            if source.rate_limit.burst_limit <= 0:
                errors.append(f"{source_prefix}: Burst limit must be positive")
            
            # Type-specific validation
            if source.type == SourceType.REDDIT:
                errors.extend(self._validate_reddit_source(source, source_prefix))
            elif source.type == SourceType.RSS:
                errors.extend(self._validate_rss_source(source, source_prefix))
        
        return errors
    
    def _validate_reddit_source(self, source: SourceConfig, prefix: str) -> List[str]:
        """Validate Reddit-specific source configuration."""
        errors = []
        
        if "subreddit" not in source.parser_hints:
            errors.append(f"{prefix}: Reddit sources must specify 'subreddit' in parser_hints")
        else:
            subreddit = source.parser_hints["subreddit"]
            if not isinstance(subreddit, str) or not subreddit.strip():
                errors.append(f"{prefix}: Subreddit name must be a non-empty string")
            elif not re.match(r'^[A-Za-z0-9_]+$', subreddit):
                errors.append(f"{prefix}: Invalid subreddit name format")
        
        # Validate optional settings
        if "post_limit" in source.parser_hints:
            post_limit = source.parser_hints["post_limit"]
            if not isinstance(post_limit, int) or post_limit <= 0 or post_limit > 100:
                errors.append(f"{prefix}: post_limit must be an integer between 1 and 100")
        
        return errors
    
    def _validate_rss_source(self, source: SourceConfig, prefix: str) -> List[str]:
        """Validate RSS-specific source configuration."""
        errors = []
        
        # Validate optional settings
        if "max_entries" in source.parser_hints:
            max_entries = source.parser_hints["max_entries"]
            if not isinstance(max_entries, int) or max_entries <= 0 or max_entries > 1000:
                errors.append(f"{prefix}: max_entries must be an integer between 1 and 1000")
        
        if "cutoff_days" in source.parser_hints:
            cutoff_days = source.parser_hints["cutoff_days"]
            if not isinstance(cutoff_days, int) or cutoff_days <= 0 or cutoff_days > 365:
                errors.append(f"{prefix}: cutoff_days must be an integer between 1 and 365")
        
        return errors
    
    def _validate_discord_channels(self, channels: List[ChannelConfig]) -> List[str]:
        """Validate Discord channel configurations."""
        errors = []
        
        if not channels:
            errors.append("At least one Discord channel must be configured")
            return errors
        
        channel_ids = set()
        channel_names = set()
        
        for i, channel in enumerate(channels):
            channel_prefix = f"Discord channel {i+1} ({channel.name})"
            
            # ID validation
            if not channel.id or not channel.id.strip():
                errors.append(f"{channel_prefix}: ID is required")
            elif len(channel.id) > 50:
                errors.append(f"{channel_prefix}: ID too long (max 50 characters)")
            
            if channel.id in channel_ids:
                errors.append(f"{channel_prefix}: Duplicate channel ID '{channel.id}'")
            channel_ids.add(channel.id)
            
            # Name validation
            if not channel.name or not channel.name.strip():
                errors.append(f"{channel_prefix}: Name is required")
            elif len(channel.name) > 100:
                errors.append(f"{channel_prefix}: Name too long (max 100 characters)")
            
            if channel.name in channel_names:
                errors.append(f"{channel_prefix}: Duplicate channel name '{channel.name}'")
            channel_names.add(channel.name)
            
            # Webhook URL validation
            if not channel.webhook_url:
                errors.append(f"{channel_prefix}: Webhook URL is required")
            elif not self.discord_webhook_pattern.match(channel.webhook_url):
                errors.append(f"{channel_prefix}: Invalid Discord webhook URL format")
        
        return errors
    
    def _validate_notification_settings(self, settings) -> List[str]:
        """Validate notification settings."""
        errors = []
        
        if settings.max_codes_per_notification <= 0:
            errors.append("max_codes_per_notification must be positive")
        elif settings.max_codes_per_notification > 50:
            errors.append("max_codes_per_notification too high (max 50)")
        
        if settings.reminder_hours_before <= 0:
            errors.append("reminder_hours_before must be positive")
        elif settings.reminder_hours_before > 168:  # 1 week
            errors.append("reminder_hours_before too high (max 168 hours)")
        
        if settings.rate_limit_delay < 0:
            errors.append("rate_limit_delay cannot be negative")
        elif settings.rate_limit_delay > 60:
            errors.append("rate_limit_delay too high (max 60 seconds)")
        
        if settings.max_retries <= 0:
            errors.append("max_retries must be positive")
        elif settings.max_retries > 10:
            errors.append("max_retries too high (max 10)")
        
        return errors
    
    def _validate_scheduler_config(self, config) -> List[str]:
        """Validate scheduler configuration."""
        errors = []
        
        # Cron schedule validation
        if not config.cron_schedule:
            errors.append("cron_schedule is required")
        elif not self._validate_cron_expression(config.cron_schedule):
            errors.append(f"Invalid cron expression: '{config.cron_schedule}'")
        
        # Execution time validation
        if config.max_execution_time <= 0:
            errors.append("max_execution_time must be positive")
        elif config.max_execution_time > 3600:  # 1 hour
            errors.append("max_execution_time too high (max 3600 seconds)")
        
        return errors
    
    def _validate_observability_config(self, config) -> List[str]:
        """Validate observability configuration."""
        errors = []
        
        # Log level validation
        valid_log_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if config.log_level not in valid_log_levels:
            errors.append(f"Invalid log_level '{config.log_level}'. Must be one of: {valid_log_levels}")
        
        # Log format validation
        valid_log_formats = ["json", "text"]
        if config.log_format not in valid_log_formats:
            errors.append(f"Invalid log_format '{config.log_format}'. Must be one of: {valid_log_formats}")
        
        # Alert webhook URL validation
        if config.alert_webhook_url:
            if not self.url_pattern.match(config.alert_webhook_url):
                errors.append("Invalid alert_webhook_url format")
        
        return errors
    
    def _validate_cross_references(self, config: Config) -> List[str]:
        """Validate cross-references between configuration sections."""
        errors = []
        
        # Check if source filters reference valid sources
        source_names = {source.name for source in config.sources}
        
        for channel in config.discord_channels:
            for source_filter in channel.source_filters:
                if source_filter not in source_names:
                    errors.append(
                        f"Discord channel '{channel.name}' references unknown source '{source_filter}'"
                    )
        
        # Check for conflicting rate limits
        total_requests_per_minute = sum(
            source.rate_limit.requests_per_minute 
            for source in config.sources 
            if source.enabled
        )
        
        if total_requests_per_minute > 1000:
            errors.append(
                f"Total requests per minute across all sources ({total_requests_per_minute}) "
                "may be too high and could cause rate limiting issues"
            )
        
        return errors
    
    def _validate_cron_expression(self, cron_expr: str) -> bool:
        """Validate cron expression format."""
        try:
            # Basic validation - in production, use croniter or similar
            parts = cron_expr.split()
            if len(parts) != 5:
                return False
            
            # Validate each part (simplified)
            ranges = [
                (0, 59),  # minute
                (0, 23),  # hour
                (1, 31),  # day
                (1, 12),  # month
                (0, 6),   # day of week
            ]
            
            for i, part in enumerate(parts):
                if part == '*':
                    continue
                
                if '/' in part:
                    # Handle step values like */5
                    base, step = part.split('/')
                    if base != '*':
                        return False
                    try:
                        step_val = int(step)
                        if step_val <= 0:
                            return False
                    except ValueError:
                        return False
                elif '-' in part:
                    # Handle ranges like 1-5
                    try:
                        start, end = map(int, part.split('-'))
                        min_val, max_val = ranges[i]
                        if start < min_val or end > max_val or start > end:
                            return False
                    except ValueError:
                        return False
                else:
                    # Handle single values
                    try:
                        val = int(part)
                        min_val, max_val = ranges[i]
                        if val < min_val or val > max_val:
                            return False
                    except ValueError:
                        return False
            
            return True
            
        except Exception:
            return False
    
    def validate_runtime_config(self, config: Config) -> List[str]:
        """Validate configuration for runtime issues."""
        errors = []
        
        # Check for enabled sources
        enabled_sources = [s for s in config.sources if s.enabled]
        if not enabled_sources:
            errors.append("No sources are enabled")
        
        # Check for enabled channels
        enabled_channels = [c for c in config.discord_channels if c.enabled]
        if not enabled_channels:
            errors.append("No Discord channels are enabled")
        
        # Check for reasonable rate limits in production
        if config.environment == "production":
            for source in enabled_sources:
                if source.rate_limit.delay_between_requests < 1.0:
                    errors.append(
                        f"Source '{source.name}' has very low delay ({source.rate_limit.delay_between_requests}s) "
                        "which may cause rate limiting in production"
                    )
        
        return errors