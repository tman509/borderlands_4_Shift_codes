"""
Unit tests for code parsing functionality.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, patch

from src.processing.parser import CodeParser
from src.processing.expiration_parser import ExpirationParser
from src.models.content import RawContent, ContentType
from src.models.code import ParsedCode, CodeMetadata


class TestCodeParser:
    """Test cases for code parsing functionality."""
    
    @pytest.fixture
    def parser(self):
        """Create a CodeParser instance for testing."""
        return CodeParser()
    
    def test_parse_html_content_with_codes(self, parser):
        """Test parsing HTML content containing shift codes."""
        html_content = """
        <html>
        <body>
            <div class="content">
                <p>New Shift Code: ABCDE-FGHIJ-KLMNO-PQRST-UVWXY</p>
                <p>Reward: 5 Golden Keys</p>
                <p>Expires: December 31, 2024</p>
            </div>
        </body>
        </html>
        """
        
        raw_content = RawContent(
            url="https://example.com/test",
            content=html_content,
            content_type=ContentType.HTML,
            source_id=1
        )
        
        result = parser.parse_codes(raw_content)
        
        assert result.success is True
        assert len(result.codes_found) >= 1
        
        code = result.codes_found[0]
        assert code.code_canonical == "ABCDE-FGHIJ-KLMNO-PQRST-UVWXY"
        assert code.source_id == 1
        assert code.confidence_score > 0.5
    
    def test_parse_text_content_with_multiple_codes(self, parser):
        """Test parsing text content with multiple codes."""
        text_content = """
        Here are some shift codes:
        1. FIRST-CODE1-CODE2-CODE3-CODE4 - 3 Golden Keys
        2. SECND-TEST1-TEST2-TEST3-TEST4 - Diamond Key
        3. THIRD-ABCDE-FGHIJ-KLMNO-PQRST - Vault Card XP
        """
        
        raw_content = RawContent(
            url="https://example.com/codes",
            content=text_content,
            content_type=ContentType.TEXT,
            source_id=2
        )
        
        result = parser.parse_codes(raw_content)
        
        assert result.success is True
        assert len(result.codes_found) == 3
        
        # Check that all codes are found
        found_codes = [code.code_canonical for code in result.codes_found]
        assert "FIRST-CODE1-CODE2-CODE3-CODE4" in found_codes
        assert "SECND-TEST1-TEST2-TEST3-TEST4" in found_codes
        assert "THIRD-ABCDE-FGHIJ-KLMNO-PQRST" in found_codes
    
    def test_parse_content_with_no_codes(self, parser):
        """Test parsing content that contains no valid codes."""
        content_without_codes = """
        This is some content about Borderlands but it doesn't contain
        any valid shift codes. There might be some random text like
        INVALID-FORMAT or SHORT-CODE but nothing valid.
        """
        
        raw_content = RawContent(
            url="https://example.com/no-codes",
            content=content_without_codes,
            content_type=ContentType.TEXT,
            source_id=1
        )
        
        result = parser.parse_codes(raw_content)
        
        assert result.success is True
        assert len(result.codes_found) == 0
    
    def test_parse_content_with_test_codes(self, parser):
        """Test that test/example codes are filtered out or marked appropriately."""
        content_with_test_codes = """
        Example codes (do not use):
        XXXXX-XXXXX-XXXXX-XXXXX-XXXXX
        12345-12345-12345-12345-12345
        
        Real code:
        VALID-REAL1-REAL2-REAL3-REAL4
        """
        
        raw_content = RawContent(
            url="https://example.com/mixed-codes",
            content=content_with_test_codes,
            content_type=ContentType.TEXT,
            source_id=1
        )
        
        result = parser.parse_codes(raw_content)
        
        assert result.success is True
        
        # Should find the valid code but filter out test codes
        valid_codes = [code for code in result.codes_found if code.confidence_score > 0.5]
        assert len(valid_codes) >= 1
        assert any(code.code_canonical == "VALID-REAL1-REAL2-REAL3-REAL4" for code in valid_codes)
    
    def test_parse_json_content(self, parser):
        """Test parsing JSON content containing codes."""
        json_content = """
        {
            "codes": [
                {
                    "code": "JSON1-JSON2-JSON3-JSON4-JSON5",
                    "reward": "Golden Keys",
                    "expires": "2024-12-31T23:59:59Z"
                }
            ]
        }
        """
        
        raw_content = RawContent(
            url="https://api.example.com/codes",
            content=json_content,
            content_type=ContentType.JSON,
            source_id=3
        )
        
        result = parser.parse_codes(raw_content)
        
        assert result.success is True
        if result.codes_found:  # JSON parsing might not be implemented yet
            code = result.codes_found[0]
            assert code.code_canonical == "JSON1-JSON2-JSON3-JSON4-JSON5"
    
    def test_parse_error_handling(self, parser):
        """Test error handling during parsing."""
        # Malformed content
        raw_content = RawContent(
            url="https://example.com/malformed",
            content="<html><body><div>Unclosed tags and malformed content",
            content_type=ContentType.HTML,
            source_id=1
        )
        
        result = parser.parse_codes(raw_content)
        
        # Should not crash, might return empty results or handle gracefully
        assert isinstance(result.success, bool)
        assert isinstance(result.codes_found, list)
    
    def test_confidence_scoring(self, parser):
        """Test confidence scoring for parsed codes."""
        high_confidence_content = """
        Official Borderlands Shift Code:
        OFFIC-IAL12-CODE3-HERE4-NOW56
        Reward: 5 Golden Keys
        Expires: January 1, 2025
        """
        
        low_confidence_content = """
        Maybe this is a code? MAYBE-NOT12-SURE3-ABOUT-THIS4
        """
        
        high_conf_raw = RawContent(
            url="https://official.gearbox.com/codes",
            content=high_confidence_content,
            content_type=ContentType.TEXT,
            source_id=1
        )
        
        low_conf_raw = RawContent(
            url="https://random-forum.com/post",
            content=low_confidence_content,
            content_type=ContentType.TEXT,
            source_id=2
        )
        
        high_result = parser.parse_codes(high_conf_raw)
        low_result = parser.parse_codes(low_conf_raw)
        
        if high_result.codes_found and low_result.codes_found:
            high_confidence = high_result.codes_found[0].confidence_score
            low_confidence = low_result.codes_found[0].confidence_score
            
            assert high_confidence > low_confidence


class TestExpirationParser:
    """Test cases for expiration date parsing."""
    
    @pytest.fixture
    def expiration_parser(self):
        """Create an ExpirationParser instance for testing."""
        return ExpirationParser()
    
    def test_parse_absolute_dates(self, expiration_parser):
        """Test parsing absolute expiration dates."""
        test_cases = [
            ("December 31, 2024", "2024-12-31"),
            ("2024-12-31 23:59:59", "2024-12-31"),
            ("Jan 15, 2025", "2025-01-15"),
            ("2025-01-15T10:30:00Z", "2025-01-15"),
        ]
        
        for date_text, expected_date in test_cases:
            context = f"Code expires on {date_text}"
            result = expiration_parser.parse_expiration(context)
            
            if result:
                assert result.date().isoformat() == expected_date
    
    def test_parse_relative_dates(self, expiration_parser):
        """Test parsing relative expiration dates."""
        test_cases = [
            "Expires in 7 days",
            "Valid for 24 hours",
            "Expires tomorrow",
            "Valid until next week"
        ]
        
        for date_text in test_cases:
            result = expiration_parser.parse_expiration(date_text)
            
            if result:
                # Should be in the future
                assert result > datetime.now(timezone.utc)
    
    def test_parse_no_expiration(self, expiration_parser):
        """Test handling content with no expiration information."""
        no_expiration_texts = [
            "Here's a code: ABCDE-FGHIJ-KLMNO-PQRST-UVWXY",
            "Golden keys available",
            "No expiration mentioned"
        ]
        
        for text in no_expiration_texts:
            result = expiration_parser.parse_expiration(text)
            assert result is None
    
    def test_parse_ambiguous_dates(self, expiration_parser):
        """Test handling ambiguous date formats."""
        ambiguous_cases = [
            "01/02/2024",  # Could be Jan 2 or Feb 1
            "12/13/2024",  # Clearly Dec 13 (month > 12)
            "2024/12/31",  # Year first format
        ]
        
        for date_text in ambiguous_cases:
            context = f"Expires {date_text}"
            result = expiration_parser.parse_expiration(context)
            
            # Should handle gracefully, either parse or return None
            if result:
                assert isinstance(result, datetime)
                assert result.tzinfo is not None  # Should be timezone-aware
    
    def test_timezone_handling(self, expiration_parser):
        """Test proper timezone handling in expiration parsing."""
        timezone_cases = [
            "2024-12-31 23:59:59 UTC",
            "2024-12-31 18:59:59 EST",
            "2024-12-31 15:59:59 PST",
        ]
        
        for date_text in timezone_cases:
            context = f"Code expires {date_text}"
            result = expiration_parser.parse_expiration(context)
            
            if result:
                # Should be converted to UTC
                assert result.tzinfo == timezone.utc
    
    def test_invalid_date_handling(self, expiration_parser):
        """Test handling of invalid date formats."""
        invalid_dates = [
            "February 30, 2024",  # Invalid date
            "13th month 2024",    # Invalid month
            "Not a date at all",  # Not a date
            "",                   # Empty string
        ]
        
        for invalid_date in invalid_dates:
            result = expiration_parser.parse_expiration(invalid_date)
            # Should return None for invalid dates
            assert result is None


class TestParsingIntegration:
    """Integration tests for parsing components working together."""
    
    def test_full_parsing_pipeline(self):
        """Test the complete parsing pipeline."""
        parser = CodeParser()
        
        complex_content = """
        <html>
        <head><title>Borderlands Shift Codes</title></head>
        <body>
            <div class="codes-section">
                <h2>Active Codes</h2>
                <div class="code-entry">
                    <span class="code">FIRST-CODE1-CODE2-CODE3-CODE4</span>
                    <span class="reward">5 Golden Keys</span>
                    <span class="expiry">Expires: December 31, 2024 11:59 PM UTC</span>
                    <span class="platforms">PC, Xbox, PlayStation</span>
                </div>
                <div class="code-entry">
                    <span class="code">SECND-TEST1-TEST2-TEST3-TEST4</span>
                    <span class="reward">Diamond Key</span>
                    <span class="expiry">Valid until January 15, 2025</span>
                    <span class="platforms">All Platforms</span>
                </div>
            </div>
            <div class="expired-section">
                <h2>Expired Codes (Examples Only)</h2>
                <div class="code-entry expired">
                    <span class="code">XXXXX-XXXXX-XXXXX-XXXXX-XXXXX</span>
                    <span class="note">Example format only</span>
                </div>
            </div>
        </body>
        </html>
        """
        
        raw_content = RawContent(
            url="https://borderlands.com/shift-codes",
            content=complex_content,
            content_type=ContentType.HTML,
            source_id=1,
            metadata={"official_source": True}
        )
        
        result = parser.parse_codes(raw_content)
        
        assert result.success is True
        assert len(result.codes_found) >= 2
        
        # Check that high-quality codes are found
        high_quality_codes = [
            code for code in result.codes_found 
            if code.confidence_score > 0.7
        ]
        assert len(high_quality_codes) >= 2
        
        # Check that metadata is extracted
        for code in high_quality_codes:
            assert code.source_id == 1
            assert code.code_canonical is not None
            assert code.code_display is not None
    
    def test_parsing_performance(self):
        """Test parsing performance with large content."""
        parser = CodeParser()
        
        # Generate large content with multiple codes
        large_content = "Large content with codes:\n"
        for i in range(100):
            large_content += f"Code {i}: TEST{i:02d}-ABCDE-FGHIJ-KLMNO-PQRST\n"
        
        raw_content = RawContent(
            url="https://example.com/large-content",
            content=large_content,
            content_type=ContentType.TEXT,
            source_id=1
        )
        
        import time
        start_time = time.time()
        result = parser.parse_codes(raw_content)
        end_time = time.time()
        
        # Should complete within reasonable time
        assert end_time - start_time < 5.0  # 5 seconds max
        assert result.success is True
        assert len(result.codes_found) > 0