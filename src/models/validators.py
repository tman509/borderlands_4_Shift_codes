"""
Validation utilities for data models.
"""

import re
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from urllib.parse import urlparse

from .config import SourceType, SourceConfig, ChannelConfig
from .code import ParsedCode, CodeMetadata

logger = logging.getLogger(__name__)


class ConfigValidator:
    """Validates configuration objects."""
    
    @staticmethod
    def validate_source_config(source: SourceConfig) -> List[str]:
        """Validate source configuration and return list of errors."""
        errors = []
        
        # Validate ID
        if source.id <= 0:
            errors.append("Source ID must be positive")
        
        # Validate name
        if not source.name or not source.name.strip():
            errors.append("Source name is required")
        
        # Validate URL
        if not source.url:
            errors.append("Source URL is required")
        else:
            # Basic URL validation
            try:
                parsed = urlparse(source.url)
                if not parsed.scheme or not parsed.netloc:
                    errors.append("Invalid URL format")
            except Exception:
                errors.append("Invalid URL format")
        
        # Validate type
        if source.type not in SourceType:
            errors.append(f"Invalid source type: {source.type}")
        
        # Validate rate limit
        if source.rate_limit.requests_per_minute <= 0:
            errors.append("Requests per minute must be positive")
        
        if source.rate_limit.delay_between_requests < 0:
            errors.append("Delay between requests cannot be negative")
        
        # Type-specific validation
        if source.type == SourceType.REDDIT:
            if "subreddit" not in source.parser_hints:
                errors.append("Reddit sources must specify subreddit in parser_hints")
        
        return errors
    
    @staticmethod
    def validate_channel_config(channel: ChannelConfig) -> List[str]:
        """Validate Discord channel configuration and return list of errors."""
        errors = []
        
        # Validate ID
        if not channel.id or not channel.id.strip():
            errors.append("Channel ID is required")
        
        # Validate name
        if not channel.name or not channel.name.strip():
            errors.append("Channel name is required")
        
        # Validate webhook URL
        if not channel.webhook_url:
            errors.append("Webhook URL is required")
        else:
            if not channel.webhook_url.startswith("https://discord.com/api/webhooks/"):
                errors.append("Invalid Discord webhook URL format")
        
        return errors


class CodeValidator:
    """Validates code-related objects."""
    
    # Valid code format patterns
    VALID_PATTERNS = [
        re.compile(r"^[A-Z0-9]{5}-[A-Z0-9]{5}-[A-Z0-9]{5}-[A-Z0-9]{5}-[A-Z0-9]{5}$"),  # 5x5
        re.compile(r"^[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$"),              # 4x4
        re.compile(r"^[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$")   # 4x5
    ]
    
    # Suspicious patterns that might indicate test codes
    TEST_PATTERNS = [
        re.compile(r"^[X]{5}-[X]{5}-[X]{5}-[X]{5}-[X]{5}$"),  # All X's
        re.compile(r"^[0]{5}-[0]{5}-[0]{5}-[0]{5}-[0]{5}$"),  # All 0's
        re.compile(r"^[1]{5}-[1]{5}-[1]{5}-[1]{5}-[1]{5}$"),  # All 1's
        re.compile(r"^ABCDE-FGHIJ-KLMNO-PQRST-UVWXY$"),       # Alphabetical
        re.compile(r"^12345-67890-12345-67890-12345$"),        # Number sequence
    ]
    
    @staticmethod
    def validate_parsed_code(code: ParsedCode) -> List[str]:
        """Validate parsed code and return list of errors."""
        errors = []
        
        # Validate canonical code format
        if not CodeValidator.is_valid_format(code.code_canonical):
            errors.append(f"Invalid canonical code format: {code.code_canonical}")
        
        # Validate display code
        if not code.code_display:
            errors.append("Display code is required")
        
        # Validate confidence score
        if not (0.0 <= code.confidence_score <= 1.0):
            errors.append("Confidence score must be between 0.0 and 1.0")
        
        # Validate source ID
        if code.source_id <= 0:
            errors.append("Source ID must be positive")
        
        # Validate platforms
        if code.platforms:
            valid_platforms = {"pc", "xbox", "playstation", "nintendo", "all"}
            invalid_platforms = set(code.platforms) - valid_platforms
            if invalid_platforms:
                errors.append(f"Invalid platforms: {invalid_platforms}")
        
        # Validate expiration date
        if code.expires_at:
            if code.expires_at.tzinfo is None:
                errors.append("Expiration date must be timezone-aware")
        
        # Check for suspicious test codes
        if CodeValidator.is_likely_test_code(code.code_canonical):
            errors.append("Code appears to be a test/example code")
        
        return errors
    
    @staticmethod
    def is_valid_format(code: str) -> bool:
        """Check if code matches valid format patterns."""
        return any(pattern.match(code) for pattern in CodeValidator.VALID_PATTERNS)
    
    @staticmethod
    def is_likely_test_code(code: str) -> bool:
        """Check if code is likely a test/example code."""
        return any(pattern.match(code) for pattern in CodeValidator.TEST_PATTERNS)
    
    @staticmethod
    def normalize_code(code: str) -> str:
        """Normalize code to canonical format."""
        if not code:
            return ""
        
        # Remove all non-alphanumeric characters and convert to uppercase
        clean_code = re.sub(r'[^A-Z0-9]', '', code.upper())
        
        # Format based on length
        if len(clean_code) == 25:  # 5x5 format
            return '-'.join([clean_code[i:i+5] for i in range(0, 25, 5)])
        elif len(clean_code) == 20:  # 4x5 format
            return '-'.join([clean_code[i:i+4] for i in range(0, 20, 4)])
        elif len(clean_code) == 16:  # 4x4 format
            return '-'.join([clean_code[i:i+4] for i in range(0, 16, 4)])
        else:
            return clean_code


class MetadataValidator:
    """Validates code metadata."""
    
    VALID_REWARD_TYPES = {
        "golden key", "diamond key", "vault card", "cosmetic", 
        "weapon", "eridium", "xp", "event"
    }
    
    VALID_PLATFORMS = {
        "pc", "xbox", "playstation", "nintendo", "all"
    }
    
    @staticmethod
    def validate_metadata(metadata: CodeMetadata) -> List[str]:
        """Validate code metadata and return list of errors."""
        errors = []
        
        # Validate reward type
        if metadata.reward_type and metadata.reward_type not in MetadataValidator.VALID_REWARD_TYPES:
            errors.append(f"Unknown reward type: {metadata.reward_type}")
        
        # Validate platforms
        if metadata.platforms:
            invalid_platforms = set(metadata.platforms) - MetadataValidator.VALID_PLATFORMS
            if invalid_platforms:
                errors.append(f"Invalid platforms: {invalid_platforms}")
        
        # Validate confidence score
        if not (0.0 <= metadata.confidence_score <= 1.0):
            errors.append("Confidence score must be between 0.0 and 1.0")
        
        # Validate expiration date
        if metadata.expires_at:
            if metadata.expires_at.tzinfo is None:
                errors.append("Expiration date must be timezone-aware")
            
            # Check if expiration is in the past (with some tolerance)
            now = datetime.now(timezone.utc)
            if metadata.expires_at < now:
                # Allow some tolerance for recently expired codes
                time_diff = now - metadata.expires_at
                if time_diff.total_seconds() > 3600:  # More than 1 hour ago
                    errors.append("Expiration date is more than 1 hour in the past")
        
        return errors


def validate_all(obj: Any) -> Dict[str, List[str]]:
    """Validate any supported object and return categorized errors."""
    validation_results = {}
    
    if isinstance(obj, SourceConfig):
        errors = ConfigValidator.validate_source_config(obj)
        if errors:
            validation_results["source_config"] = errors
    
    elif isinstance(obj, ChannelConfig):
        errors = ConfigValidator.validate_channel_config(obj)
        if errors:
            validation_results["channel_config"] = errors
    
    elif isinstance(obj, ParsedCode):
        errors = CodeValidator.validate_parsed_code(obj)
        if errors:
            validation_results["parsed_code"] = errors
        
        # Also validate metadata
        metadata_errors = MetadataValidator.validate_metadata(obj.metadata)
        if metadata_errors:
            validation_results["metadata"] = metadata_errors
    
    elif isinstance(obj, CodeMetadata):
        errors = MetadataValidator.validate_metadata(obj)
        if errors:
            validation_results["metadata"] = errors
    
    else:
        validation_results["unknown"] = [f"Unknown object type: {type(obj)}"]
    
    return validation_results