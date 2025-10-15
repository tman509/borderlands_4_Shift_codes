"""
Content-related data models for the Shift Code Bot.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any


@dataclass
class RawContent:
    """Raw content fetched from a source."""
    url: str
    content: str
    content_type: str = "text/html"
    source_id: int = 0
    fetch_timestamp: Optional[str] = None
    content_hash: Optional[str] = None
    headers: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FormattedMessage:
    """A formatted message ready for delivery."""
    content: str
    embeds: List[Dict] = field(default_factory=list)
    components: List[Dict] = field(default_factory=list)
    template_vars: Dict[str, Any] = field(default_factory=dict)
    
    # Message metadata
    priority: int = 0  # Higher numbers = higher priority
    retry_count: int = 0
    max_retries: int = 3