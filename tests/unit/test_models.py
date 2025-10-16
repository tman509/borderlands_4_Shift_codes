"""
Unit tests for data models.
"""

import pytest
from datetime import datetime, timezone
from src.models.code import ParsedCode, CodeMetadata, CodeStatus, ValidationResult
from src.models.config import SourceConfig, SourceType, ChannelConfig
from src.models.content import RawContent, ContentType


class TestParsedCode:
    """Test cases for ParsedCode model."""
    
    def test_parsed_code_creation(self):
        """Test creating a ParsedCode instance."""
        code = ParsedCode(
            code_canonical="ABCDE-FGHIJ-KLMNO-PQRST-UVWXY",
            code_display="abcde-fghij-klmno-pqrst-uvwxy",
            reward_type="golden key",
            platforms=["pc", "xbox"],
            source_id=1
        )
        
        assert code.code_canonical == "ABCDE-FGHIJ-KLMNO-PQRST-UVWXY"
        assert code.code_display == "abcde-fghij-klmno-pqrst-uvwxy"
        assert code.reward_type == "golden key"
        assert code.platforms == ["pc", "xbox"]
        assert code.source_id == 1
        assert code.status == CodeStatus.NEW
    
    def test_code_normalization(self):
        """Test code normalization functionality."""
        code = ParsedCode(
            code_canonical="ABCDE-FGHIJ-KLMNO-PQRST-UVWXY",
            code_display="abcde fghij klmno pqrst uvwxy"
        )
        
        normalized = code._normalize_code_string("abcde fghij klmno pqrst uvwxy")
        assert normalized == "ABCDE-FGHIJ-KLMNO-PQRST-UVWXY"
    
    def test_code_validation(self):
        """Test code format validation."""
        # Valid codes
        assert ParsedCode._is_valid_code_format("ABCDE-FGHIJ-KLMNO-PQRST-UVWXY")
        assert ParsedCode._is_valid_code_format("1234-5678-9012-3456")
        
        # Invalid codes
        assert not ParsedCode._is_valid_code_format("INVALID")
        assert not ParsedCode._is_valid_code_format("TOO-SHORT")
        assert not ParsedCode._is_valid_code_format("")
    
    def test_expiration_check(self):
        """Test expiration checking."""
        # Non-expired code
        future_time = datetime.now(timezone.utc).replace(year=2030)
        code = ParsedCode(
            code_canonical="TEST1-TEST2-TEST3-TEST4-TEST5",
            code_display="TEST1-TEST2-TEST3-TEST4-TEST5",
            expires_at=future_time
        )
        assert not code.is_expired()
        
        # Expired code
        past_time = datetime.now(timezone.utc).replace(year=2020)
        code.expires_at = past_time
        assert code.is_expired()
        
        # No expiration
        code.expires_at = None
        assert not code.is_expired()
    
    def test_to_dict_conversion(self):
        """Test converting ParsedCode to dictionary."""
        code = ParsedCode(
            code_canonical="ABCDE-FGHIJ-KLMNO-PQRST-UVWXY",
            code_display="ABCDE-FGHIJ-KLMNO-PQRST-UVWXY",
            reward_type="golden key",
            platforms=["pc"],
            source_id=1
        )
        
        code_dict = code.to_dict()
        
        assert code_dict["code_canonical"] == "ABCDE-FGHIJ-KLMNO-PQRST-UVWXY"
        assert code_dict["reward_type"] == "golden key"
        assert code_dict["platforms"] == ["pc"]
        assert code_dict["source_id"] == 1
        assert "metadata" in code_dict
    
    def test_from_dict_creation(self):
        """Test creating ParsedCode from dictionary."""
        code_dict = {
            "code_canonical": "ABCDE-FGHIJ-KLMNO-PQRST-UVWXY",
            "code_display": "ABCDE-FGHIJ-KLMNO-PQRST-UVWXY",
            "reward_type": "golden key",
            "platforms": ["pc"],
            "source_id": 1,
            "status": "new"
        }
        
        code = ParsedCode.from_dict(code_dict)
        
        assert code.code_canonical == "ABCDE-FGHIJ-KLMNO-PQRST-UVWXY"
        assert code.reward_type == "golden key"
        assert code.platforms == ["pc"]
        assert code.status == CodeStatus.NEW


class TestCodeMetadata:
    """Test cases for CodeMetadata model."""
    
    def test_metadata_creation(self):
        """Test creating CodeMetadata instance."""
        metadata = CodeMetadata(
            reward_type="golden key",
            platforms=["pc", "xbox"],
            confidence_score=0.9
        )
        
        assert metadata.reward_type == "golden key"
        assert metadata.platforms == ["pc", "xbox"]
        assert metadata.confidence_score == 0.9
        assert not metadata.is_expiration_estimated
    
    def test_metadata_validation(self):
        """Test metadata validation."""
        # Valid metadata
        metadata = CodeMetadata(confidence_score=0.5)
        assert metadata.confidence_score == 0.5
        
        # Invalid confidence score
        with pytest.raises(ValueError):
            CodeMetadata(confidence_score=1.5)
        
        with pytest.raises(ValueError):
            CodeMetadata(confidence_score=-0.1)
    
    def test_metadata_serialization(self):
        """Test metadata to/from dict conversion."""
        metadata = CodeMetadata(
            reward_type="diamond key",
            platforms=["pc"],
            confidence_score=0.8
        )
        
        metadata_dict = metadata.to_dict()
        assert metadata_dict["reward_type"] == "diamond key"
        assert metadata_dict["platforms"] == ["pc"]
        assert metadata_dict["confidence_score"] == 0.8
        
        # Test round-trip conversion
        restored_metadata = CodeMetadata.from_dict(metadata_dict)
        assert restored_metadata.reward_type == metadata.reward_type
        assert restored_metadata.platforms == metadata.platforms
        assert restored_metadata.confidence_score == metadata.confidence_score


class TestSourceConfig:
    """Test cases for SourceConfig model."""
    
    def test_source_config_creation(self):
        """Test creating SourceConfig instance."""
        source = SourceConfig(
            id=1,
            name="Test Source",
            url="https://example.com",
            type=SourceType.HTML,
            enabled=True
        )
        
        assert source.id == 1
        assert source.name == "Test Source"
        assert source.url == "https://example.com"
        assert source.type == SourceType.HTML
        assert source.enabled is True
    
    def test_source_config_validation(self):
        """Test source configuration validation."""
        # Valid source
        source = SourceConfig(
            id=1,
            name="Valid Source",
            url="https://example.com",
            type=SourceType.HTML
        )
        assert source.name == "Valid Source"
        
        # Invalid ID
        with pytest.raises(ValueError):
            SourceConfig(
                id=0,
                name="Invalid Source",
                url="https://example.com",
                type=SourceType.HTML
            )
        
        # Empty name
        with pytest.raises(ValueError):
            SourceConfig(
                id=1,
                name="",
                url="https://example.com",
                type=SourceType.HTML
            )
    
    def test_source_config_serialization(self):
        """Test source config to/from dict conversion."""
        source = SourceConfig(
            id=1,
            name="Test Source",
            url="https://example.com",
            type=SourceType.RSS,
            enabled=False,
            parser_hints={"test": "value"}
        )
        
        source_dict = source.to_dict()
        assert source_dict["id"] == 1
        assert source_dict["name"] == "Test Source"
        assert source_dict["type"] == "rss"
        assert source_dict["enabled"] is False
        assert source_dict["parser_hints"] == {"test": "value"}
        
        # Test round-trip conversion
        restored_source = SourceConfig.from_dict(source_dict)
        assert restored_source.id == source.id
        assert restored_source.name == source.name
        assert restored_source.type == source.type
        assert restored_source.enabled == source.enabled


class TestRawContent:
    """Test cases for RawContent model."""
    
    def test_raw_content_creation(self):
        """Test creating RawContent instance."""
        content = RawContent(
            url="https://example.com",
            content="Test content",
            content_type=ContentType.HTML,
            source_id=1
        )
        
        assert content.url == "https://example.com"
        assert content.content == "Test content"
        assert content.content_type == ContentType.HTML
        assert content.source_id == 1
        assert content.fetched_at is not None
    
    def test_raw_content_validation(self):
        """Test raw content validation."""
        # Valid content
        content = RawContent(
            url="https://example.com",
            content="Valid content",
            content_type=ContentType.HTML,
            source_id=1
        )
        assert content.content == "Valid content"
        
        # Empty content
        with pytest.raises(ValueError):
            RawContent(
                url="https://example.com",
                content="",
                content_type=ContentType.HTML,
                source_id=1
            )
        
        # Invalid source ID
        with pytest.raises(ValueError):
            RawContent(
                url="https://example.com",
                content="Test content",
                content_type=ContentType.HTML,
                source_id=0
            )
    
    def test_raw_content_serialization(self):
        """Test raw content serialization."""
        content = RawContent(
            url="https://example.com",
            content="Test content",
            content_type=ContentType.JSON,
            source_id=1,
            headers={"content-type": "application/json"}
        )
        
        content_dict = content.to_dict()
        assert content_dict["url"] == "https://example.com"
        assert content_dict["content"] == "Test content"
        assert content_dict["content_type"] == "json"
        assert content_dict["source_id"] == 1
        assert content_dict["headers"] == {"content-type": "application/json"}
        
        # Test round-trip conversion
        restored_content = RawContent.from_dict(content_dict)
        assert restored_content.url == content.url
        assert restored_content.content == content.content
        assert restored_content.content_type == content.content_type
        assert restored_content.source_id == content.source_id