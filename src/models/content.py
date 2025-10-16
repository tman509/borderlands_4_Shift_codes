"""
Content-related data models for the Shift Code Bot.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
from enum import Enum


class ContentType(Enum):
    """Type of content fetched from sources."""
    HTML = "html"
    RSS = "rss"
    JSON = "json"
    TEXT = "text"


@dataclass
class RawContent:
    """Raw content fetched from a source."""
    content: str
    content_type: ContentType
    source_id: int
    url: str
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    headers: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    content_hash: Optional[str] = None
    
    def __post_init__(self):
        """Validate raw content after initialization."""
        if not self.content:
            raise ValueError("Content cannot be empty")
        
        if not self.url:
            raise ValueError("URL is required")
        
        if self.source_id <= 0:
            raise ValueError("Source ID must be positive")
        
        # Ensure timestamp is timezone-aware
        if self.fetched_at.tzinfo is None:
            self.fetched_at = self.fetched_at.replace(tzinfo=timezone.utc)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "content": self.content,
            "content_type": self.content_type.value,
            "source_id": self.source_id,
            "url": self.url,
            "fetched_at": self.fetched_at.isoformat(),
            "headers": self.headers,
            "metadata": self.metadata,
            "content_hash": self.content_hash
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RawContent':
        """Create from dictionary."""
        fetched_at = datetime.now(timezone.utc)
        if data.get("fetched_at"):
            fetched_at = datetime.fromisoformat(data["fetched_at"])
        
        return cls(
            content=data["content"],
            content_type=ContentType(data["content_type"]),
            source_id=data["source_id"],
            url=data["url"],
            fetched_at=fetched_at,
            headers=data.get("headers", {}),
            metadata=data.get("metadata", {}),
            content_hash=data.get("content_hash")
        )


@dataclass
class ParseContext:
    """Context information for parsing operations."""
    source_config: Dict[str, Any]
    content_snippet: str = ""
    confidence_factors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    def add_confidence_factor(self, factor: str) -> None:
        """Add a confidence factor."""
        if factor not in self.confidence_factors:
            self.confidence_factors.append(factor)
    
    def add_warning(self, warning: str) -> None:
        """Add a parsing warning."""
        if warning not in self.warnings:
            self.warnings.append(warning)
    
    def calculate_confidence_score(self) -> float:
        """Calculate confidence score based on factors."""
        if not self.confidence_factors:
            return 0.5  # Default medium confidence
        
        # Simple scoring based on number of positive factors
        base_score = min(len(self.confidence_factors) * 0.2, 1.0)
        
        # Reduce score for warnings
        warning_penalty = len(self.warnings) * 0.1
        
        return max(0.1, base_score - warning_penalty)


@dataclass
class ParseResult:
    """Result of parsing operation."""
    codes_found: List['ParsedCode'] = field(default_factory=list)
    parse_context: ParseContext = field(default_factory=ParseContext)
    success: bool = True
    error_message: Optional[str] = None
    processing_time_ms: float = 0.0
    
    def add_code(self, code: 'ParsedCode') -> None:
        """Add a parsed code to the result."""
        self.codes_found.append(code)
    
    def has_codes(self) -> bool:
        """Check if any codes were found."""
        return len(self.codes_found) > 0
    
    def get_code_count(self) -> int:
        """Get number of codes found."""
        return len(self.codes_found)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "codes_found": [code.to_dict() for code in self.codes_found],
            "success": self.success,
            "error_message": self.error_message,
            "processing_time_ms": self.processing_time_ms,
            "code_count": self.get_code_count(),
            "confidence_factors": self.parse_context.confidence_factors,
            "warnings": self.parse_context.warnings
        }