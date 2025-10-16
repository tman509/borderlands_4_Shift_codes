"""
Unit tests for validation logic.
"""

import pytest
from datetime import datetime, timezone
from src.models.validators import (
    ConfigValidator, CodeValidator, MetadataValidator, validate_all
)
from src.models.config import SourceConfig, ChannelConfig, SourceType
from src.models.code import ParsedCode, CodeMetadata


class TestConfigValidator:
    """Test cases for configuration validation."""
    
    def test_valid_source_config(self):
        """Test validation of valid source configuration."""
        source = SourceConfig(
            id=1,
            name="Valid Source",
            url="https://example.com",
            type=SourceType.HTML,
            enabled=True
        )
        
        errors = ConfigValidator.validate_source_config(source)
        assert len(errors) == 0
    
    def test_invalid_source_config(self):
        """Test validation of invalid source configurations."""
        # Invalid ID
        source = SourceConfig(
            id=-1,
            name="Invalid Source",
            url="https://example.com",
            type=SourceType.HTML
        )
        errors = ConfigValidator.validate_source_config(source)
        assert any("ID must be positive" in error for error in errors)
        
        # Empty name
        source.id = 1
        source.name = ""
        errors = ConfigValidator.validate_source_config(source)
        assert any("name is required" in error for error in errors)
        
        # Invalid URL
        source.name = "Valid Name"
        source.url = "not-a-url"
        errors = ConfigValidator.validate_source_config(source)
        assert any("Invalid URL format" in error for error in errors)
    
    def test_reddit_source_validation(self):
        """Test Reddit-specific source validation."""
        source = SourceConfig(
            id=1,
            name="Reddit Source",
            url="https://reddit.com/r/test",
            type=SourceType.REDDIT,
            parser_hints={}  # Missing subreddit
        )
        
        errors = ConfigValidator.validate_source_config(source)
        assert any("subreddit" in error for error in errors)
        
        # Valid Reddit source
        source.parser_hints = {"subreddit": "borderlands3"}
        errors = ConfigValidator.validate_source_config(source)
        assert len(errors) == 0
    
    def test_valid_channel_config(self):
        """Test validation of valid channel configuration."""
        channel = ChannelConfig(
            id="123456789",
            name="test-channel",
            webhook_url="https://discord.com/api/webhooks/123/abc",
            enabled=True
        )
        
        errors = ConfigValidator.validate_channel_config(channel)
        assert len(errors) == 0
    
    def test_invalid_channel_config(self):
        """Test validation of invalid channel configurations."""
        # Empty ID
        channel = ChannelConfig(
            id="",
            name="test-channel",
            webhook_url="https://discord.com/api/webhooks/123/abc"
        )
        errors = ConfigValidator.validate_channel_config(channel)
        assert any("Channel ID is required" in error for error in errors)
        
        # Invalid webhook URL
        channel.id = "123456789"
        channel.webhook_url = "https://example.com/not-discord"
        errors = ConfigValidator.validate_channel_config(channel)
        assert any("Invalid Discord webhook URL" in error for error in errors)


class TestCodeValidator:
    """Test cases for code validation."""
    
    def test_valid_code_formats(self):
        """Test validation of valid code formats."""
        valid_codes = [
            "ABCDE-FGHIJ-KLMNO-PQRST-UVWXY",  # 5x5
            "1234-5678-9012-3456",             # 4x4
            "ABCD-EFGH-IJKL-MNOP-QRST"        # 4x5
        ]
        
        for code in valid_codes:
            assert CodeValidator.is_valid_format(code), f"Code {code} should be valid"
    
    def test_invalid_code_formats(self):
        """Test validation of invalid code formats."""
        invalid_codes = [
            "TOO-SHORT",
            "TOOLONG-TOOLONG-TOOLONG-TOOLONG-TOOLONG-EXTRA",
            "INVALID_FORMAT",
            "",
            "12345"
        ]
        
        for code in invalid_codes:
            assert not CodeValidator.is_valid_format(code), f"Code {code} should be invalid"
    
    def test_test_code_detection(self):
        """Test detection of test/example codes."""
        test_codes = [
            "XXXXX-XXXXX-XXXXX-XXXXX-XXXXX",  # All X's
            "00000-00000-00000-00000-00000",  # All 0's
            "11111-11111-11111-11111-11111",  # All 1's
            "ABCDE-FGHIJ-KLMNO-PQRST-UVWXY", # Alphabetical
            "12345-67890-12345-67890-12345"   # Number sequence
        ]
        
        for code in test_codes:
            assert CodeValidator.is_likely_test_code(code), f"Code {code} should be detected as test code"
    
    def test_code_normalization(self):
        """Test code normalization."""
        test_cases = [
            ("abcde fghij klmno pqrst uvwxy", "ABCDE-FGHIJ-KLMNO-PQRST-UVWXY"),
            ("1234 5678 9012 3456", "1234-5678-9012-3456"),
            ("ABCD-EFGH-IJKL-MNOP", "ABCD-EFGH-IJKL-MNOP"),  # Already normalized
            ("", ""),  # Empty string
        ]
        
        for input_code, expected in test_cases:
            result = CodeValidator.normalize_code(input_code)
            assert result == expected, f"Expected {expected}, got {result}"
    
    def test_parsed_code_validation(self):
        """Test validation of ParsedCode objects."""
        # Valid code
        code = ParsedCode(
            code_canonical="ABCDE-FGHIJ-KLMNO-PQRST-UVWXY",
            code_display="ABCDE-FGHIJ-KLMNO-PQRST-UVWXY",
            reward_type="golden key",
            platforms=["pc", "xbox"],
            source_id=1,
            confidence_score=0.9
        )
        
        errors = CodeValidator.validate_parsed_code(code)
        assert len(errors) == 0
        
        # Invalid canonical format
        code.code_canonical = "INVALID"
        errors = CodeValidator.validate_parsed_code(code)
        assert any("Invalid canonical code format" in error for error in errors)
        
        # Invalid confidence score
        code.code_canonical = "ABCDE-FGHIJ-KLMNO-PQRST-UVWXY"
        code.confidence_score = 1.5
        errors = CodeValidator.validate_parsed_code(code)
        assert any("Confidence score must be between" in error for error in errors)
        
        # Invalid platforms
        code.confidence_score = 0.9
        code.platforms = ["invalid_platform"]
        errors = CodeValidator.validate_parsed_code(code)
        assert any("Invalid platforms" in error for error in errors)


class TestMetadataValidator:
    """Test cases for metadata validation."""
    
    def test_valid_metadata(self):
        """Test validation of valid metadata."""
        metadata = CodeMetadata(
            reward_type="golden key",
            platforms=["pc", "xbox"],
            confidence_score=0.8,
            expires_at=datetime.now(timezone.utc).replace(year=2030)
        )
        
        errors = MetadataValidator.validate_metadata(metadata)
        assert len(errors) == 0
    
    def test_invalid_reward_type(self):
        """Test validation of invalid reward types."""
        metadata = CodeMetadata(
            reward_type="invalid_reward",
            confidence_score=0.8
        )
        
        errors = MetadataValidator.validate_metadata(metadata)
        assert any("Unknown reward type" in error for error in errors)
    
    def test_invalid_platforms(self):
        """Test validation of invalid platforms."""
        metadata = CodeMetadata(
            platforms=["invalid_platform"],
            confidence_score=0.8
        )
        
        errors = MetadataValidator.validate_metadata(metadata)
        assert any("Invalid platforms" in error for error in errors)
    
    def test_expired_metadata(self):
        """Test validation of expired metadata."""
        # Recently expired (should be allowed with tolerance)
        recent_past = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        metadata = CodeMetadata(
            expires_at=recent_past,
            confidence_score=0.8
        )
        
        errors = MetadataValidator.validate_metadata(metadata)
        # Should not have expiration errors for recently expired
        
        # Long expired (should trigger error)
        old_past = datetime.now(timezone.utc).replace(year=2020)
        metadata.expires_at = old_past
        errors = MetadataValidator.validate_metadata(metadata)
        assert any("more than 1 hour in the past" in error for error in errors)


class TestValidateAll:
    """Test cases for the validate_all function."""
    
    def test_validate_source_config(self):
        """Test validate_all with SourceConfig."""
        source = SourceConfig(
            id=1,
            name="Test Source",
            url="https://example.com",
            type=SourceType.HTML
        )
        
        results = validate_all(source)
        assert len(results) == 0  # No errors
        
        # Invalid source
        source.id = -1
        results = validate_all(source)
        assert "source_config" in results
        assert len(results["source_config"]) > 0
    
    def test_validate_parsed_code(self):
        """Test validate_all with ParsedCode."""
        code = ParsedCode(
            code_canonical="ABCDE-FGHIJ-KLMNO-PQRST-UVWXY",
            code_display="ABCDE-FGHIJ-KLMNO-PQRST-UVWXY",
            source_id=1
        )
        
        results = validate_all(code)
        assert len(results) == 0  # No errors
        
        # Invalid code
        code.code_canonical = "INVALID"
        results = validate_all(code)
        assert "parsed_code" in results
        assert len(results["parsed_code"]) > 0
    
    def test_validate_unknown_object(self):
        """Test validate_all with unknown object type."""
        unknown_obj = {"test": "object"}
        
        results = validate_all(unknown_obj)
        assert "unknown" in results
        assert "Unknown object type" in results["unknown"][0]