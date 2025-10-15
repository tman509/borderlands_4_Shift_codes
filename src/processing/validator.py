"""
Enhanced code validation and normalization for the Shift Code Bot.
"""

import re
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Set, Tuple
from functools import lru_cache

from ..models.code import ValidationResult, CodeMetadata, ParsedCode

logger = logging.getLogger(__name__)


class CodeValidator:
    """Enhanced validator for shift codes with comprehensive validation rules."""
    
    # Valid code format patterns with priorities
    VALID_PATTERNS = [
        # Primary formats (highest confidence)
        (re.compile(r"^[A-Z0-9]{5}-[A-Z0-9]{5}-[A-Z0-9]{5}-[A-Z0-9]{5}-[A-Z0-9]{5}$"), 1.0, "5x5"),
        (re.compile(r"^[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$"), 0.9, "4x5"),
        (re.compile(r"^[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$"), 0.8, "4x4"),
        
        # Alternative separators (lower confidence)
        (re.compile(r"^[A-Z0-9]{5}_[A-Z0-9]{5}_[A-Z0-9]{5}_[A-Z0-9]{5}_[A-Z0-9]{5}$"), 0.7, "5x5_underscore"),
        (re.compile(r"^[A-Z0-9]{5}\s[A-Z0-9]{5}\s[A-Z0-9]{5}\s[A-Z0-9]{5}\s[A-Z0-9]{5}$"), 0.6, "5x5_space"),
    ]
    
    # Comprehensive test/example patterns
    TEST_PATTERNS = [
        # All same character
        re.compile(r"^([A-Z0-9])\1*-\1+-\1+-\1+-\1+$"),
        
        # Sequential patterns
        re.compile(r"^ABCDE-FGHIJ-KLMNO-PQRST-UVWXY$"),
        re.compile(r"^12345-67890-12345-67890-12345$"),
        re.compile(r"^AAAAA-BBBBB-CCCCC-DDDDD-EEEEE$"),
        
        # Common placeholders
        re.compile(r"^XXXXX-XXXXX-XXXXX-XXXXX-XXXXX$"),
        re.compile(r"^00000-00000-00000-00000-00000$"),
        re.compile(r"^11111-11111-11111-11111-11111$"),
        
        # Example patterns
        re.compile(r"^EXAMP-LECOD-EHERE-12345-ABCDE$"),
        re.compile(r"^SHIFT-CODES-EXAMP-LE123-45678$"),
        
        # Keyboard patterns
        re.compile(r"^QWERT-YUIOP-ASDFG-HJKLZ-XCVBN$"),
        re.compile(r"^12345-QWERT-ASDFG-ZXCVB-POIUY$"),
    ]
    
    # Suspicious character patterns
    SUSPICIOUS_PATTERNS = [
        # Too many repeated characters
        re.compile(r"([A-Z0-9])\1{3,}"),  # 4+ same chars in a row
        
        # Common typo patterns
        re.compile(r"[IL1]{3,}|[O0]{3,}"),  # Confusing characters
        
        # Non-random looking patterns
        re.compile(r"(ABC|123|XYZ){2,}"),  # Sequential repeats
    ]
    
    # Known invalid prefixes/suffixes that indicate examples
    EXAMPLE_INDICATORS = [
        "EXAMPLE", "SAMPLE", "TEST", "DEMO", "FAKE", "PLACEHOLDER",
        "XXXXX", "00000", "11111", "AAAAA", "ZZZZZ"
    ]
    
    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        
        # Cache for expensive validations
        self._validation_cache: Dict[str, ValidationResult] = {}
        self._normalization_cache: Dict[str, str] = {}
        
        # Statistics for adaptive validation
        self._validation_stats = {
            "total_validated": 0,
            "valid_codes": 0,
            "test_codes_detected": 0,
            "format_errors": 0
        }
    
    def validate_format(self, code: str) -> ValidationResult:
        """Enhanced format validation with comprehensive checks."""
        if not code:
            return ValidationResult(
                is_valid=False,
                canonical_code="",
                reason="Empty code",
                confidence_score=0.0
            )
        
        # Check cache first
        cache_key = code.upper().strip()
        if cache_key in self._validation_cache:
            return self._validation_cache[cache_key]
        
        try:
            # Normalize the code
            canonical_code = self.normalize_code(code)
            
            # Basic format validation
            format_result = self._validate_basic_format(canonical_code)
            if not format_result["is_valid"]:
                result = ValidationResult(
                    is_valid=False,
                    canonical_code=canonical_code,
                    reason=format_result["reason"],
                    confidence_score=0.0
                )
                self._validation_cache[cache_key] = result
                self._validation_stats["format_errors"] += 1
                return result
            
            # Advanced validation checks
            validation_checks = [
                self._check_test_patterns(canonical_code),
                self._check_suspicious_patterns(canonical_code),
                self._check_character_distribution(canonical_code),
                self._check_segment_quality(canonical_code),
                self._check_entropy(canonical_code)
            ]
            
            # Combine all validation results
            is_valid = all(check["is_valid"] for check in validation_checks)
            confidence = format_result["confidence"]
            reasons = []
            
            for check in validation_checks:
                if not check["is_valid"]:
                    reasons.append(check["reason"])
                confidence *= check["confidence_multiplier"]
            
            # Final confidence adjustment
            confidence = min(1.0, max(0.0, confidence))
            
            result = ValidationResult(
                is_valid=is_valid,
                canonical_code=canonical_code,
                reason="; ".join(reasons) if reasons else None,
                confidence_score=confidence
            )
            
            # Update statistics
            self._validation_stats["total_validated"] += 1
            if is_valid:
                self._validation_stats["valid_codes"] += 1
            if any("test" in check.get("reason", "").lower() for check in validation_checks):
                self._validation_stats["test_codes_detected"] += 1
            
            # Cache result
            self._validation_cache[cache_key] = result
            return result
            
        except Exception as e:
            self.logger.error(f"Error validating code {code}: {e}")
            return ValidationResult(
                is_valid=False,
                canonical_code=code,
                reason=f"Validation error: {str(e)}",
                confidence_score=0.0
            )
    
    def _validate_basic_format(self, canonical_code: str) -> Dict:
        """Validate basic code format against known patterns."""
        for pattern, confidence, format_name in self.VALID_PATTERNS:
            if pattern.match(canonical_code):
                return {
                    "is_valid": True,
                    "confidence": confidence,
                    "format": format_name,
                    "reason": None
                }
        
        return {
            "is_valid": False,
            "confidence": 0.0,
            "format": "unknown",
            "reason": f"Code format not recognized: {canonical_code}"
        }
    
    def _check_test_patterns(self, canonical_code: str) -> Dict:
        """Check if code matches known test/example patterns."""
        for pattern in self.TEST_PATTERNS:
            if pattern.match(canonical_code):
                return {
                    "is_valid": False,
                    "confidence_multiplier": 0.1,
                    "reason": "Code matches known test/example pattern"
                }
        
        # Check for example indicators in segments
        segments = canonical_code.split('-')
        for segment in segments:
            if segment in self.EXAMPLE_INDICATORS:
                return {
                    "is_valid": False,
                    "confidence_multiplier": 0.2,
                    "reason": f"Code contains example indicator: {segment}"
                }
        
        return {
            "is_valid": True,
            "confidence_multiplier": 1.0,
            "reason": None
        }
    
    def _check_suspicious_patterns(self, canonical_code: str) -> Dict:
        """Check for suspicious character patterns."""
        for pattern in self.SUSPICIOUS_PATTERNS:
            if pattern.search(canonical_code):
                return {
                    "is_valid": True,  # Still valid but lower confidence
                    "confidence_multiplier": 0.7,
                    "reason": "Code contains suspicious character patterns"
                }
        
        return {
            "is_valid": True,
            "confidence_multiplier": 1.0,
            "reason": None
        }
    
    def _check_character_distribution(self, canonical_code: str) -> Dict:
        """Check character distribution for randomness."""
        clean_code = canonical_code.replace('-', '')
        
        # Count character frequencies
        char_counts = {}
        for char in clean_code:
            char_counts[char] = char_counts.get(char, 0) + 1
        
        total_chars = len(clean_code)
        
        # Check for over-representation of any character
        for char, count in char_counts.items():
            frequency = count / total_chars
            if frequency > 0.4:  # More than 40% of one character
                return {
                    "is_valid": True,
                    "confidence_multiplier": 0.6,
                    "reason": f"Character '{char}' over-represented ({frequency:.1%})"
                }
        
        # Check for too few unique characters
        unique_chars = len(char_counts)
        if unique_chars < 4:  # Less than 4 unique characters in the whole code
            return {
                "is_valid": True,
                "confidence_multiplier": 0.7,
                "reason": f"Too few unique characters ({unique_chars})"
            }
        
        return {
            "is_valid": True,
            "confidence_multiplier": 1.0,
            "reason": None
        }
    
    def _check_segment_quality(self, canonical_code: str) -> Dict:
        """Check quality of individual segments."""
        segments = canonical_code.split('-')
        
        # Check for repeated segments
        unique_segments = set(segments)
        if len(unique_segments) < len(segments):
            repetition_ratio = 1 - (len(unique_segments) / len(segments))
            return {
                "is_valid": True,
                "confidence_multiplier": max(0.3, 1.0 - repetition_ratio),
                "reason": f"Repeated segments detected ({repetition_ratio:.1%} repetition)"
            }
        
        # Check for sequential segments
        for i in range(len(segments) - 1):
            if self._are_segments_sequential(segments[i], segments[i + 1]):
                return {
                    "is_valid": True,
                    "confidence_multiplier": 0.8,
                    "reason": "Sequential segments detected"
                }
        
        return {
            "is_valid": True,
            "confidence_multiplier": 1.0,
            "reason": None
        }
    
    def _check_entropy(self, canonical_code: str) -> Dict:
        """Check entropy/randomness of the code."""
        import math
        
        clean_code = canonical_code.replace('-', '')
        
        # Calculate Shannon entropy
        char_counts = {}
        for char in clean_code:
            char_counts[char] = char_counts.get(char, 0) + 1
        
        entropy = 0
        total_chars = len(clean_code)
        
        for count in char_counts.values():
            probability = count / total_chars
            entropy -= probability * math.log2(probability)
        
        # Expected entropy for random alphanumeric is ~5.17 bits
        # Lower entropy suggests less randomness
        if entropy < 3.0:  # Very low entropy
            return {
                "is_valid": True,
                "confidence_multiplier": 0.5,
                "reason": f"Low entropy ({entropy:.2f} bits) suggests non-random pattern"
            }
        elif entropy < 4.0:  # Moderately low entropy
            return {
                "is_valid": True,
                "confidence_multiplier": 0.8,
                "reason": f"Moderate entropy ({entropy:.2f} bits)"
            }
        
        return {
            "is_valid": True,
            "confidence_multiplier": 1.0,
            "reason": None
        }
    
    def _are_segments_sequential(self, seg1: str, seg2: str) -> bool:
        """Check if two segments are sequential (e.g., ABCDE -> FGHIJ)."""
        if len(seg1) != len(seg2):
            return False
        
        # Check for simple alphabetical sequence
        for i in range(len(seg1)):
            if ord(seg2[i]) != ord(seg1[i]) + len(seg1):
                return False
        
        return True
    
    @lru_cache(maxsize=1000)
    def normalize_code(self, code: str) -> str:
        """Enhanced code normalization with caching."""
        if not code:
            return ""
        
        # Remove all non-alphanumeric characters and convert to uppercase
        clean_code = re.sub(r'[^A-Z0-9]', '', code.upper())
        
        # Handle common character confusions
        clean_code = self._fix_common_typos(clean_code)
        
        # Format based on length
        if len(clean_code) == 25:  # 5x5 format
            return '-'.join([clean_code[i:i+5] for i in range(0, 25, 5)])
        elif len(clean_code) == 20:  # 4x5 format
            return '-'.join([clean_code[i:i+4] for i in range(0, 20, 4)])
        elif len(clean_code) == 16:  # 4x4 format
            return '-'.join([clean_code[i:i+4] for i in range(0, 16, 4)])
        else:
            # Return as-is if length doesn't match expected formats
            return clean_code
    
    def _fix_common_typos(self, code: str) -> str:
        """Fix common character typos in codes."""
        # Common character confusions
        typo_map = {
            'O': '0',  # Letter O to zero (context-dependent)
            'I': '1',  # Letter I to one (context-dependent)
            'S': '5',  # Letter S to five (less common)
            'Z': '2',  # Letter Z to two (less common)
        }
        
        # Only apply fixes if the result would be more "numeric"
        # This is a heuristic and might need adjustment
        result = code
        for old_char, new_char in typo_map.items():
            if old_char in result:
                # Count numeric vs alphabetic characters
                num_count = sum(1 for c in result if c.isdigit())
                alpha_count = sum(1 for c in result if c.isalpha())
                
                # If more numeric, likely the alphabetic chars are typos
                if num_count > alpha_count:
                    result = result.replace(old_char, new_char)
        
        return result
    
    def check_expiration(self, metadata: CodeMetadata) -> bool:
        """Enhanced expiration checking with timezone handling."""
        if not metadata.expires_at:
            return False  # No expiration date means not expired
        
        now = datetime.now(timezone.utc)
        
        # Handle timezone-naive datetime objects
        expires_at = metadata.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        
        # Add small buffer for network delays and processing time
        buffer = timedelta(minutes=5)
        return expires_at < (now - buffer)
    
    def is_likely_test_code(self, code: str) -> bool:
        """Enhanced test code detection."""
        canonical = self.normalize_code(code)
        
        # Use the comprehensive test pattern checking
        test_check = self._check_test_patterns(canonical)
        return not test_check["is_valid"]
    
    def validate_code_metadata(self, code: ParsedCode) -> List[str]:
        """Validate code metadata for consistency and reasonableness."""
        issues = []
        
        # Check expiration date reasonableness
        if code.expires_at:
            now = datetime.now(timezone.utc)
            
            # Check if expiration is too far in the past
            if code.expires_at < now - timedelta(days=30):
                issues.append("Expiration date is more than 30 days in the past")
            
            # Check if expiration is too far in the future
            if code.expires_at > now + timedelta(days=365 * 2):
                issues.append("Expiration date is more than 2 years in the future")
        
        # Check confidence score reasonableness
        if code.confidence_score < 0.3:
            issues.append("Very low confidence score suggests unreliable code")
        
        # Check for consistency between reward type and platforms
        if code.reward_type and code.platforms:
            if "nintendo" in code.platforms and code.reward_type in ["diamond key", "vault card"]:
                issues.append("Diamond keys and vault cards may not be available on Nintendo Switch")
        
        return issues
    
    def get_validation_stats(self) -> Dict:
        """Get validation statistics for monitoring."""
        stats = self._validation_stats.copy()
        if stats["total_validated"] > 0:
            stats["valid_rate"] = stats["valid_codes"] / stats["total_validated"]
            stats["test_detection_rate"] = stats["test_codes_detected"] / stats["total_validated"]
        else:
            stats["valid_rate"] = 0.0
            stats["test_detection_rate"] = 0.0
        
        stats["cache_size"] = len(self._validation_cache)
        return stats
    
    def clear_cache(self) -> None:
        """Clear validation caches."""
        self._validation_cache.clear()
        self._normalization_cache.clear()
        self.logger.info("Validation caches cleared")