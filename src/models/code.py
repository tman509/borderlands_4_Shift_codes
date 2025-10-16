"""
Code-related data models for the Shift Code Bot.
"""

import re
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Union, TYPE_CHECKING
from datetime import datetime, timezone
from enum import Enum

if TYPE_CHECKING:
    from .content import ParseContext


class CodeStatus(Enum):
    """Status of a shift code in the system."""
    NEW = "new"
    ANNOUNCED = "announced"
    EXPIRED = "expired"
    UPDATED = "updated"
    DUPLICATE = "duplicate"


@dataclass
class ValidationResult:
    """Result of code validation."""
    is_valid: bool
    canonical_code: str
    reason: Optional[str] = None
    confidence_score: float = 1.0
    
    def __post_init__(self):
        """Validate the validation result itself."""
        if not isinstance(self.is_valid, bool):
            raise ValueError("is_valid must be a boolean")
        if not isinstance(self.canonical_code, str):
            raise ValueError("canonical_code must be a string")
        if self.confidence_score < 0.0 or self.confidence_score > 1.0:
            raise ValueError("confidence_score must be between 0.0 and 1.0")


@dataclass
class CodeMetadata:
    """Metadata associated with a shift code."""
    reward_type: Optional[str] = None
    platforms: List[str] = field(default_factory=list)
    expires_at: Optional[datetime] = None
    is_expiration_estimated: bool = False
    additional_info: Dict[str, Any] = field(default_factory=dict)
    confidence_score: float = 1.0
    
    def __post_init__(self):
        """Validate metadata after initialization."""
        if self.confidence_score < 0.0 or self.confidence_score > 1.0:
            raise ValueError("confidence_score must be between 0.0 and 1.0")
        
        if self.platforms and not all(isinstance(p, str) for p in self.platforms):
            raise ValueError("All platforms must be strings")
        
        if self.expires_at and not isinstance(self.expires_at, datetime):
            raise ValueError("expires_at must be a datetime object")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert metadata to dictionary for JSON serialization."""
        return {
            "reward_type": self.reward_type,
            "platforms": self.platforms,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "is_expiration_estimated": self.is_expiration_estimated,
            "additional_info": self.additional_info,
            "confidence_score": self.confidence_score
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CodeMetadata':
        """Create metadata from dictionary."""
        expires_at = None
        if data.get("expires_at"):
            expires_at = datetime.fromisoformat(data["expires_at"])
        
        return cls(
            reward_type=data.get("reward_type"),
            platforms=data.get("platforms", []),
            expires_at=expires_at,
            is_expiration_estimated=data.get("is_expiration_estimated", False),
            additional_info=data.get("additional_info", {}),
            confidence_score=data.get("confidence_score", 1.0)
        )


@dataclass
class ParsedCode:
    """A parsed shift code with all associated data."""
    code_canonical: str
    code_display: str
    reward_type: Optional[str] = None
    platforms: List[str] = field(default_factory=list)
    expires_at: Optional[datetime] = None
    source_id: int = 0
    context: str = ""
    confidence_score: float = 1.0
    metadata: CodeMetadata = field(default_factory=CodeMetadata)
    status: CodeStatus = CodeStatus.NEW
    
    # Timestamps
    first_seen_at: Optional[datetime] = None
    last_updated_at: Optional[datetime] = None
    
    # Database fields
    id: Optional[int] = None
    
    def __post_init__(self):
        """Validate parsed code after initialization."""
        if not self.code_canonical:
            raise ValueError("code_canonical is required")
        
        if not self.code_display:
            raise ValueError("code_display is required")
        
        if self.confidence_score < 0.0 or self.confidence_score > 1.0:
            raise ValueError("confidence_score must be between 0.0 and 1.0")
        
        if self.source_id < 0:
            raise ValueError("source_id must be non-negative")
        
        # Ensure timestamps are timezone-aware
        if self.first_seen_at and self.first_seen_at.tzinfo is None:
            self.first_seen_at = self.first_seen_at.replace(tzinfo=timezone.utc)
        
        if self.last_updated_at and self.last_updated_at.tzinfo is None:
            self.last_updated_at = self.last_updated_at.replace(tzinfo=timezone.utc)
        
        if self.expires_at and self.expires_at.tzinfo is None:
            self.expires_at = self.expires_at.replace(tzinfo=timezone.utc)
    
    def is_expired(self) -> bool:
        """Check if the code has expired."""
        if not self.expires_at:
            return False
        
        now = datetime.now(timezone.utc)
        return self.expires_at < now
    
    def is_expiring_soon(self, hours: int = 24) -> bool:
        """Check if the code is expiring within the specified hours."""
        if not self.expires_at:
            return False
        
        now = datetime.now(timezone.utc)
        time_until_expiry = self.expires_at - now
        return 0 < time_until_expiry.total_seconds() < (hours * 3600)
    
    def normalize_code(self) -> str:
        """Normalize the code to canonical format."""
        return self._normalize_code_string(self.code_display)
    
    @staticmethod
    def _normalize_code_string(code: str) -> str:
        """Static method to normalize any code string."""
        if not code:
            return ""
        
        # Remove all non-alphanumeric characters and convert to uppercase
        clean_code = re.sub(r'[^A-Z0-9]', '', code.upper())
        
        # Format based on length
        if len(clean_code) == 25:  # 5x5 format (most common)
            return '-'.join([clean_code[i:i+5] for i in range(0, 25, 5)])
        elif len(clean_code) == 20:  # 4x5 format
            return '-'.join([clean_code[i:i+4] for i in range(0, 20, 4)])
        elif len(clean_code) == 16:  # 4x4 format
            return '-'.join([clean_code[i:i+4] for i in range(0, 16, 4)])
        elif len(clean_code) == 15:  # 3x5 format (rare)
            return '-'.join([clean_code[i:i+3] for i in range(0, 15, 3)])
        else:
            # Return as-is if doesn't match known patterns
            return clean_code
    
    def validate_format(self) -> bool:
        """Validate that the code matches expected format patterns."""
        return self._is_valid_code_format(self.code_canonical)
    
    @staticmethod
    def _is_valid_code_format(code: str) -> bool:
        """Static method to validate code format."""
        if not code:
            return False
        
        # Valid patterns for Shift Codes
        patterns = [
            r'^[A-Z0-9]{5}-[A-Z0-9]{5}-[A-Z0-9]{5}-[A-Z0-9]{5}-[A-Z0-9]{5}$',  # 5x5
            r'^[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$',  # 4x5
            r'^[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$',              # 4x4
            r'^[A-Z0-9]{3}-[A-Z0-9]{3}-[A-Z0-9]{3}-[A-Z0-9]{3}-[A-Z0-9]{3}$'   # 3x5
        ]
        
        return any(re.match(pattern, code) for pattern in patterns)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert parsed code to dictionary for serialization."""
        return {
            "id": self.id,
            "code_canonical": self.code_canonical,
            "code_display": self.code_display,
            "reward_type": self.reward_type,
            "platforms": self.platforms,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "source_id": self.source_id,
            "context": self.context,
            "confidence_score": self.confidence_score,
            "status": self.status.value,
            "first_seen_at": self.first_seen_at.isoformat() if self.first_seen_at else None,
            "last_updated_at": self.last_updated_at.isoformat() if self.last_updated_at else None,
            "metadata": self.metadata.to_dict()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ParsedCode':
        """Create parsed code from dictionary."""
        # Parse timestamps
        first_seen_at = None
        if data.get("first_seen_at"):
            first_seen_at = datetime.fromisoformat(data["first_seen_at"])
        
        last_updated_at = None
        if data.get("last_updated_at"):
            last_updated_at = datetime.fromisoformat(data["last_updated_at"])
        
        expires_at = None
        if data.get("expires_at"):
            expires_at = datetime.fromisoformat(data["expires_at"])
        
        # Parse metadata
        metadata = CodeMetadata()
        if data.get("metadata"):
            if isinstance(data["metadata"], dict):
                metadata = CodeMetadata.from_dict(data["metadata"])
            elif isinstance(data["metadata"], str):
                metadata = CodeMetadata.from_dict(json.loads(data["metadata"]))
        
        # Parse status
        status = CodeStatus.NEW
        if data.get("status"):
            status = CodeStatus(data["status"])
        
        return cls(
            id=data.get("id"),
            code_canonical=data["code_canonical"],
            code_display=data["code_display"],
            reward_type=data.get("reward_type"),
            platforms=data.get("platforms", []),
            expires_at=expires_at,
            source_id=data.get("source_id", 0),
            context=data.get("context", ""),
            confidence_score=data.get("confidence_score", 1.0),
            metadata=metadata,
            status=status,
            first_seen_at=first_seen_at,
            last_updated_at=last_updated_at
        )
    
    def update_metadata(self, new_metadata: CodeMetadata) -> bool:
        """Update metadata and return True if there were meaningful changes."""
        old_metadata = self.metadata.to_dict()
        new_metadata_dict = new_metadata.to_dict()
        
        # Check for meaningful changes
        meaningful_changes = False
        
        # Check reward type change
        if old_metadata.get("reward_type") != new_metadata_dict.get("reward_type"):
            meaningful_changes = True
        
        # Check platform changes
        old_platforms = set(old_metadata.get("platforms", []))
        new_platforms = set(new_metadata_dict.get("platforms", []))
        if old_platforms != new_platforms:
            meaningful_changes = True
        
        # Check expiration changes
        if old_metadata.get("expires_at") != new_metadata_dict.get("expires_at"):
            meaningful_changes = True
        
        # Update metadata
        self.metadata = new_metadata
        self.last_updated_at = datetime.now(timezone.utc)
        
        if meaningful_changes:
            self.status = CodeStatus.UPDATED
        
        return meaningful_changes