"""
Enhanced code parsing functionality for the Shift Code Bot.
"""

import re
import logging
from typing import List, Optional, Dict, Any, Tuple, Set
from datetime import datetime, timezone
from functools import lru_cache

from ..models.content import RawContent
from ..models.code import ParsedCode, CodeMetadata

logger = logging.getLogger(__name__)


class CodeParser:
    """Enhanced parser for shift codes with multiple strategies and confidence scoring."""
    
    # Enhanced regex patterns for different code formats
    CODE_PATTERNS = [
        # Standard formats
        re.compile(r"\b[A-Z0-9]{5}(?:-[A-Z0-9]{5}){4}\b", re.I),  # 5x5 format
        re.compile(r"\b[A-Z0-9]{4}(?:-[A-Z0-9]{4}){3,4}\b", re.I),  # 4x4 format
        
        # Variations with different separators
        re.compile(r"\b[A-Z0-9]{5}(?:[_\s][A-Z0-9]{5}){4}\b", re.I),  # Underscore/space separated
        re.compile(r"\b[A-Z0-9]{25}\b", re.I),  # No separators (25 chars)
        re.compile(r"\b[A-Z0-9]{20}\b", re.I),  # No separators (20 chars)
        re.compile(r"\b[A-Z0-9]{16}\b", re.I),  # No separators (16 chars)
        
        # Codes in quotes or brackets
        re.compile(r'["\']([A-Z0-9]{5}(?:-[A-Z0-9]{5}){4})["\']', re.I),
        re.compile(r'\[([A-Z0-9]{5}(?:-[A-Z0-9]{5}){4})\]', re.I),
        re.compile(r'\(([A-Z0-9]{5}(?:-[A-Z0-9]{5}){4})\)', re.I),
    ]
    
    # Enhanced reward type detection with scoring
    REWARD_KEYWORDS = {
        "golden key": {
            "primary": ["golden key", "golden keys", "gold key", "gold keys"],
            "secondary": ["5 golden keys", "3 golden keys", "5 keys", "3 keys", "key"],
            "context": ["vault", "chest", "loot"]
        },
        "diamond key": {
            "primary": ["diamond key", "diamond keys"],
            "secondary": ["diamond", "rare key"],
            "context": ["vault", "special"]
        },
        "vault card": {
            "primary": ["vault card", "vaultcard"],
            "secondary": ["card", "vault"],
            "context": ["season", "battle pass"]
        },
        "cosmetic": {
            "primary": ["cosmetic", "skin", "weapon skin", "head", "appearance"],
            "secondary": ["outfit", "customization", "style", "look"],
            "context": ["character", "weapon", "vehicle"]
        },
        "weapon": {
            "primary": ["weapon", "gun", "legendary weapon"],
            "secondary": ["rare weapon", "epic weapon", "legendary"],
            "context": ["damage", "stats", "loot"]
        },
        "eridium": {
            "primary": ["eridium"],
            "secondary": ["currency", "purple"],
            "context": ["upgrade", "purchase"]
        },
        "xp": {
            "primary": ["xp", "experience"],
            "secondary": ["exp", "level"],
            "context": ["boost", "bonus"]
        }
    }
    
    # Enhanced platform detection
    PLATFORM_KEYWORDS = {
        "pc": {
            "primary": ["pc", "steam", "epic games", "epic store"],
            "secondary": ["windows", "computer", "desktop"],
            "exclusions": ["xbox", "playstation", "nintendo"]
        },
        "xbox": {
            "primary": ["xbox", "xbox one", "xbox series", "microsoft"],
            "secondary": ["xb1", "series x", "series s"],
            "exclusions": ["playstation", "nintendo", "pc"]
        },
        "playstation": {
            "primary": ["playstation", "ps4", "ps5", "sony"],
            "secondary": ["psx", "playstation 4", "playstation 5"],
            "exclusions": ["xbox", "nintendo", "pc"]
        },
        "nintendo": {
            "primary": ["nintendo", "switch", "nintendo switch"],
            "secondary": ["ns", "switch lite"],
            "exclusions": ["xbox", "playstation", "pc"]
        }
    }
    
    # Expiration date patterns with improved parsing
    EXPIRATION_PATTERNS = [
        # Standard formats
        (r"expires?\s+(?:on\s+)?(\w+\s+\d{1,2},?\s+\d{4})", "%B %d, %Y"),
        (r"expires?\s+(\d{4}-\d{2}-\d{2})", "%Y-%m-%d"),
        (r"expires?\s+(\d{1,2}/\d{1,2}/\d{4})", "%m/%d/%Y"),
        (r"expires?\s+(\d{1,2}-\d{1,2}-\d{4})", "%m-%d-%Y"),
        
        # Relative dates
        (r"expires?\s+in\s+(\d+)\s+days?", "relative_days"),
        (r"expires?\s+in\s+(\d+)\s+hours?", "relative_hours"),
        
        # End dates
        (r"(?:valid\s+)?until\s+(\w+\s+\d{1,2},?\s+\d{4})", "%B %d, %Y"),
        (r"ends?\s+(?:on\s+)?(\w+\s+\d{1,2},?\s+\d{4})", "%B %d, %Y"),
        
        # Time included
        (r"expires?\s+(\w+\s+\d{1,2},?\s+\d{4}\s+\d{1,2}:\d{2})", "%B %d, %Y %H:%M"),
        (r"expires?\s+(\d{4}-\d{2}-\d{2}\s+\d{1,2}:\d{2})", "%Y-%m-%d %H:%M"),
    ]
    
    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        
        # Compile patterns for better performance
        self._compiled_patterns = self.CODE_PATTERNS
        
        # Cache for expensive operations
        self._reward_cache: Dict[str, Optional[str]] = {}
        self._platform_cache: Dict[str, List[str]] = {}
    
    def parse_codes(self, content: RawContent) -> List[ParsedCode]:
        """Parse shift codes from raw content with enhanced strategies."""
        try:
            # Extract codes using multiple strategies
            codes = self._extract_codes_multi_strategy(content.content)
            parsed_codes = []
            
            for code_info in codes:
                try:
                    code = code_info["code"]
                    confidence = code_info["confidence"]
                    
                    # Extract metadata for this specific code
                    metadata = self.extract_metadata(content, code)
                    
                    # Combine confidence scores
                    final_confidence = (confidence + metadata.confidence_score) / 2
                    
                    parsed_code = ParsedCode(
                        code_canonical=self._normalize_code(code),
                        code_display=code.upper(),
                        reward_type=metadata.reward_type,
                        platforms=metadata.platforms,
                        expires_at=metadata.expires_at,
                        source_id=content.source_id,
                        context=self._extract_context(content.content, code),
                        confidence_score=final_confidence,
                        metadata=metadata,
                        first_seen_at=datetime.now(timezone.utc)
                    )
                    
                    parsed_codes.append(parsed_code)
                    self.logger.debug(f"Parsed code: {parsed_code.code_display} (confidence: {final_confidence:.2f})")
                    
                except Exception as e:
                    self.logger.warning(f"Failed to process code {code}: {e}")
                    continue
            
            # Sort by confidence score (highest first)
            parsed_codes.sort(key=lambda x: x.confidence_score, reverse=True)
            
            self.logger.info(f"Parsed {len(parsed_codes)} codes from {content.url}")
            return parsed_codes
            
        except Exception as e:
            self.logger.error(f"Error parsing codes from {content.url}: {e}")
            return []
    
    def _extract_codes_multi_strategy(self, text: str) -> List[Dict[str, Any]]:
        """Extract codes using multiple strategies with confidence scoring."""
        found_codes: Dict[str, Dict[str, Any]] = {}
        
        # Strategy 1: Direct pattern matching
        for i, pattern in enumerate(self._compiled_patterns):
            matches = pattern.findall(text)
            for match in matches:
                # Handle grouped matches
                code = match if isinstance(match, str) else match[0] if match else ""
                if not code:
                    continue
                
                normalized = self._normalize_code(code)
                if self._is_valid_code_format(normalized):
                    confidence = 1.0 - (i * 0.1)  # Higher confidence for earlier patterns
                    
                    if normalized not in found_codes or found_codes[normalized]["confidence"] < confidence:
                        found_codes[normalized] = {
                            "code": code,
                            "confidence": confidence,
                            "strategy": f"pattern_{i}",
                            "original": code
                        }
        
        # Strategy 2: Context-aware extraction
        context_codes = self._extract_codes_with_context(text)
        for code_info in context_codes:
            normalized = self._normalize_code(code_info["code"])
            if normalized not in found_codes:
                found_codes[normalized] = code_info
        
        # Strategy 3: Fuzzy matching for damaged codes
        if len(found_codes) == 0:  # Only if no codes found yet
            fuzzy_codes = self._extract_fuzzy_codes(text)
            for code_info in fuzzy_codes:
                normalized = self._normalize_code(code_info["code"])
                if normalized not in found_codes:
                    found_codes[normalized] = code_info
        
        return list(found_codes.values())
    
    def _extract_codes_with_context(self, text: str) -> List[Dict[str, Any]]:
        """Extract codes by looking for contextual clues."""
        codes = []
        
        # Look for code-like patterns near shift/code keywords
        context_patterns = [
            r"(?:shift\s+code|code)[:\s]*([A-Z0-9-]{15,30})",
            r"([A-Z0-9-]{15,30})(?:\s+is\s+the\s+code)",
            r"redeem[:\s]*([A-Z0-9-]{15,30})",
            r"use[:\s]*([A-Z0-9-]{15,30})"
        ]
        
        for pattern in context_patterns:
            matches = re.finditer(pattern, text, re.I)
            for match in matches:
                potential_code = match.group(1).strip()
                normalized = self._normalize_code(potential_code)
                
                if self._is_valid_code_format(normalized):
                    codes.append({
                        "code": potential_code,
                        "confidence": 0.8,
                        "strategy": "context",
                        "original": potential_code
                    })
        
        return codes
    
    def _extract_fuzzy_codes(self, text: str) -> List[Dict[str, Any]]:
        """Extract codes with fuzzy matching for damaged/malformed codes."""
        codes = []
        
        # Look for sequences that might be damaged codes
        fuzzy_pattern = r"\b[A-Z0-9]{4,6}[-_\s]*[A-Z0-9]{4,6}[-_\s]*[A-Z0-9]{4,6}[-_\s]*[A-Z0-9]{4,6}(?:[-_\s]*[A-Z0-9]{4,6})?\b"
        
        matches = re.finditer(fuzzy_pattern, text, re.I)
        for match in matches:
            potential_code = match.group(0)
            
            # Try to repair the code
            repaired = self._repair_code(potential_code)
            if repaired and self._is_valid_code_format(repaired):
                codes.append({
                    "code": repaired,
                    "confidence": 0.6,  # Lower confidence for fuzzy matches
                    "strategy": "fuzzy",
                    "original": potential_code
                })
        
        return codes
    
    def _repair_code(self, damaged_code: str) -> Optional[str]:
        """Attempt to repair a damaged code."""
        # Remove all non-alphanumeric characters
        clean = re.sub(r'[^A-Z0-9]', '', damaged_code.upper())
        
        # Check if it's a valid length
        if len(clean) in [16, 20, 25]:
            return self._normalize_code(clean)
        
        return None
    
    @lru_cache(maxsize=1000)
    def extract_metadata(self, content: RawContent, code: str) -> CodeMetadata:
        """Extract metadata for a specific code from content with caching."""
        text = content.content.lower()
        
        # Extract reward type with enhanced scoring
        reward_type = self._infer_reward_type_enhanced(text, code)
        
        # Extract platforms with exclusion logic
        platforms = self._infer_platforms_enhanced(text)
        
        # Extract expiration date with multiple formats
        expires_at, is_estimated = self._extract_expiration_enhanced(text)
        
        # Calculate enhanced confidence score
        confidence_score = self._calculate_confidence_enhanced(text, code, content)
        
        return CodeMetadata(
            reward_type=reward_type,
            platforms=platforms,
            expires_at=expires_at,
            is_expiration_estimated=is_estimated,
            confidence_score=confidence_score,
            additional_info={
                "context_length": len(text),
                "code_position": text.find(code.lower()),
                "source_type": content.metadata.get("source_type"),
                "has_expiration_keywords": self._has_expiration_keywords(text),
                "reward_keyword_count": self._count_reward_keywords(text)
            }
        )
    
    def _infer_reward_type_enhanced(self, text: str, code: str) -> Optional[str]:
        """Enhanced reward type inference with context and scoring."""
        cache_key = f"{hash(text[:1000])}_{code}"  # Cache based on first 1000 chars + code
        if cache_key in self._reward_cache:
            return self._reward_cache[cache_key]
        
        scores: Dict[str, float] = {}
        
        # Get context around the code
        code_context = self._get_code_context(text, code, window=200)
        
        for reward_type, keywords in self.REWARD_KEYWORDS.items():
            score = 0.0
            
            # Primary keywords (high weight)
            for keyword in keywords["primary"]:
                if keyword in text:
                    score += 3.0
                if keyword in code_context:
                    score += 5.0  # Higher weight for context near code
            
            # Secondary keywords (medium weight)
            for keyword in keywords["secondary"]:
                if keyword in text:
                    score += 1.0
                if keyword in code_context:
                    score += 2.0
            
            # Context keywords (low weight)
            for keyword in keywords["context"]:
                if keyword in text:
                    score += 0.5
                if keyword in code_context:
                    score += 1.0
            
            if score > 0:
                scores[reward_type] = score
        
        # Return the highest scoring reward type
        result = max(scores.items(), key=lambda x: x[1])[0] if scores else None
        self._reward_cache[cache_key] = result
        return result
    
    def _infer_platforms_enhanced(self, text: str) -> List[str]:
        """Enhanced platform inference with exclusion logic."""
        cache_key = hash(text[:1000])
        if cache_key in self._platform_cache:
            return self._platform_cache[cache_key]
        
        platform_scores: Dict[str, float] = {}
        
        for platform, keywords in self.PLATFORM_KEYWORDS.items():
            score = 0.0
            
            # Check primary keywords
            for keyword in keywords["primary"]:
                if keyword in text:
                    score += 3.0
            
            # Check secondary keywords
            for keyword in keywords["secondary"]:
                if keyword in text:
                    score += 1.0
            
            # Apply exclusions (negative scoring)
            for exclusion in keywords["exclusions"]:
                if exclusion in text:
                    score -= 2.0
            
            if score > 0:
                platform_scores[platform] = score
        
        # Determine platforms based on scores
        platforms = []
        if platform_scores:
            # If multiple platforms have positive scores, include them
            for platform, score in platform_scores.items():
                if score > 1.0:  # Threshold for inclusion
                    platforms.append(platform)
        
        # Default to "all" if no specific platforms detected
        if not platforms:
            platforms = ["all"]
        
        self._platform_cache[cache_key] = platforms
        return platforms
    
    def _extract_expiration_enhanced(self, text: str) -> Tuple[Optional[datetime], bool]:
        """Enhanced expiration date extraction using dedicated parser."""
        from .expiration_parser import ExpirationParser
        
        if not hasattr(self, '_expiration_parser'):
            self._expiration_parser = ExpirationParser()
        
        return self._expiration_parser.parse_expiration(text)
    
    def _calculate_confidence_enhanced(self, text: str, code: str, content: RawContent) -> float:
        """Enhanced confidence calculation with multiple factors."""
        confidence = 1.0
        
        # Factor 1: Code frequency (lower confidence for repeated codes)
        code_count = text.lower().count(code.lower())
        if code_count > 1:
            confidence *= max(0.3, 1.0 - (code_count - 1) * 0.2)
        
        # Factor 2: Reward keywords presence
        reward_keywords_found = self._count_reward_keywords(text)
        if reward_keywords_found > 0:
            confidence = min(1.0, confidence + 0.1 * reward_keywords_found)
        
        # Factor 3: Source reliability
        source_type = content.metadata.get("source_type", "unknown")
        if source_type == "reddit":
            confidence *= 0.9  # Slightly lower for Reddit due to noise
        elif source_type == "rss":
            confidence *= 1.1  # Higher for RSS feeds
        
        # Factor 4: Context quality
        context = self._get_code_context(text, code, window=100)
        if any(keyword in context for keyword in ["shift", "code", "redeem", "key"]):
            confidence *= 1.2
        
        # Factor 5: Code format quality
        if self._is_perfect_format(code):
            confidence *= 1.1
        
        # Factor 6: Expiration information presence
        if self._has_expiration_keywords(text):
            confidence *= 1.05
        
        return min(1.0, confidence)
    
    def _get_code_context(self, text: str, code: str, window: int = 200) -> str:
        """Get text context around a code."""
        code_pos = text.lower().find(code.lower())
        if code_pos == -1:
            return ""
        
        start = max(0, code_pos - window)
        end = min(len(text), code_pos + len(code) + window)
        
        return text[start:end]
    
    def _count_reward_keywords(self, text: str) -> int:
        """Count reward-related keywords in text."""
        count = 0
        for keywords_dict in self.REWARD_KEYWORDS.values():
            for keyword_list in keywords_dict.values():
                for keyword in keyword_list:
                    if keyword in text:
                        count += 1
        return count
    
    def _has_expiration_keywords(self, text: str) -> bool:
        """Check if text contains expiration-related keywords."""
        expiration_keywords = [
            "expires", "expiry", "expire", "until", "ends", "valid",
            "deadline", "limited time", "temporary"
        ]
        return any(keyword in text.lower() for keyword in expiration_keywords)
    
    def _is_perfect_format(self, code: str) -> bool:
        """Check if code is in perfect format."""
        return bool(re.match(r'^[A-Z0-9]{5}-[A-Z0-9]{5}-[A-Z0-9]{5}-[A-Z0-9]{5}-[A-Z0-9]{5}$', code))
    
    def _extract_codes(self, text: str) -> List[str]:
        """Legacy method for backward compatibility."""
        codes_info = self._extract_codes_multi_strategy(text)
        return [info["code"] for info in codes_info]
    
    def _normalize_code(self, code: str) -> str:
        """Normalize code to canonical format."""
        # Remove all non-alphanumeric characters
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
    
    def _is_valid_code_format(self, code: str) -> bool:
        """Check if code matches valid format."""
        clean_code = re.sub(r'[^A-Z0-9]', '', code)
        return len(clean_code) in [16, 20, 25]
    
    def _extract_context(self, text: str, code: str) -> str:
        """Extract context around the code for better understanding."""
        return self._get_code_context(text, code, window=250)