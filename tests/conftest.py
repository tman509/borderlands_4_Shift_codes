"""
Pytest configuration and shared fixtures for the Shift Code Bot tests.
"""

import pytest
import tempfile
import os
from datetime import datetime, timezone
from typing import Dict, Any, List
from unittest.mock import Mock, MagicMock

from src.models.config import Config, SourceConfig, ChannelConfig, SourceType
from src.models.code import ParsedCode, CodeMetadata, CodeStatus
from src.models.content import RawContent, ContentType
from src.storage.database import Database
from src.core.config_manager import ConfigManager


@pytest.fixture
def temp_database():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    
    try:
        database = Database(f"sqlite:///{db_path}")
        database.initialize_schema()
        yield database
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


@pytest.fixture
def sample_config() -> Config:
    """Create a sample configuration for testing."""
    return Config(
        database_url="sqlite:///test.db",
        sources=[
            SourceConfig(
                id=1,
                name="Test HTML Source",
                url="https://example.com/codes",
                type=SourceType.HTML,
                enabled=True,
                parser_hints={"selectors": [".code-text"]}
            ),
            SourceConfig(
                id=2,
                name="Test RSS Source", 
                url="https://example.com/rss",
                type=SourceType.RSS,
                enabled=True
            )
        ],
        discord_channels=[
            ChannelConfig(
                id="123456789",
                name="test-channel",
                webhook_url="https://discord.com/api/webhooks/test",
                enabled=True
            )
        ]
    )


@pytest.fixture
def mock_config_manager(sample_config):
    """Create a mock configuration manager."""
    mock_manager = Mock(spec=ConfigManager)
    mock_manager.load_config.return_value = sample_config
    mock_manager.get_sources.return_value = sample_config.sources
    return mock_manager


@pytest.fixture
def sample_raw_content() -> RawContent:
    """Create sample raw content for testing."""
    return RawContent(
        url="https://example.com/test",
        content="Test content with code ABCDE-FGHIJ-KLMNO-PQRST-UVWXY",
        content_type=ContentType.HTML,
        source_id=1,
        headers={"content-type": "text/html"},
        metadata={"test": True}
    )


@pytest.fixture
def sample_parsed_code() -> ParsedCode:
    """Create a sample parsed code for testing."""
    return ParsedCode(
        code_canonical="ABCDE-FGHIJ-KLMNO-PQRST-UVWXY",
        code_display="ABCDE-FGHIJ-KLMNO-PQRST-UVWXY",
        reward_type="golden key",
        platforms=["pc", "xbox", "playstation"],
        expires_at=datetime.now(timezone.utc),
        source_id=1,
        context="Test context",
        confidence_score=0.9,
        metadata=CodeMetadata(
            reward_type="golden key",
            platforms=["pc", "xbox", "playstation"]
        ),
        status=CodeStatus.NEW,
        first_seen_at=datetime.now(timezone.utc)
    )


@pytest.fixture
def sample_parsed_codes() -> List[ParsedCode]:
    """Create multiple sample parsed codes for testing."""
    codes = []
    for i in range(3):
        code = ParsedCode(
            code_canonical=f"TEST{i}-FGHIJ-KLMNO-PQRST-UVWXY",
            code_display=f"TEST{i}-FGHIJ-KLMNO-PQRST-UVWXY",
            reward_type="golden key",
            platforms=["pc"],
            source_id=1,
            context=f"Test context {i}",
            confidence_score=0.8 + (i * 0.05),
            status=CodeStatus.NEW,
            first_seen_at=datetime.now(timezone.utc)
        )
        codes.append(code)
    return codes


@pytest.fixture
def mock_requests():
    """Mock requests module for HTTP testing."""
    with pytest.mock.patch('requests.Session') as mock_session:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "<html><body>Test content</body></html>"
        mock_response.headers = {"content-type": "text/html"}
        mock_response.raise_for_status.return_value = None
        
        mock_session.return_value.get.return_value = mock_response
        mock_session.return_value.head.return_value = mock_response
        
        yield mock_session


@pytest.fixture
def mock_discord_webhook():
    """Mock Discord webhook for notification testing."""
    with pytest.mock.patch('requests.post') as mock_post:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "test_message_id"}
        mock_post.return_value = mock_response
        yield mock_post


@pytest.fixture
def html_test_content():
    """Sample HTML content for parser testing."""
    return """
    <html>
    <head><title>Test Page</title></head>
    <body>
        <div class="content">
            <p>New Shift Code available!</p>
            <div class="code-text">ABCDE-FGHIJ-KLMNO-PQRST-UVWXY</div>
            <p>Reward: 5 Golden Keys</p>
            <p>Expires: 2024-12-31 23:59:59 UTC</p>
        </div>
        <div class="other-content">
            <p>Some other content</p>
            <div class="invalid-code">XXXXX-XXXXX-XXXXX-XXXXX-XXXXX</div>
        </div>
    </body>
    </html>
    """


@pytest.fixture
def rss_test_content():
    """Sample RSS content for parser testing."""
    return """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
        <channel>
            <title>Test RSS Feed</title>
            <description>Test feed for shift codes</description>
            <item>
                <title>New Shift Code Available</title>
                <description>Use code ABCDE-FGHIJ-KLMNO-PQRST-UVWXY for 5 Golden Keys</description>
                <pubDate>Mon, 01 Jan 2024 12:00:00 GMT</pubDate>
                <link>https://example.com/code1</link>
            </item>
            <item>
                <title>Another Code</title>
                <description>Code TEST1-TEST2-TEST3-TEST4-TEST5 expires soon!</description>
                <pubDate>Sun, 31 Dec 2023 18:00:00 GMT</pubDate>
                <link>https://example.com/code2</link>
            </item>
        </channel>
    </rss>
    """


@pytest.fixture(autouse=True)
def setup_test_logging():
    """Setup logging for tests."""
    import logging
    logging.getLogger().setLevel(logging.DEBUG)


# Test data constants
TEST_CODES = [
    "ABCDE-FGHIJ-KLMNO-PQRST-UVWXY",
    "12345-67890-ABCDE-FGHIJ-KLMNO",
    "TEST1-TEST2-TEST3-TEST4-TEST5"
]

INVALID_CODES = [
    "XXXXX-XXXXX-XXXXX-XXXXX-XXXXX",  # All X's
    "12345-12345-12345-12345-12345",  # Repeated pattern
    "ABCD-EFGH-IJKL",                 # Too short
    "TOOLONG-TOOLONG-TOOLONG-TOOLONG-TOOLONG-EXTRA"  # Too long
]

TEST_URLS = [
    "https://example.com/codes",
    "https://test.gearboxsoftware.com/shift",
    "https://borderlands.com/news"
]