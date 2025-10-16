"""
Advanced deduplication engine for shift codes.
"""

import logging
from typing import List, Optional, Dict, Any, Tuple, Set
from datetime import datetime, timezone
from enum import Enum

from models.code import ParsedCode, CodeMetadata, CodeStatus
from storage.repositories import CodeRepository
from processing.validator import CodeValidator

logger = logging.getLogger(__name__)


class DeduplicationAction(Enum):
    """Actions that can be taken during deduplication."""
    INSERT_NEW = "insert_new"
    SKIP_DUPLICATE = "skip_duplicate"
    UPDATE_METADATA = "update_metadata"
    MARK_EXPIRED = "mark_expired"
    MERGE_SOURCES = "merge_sources"


class DeduplicationResult:
    """Result of deduplication process."""
    
    def __init__(self, action: DeduplicationAction, code: ParsedCode, 
                 existing_code: Optional[ParsedCode] = None, reason: str = ""):
        self.action = action
        self.code = code
        self.existing_code = existing_code
        self.reason = reason
        self.metadata_changes: Dict[str, Any] = {}
        self.confidence_change: float = 0.0
    
    def __str__(self) -> str:
        return f"DeduplicationResult(action={self.action.value}, code={self.code.code_display}, reason={self.reason})"


class DeduplicationEngine:
    """Advanced deduplication engine with metadata comparison and conflict resolution."""
    
    def __init__(self, code_repository: CodeRepository, validator: CodeValidator):
        self.code_repository = code_repository
        self.validator = validator
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        
        # Configuration for deduplication behavior
        self.config = {
            "confidence_threshold": 0.3,  # Minimum confidence to consider a code
            "metadata_update_threshold": 0.1,  # Minimum confidence difference to update
            "expiration_buffer_hours": 1,  # Buffer for expiration checking
            "max_source_merge": 5,  # Maximum sources to merge for a single code
            "enable_fuzzy_matching": True,  # Enable fuzzy duplicate detection
            "similarity_threshold": 0.85,  # Threshold for fuzzy matching
        }
        
        # Statistics tracking
        self.stats = {
            "codes_processed": 0,
            "new_codes": 0,
            "duplicates_found": 0,
            "metadata_updates": 0,
            "expired_codes": 0,
            "low_confidence_rejected": 0
        }
    
    def process_codes(self, codes: List[ParsedCode]) -> List[DeduplicationResult]:
        """Process a batch of codes for deduplication."""
        results = []
        
        self.logger.info(f"Processing {len(codes)} codes for deduplication")
        
        for code in codes:
            try:
                result = self.process_single_code(code)
                results.append(result)
                self._update_stats(result)
                
            except Exception as e:
                self.logger.error(f"Error processing code {code.code_display}: {e}")
                # Create error result
                error_result = DeduplicationResult(
                    action=DeduplicationAction.SKIP_DUPLICATE,
                    code=code,
                    reason=f"Processing error: {str(e)}"
                )
                results.append(error_result)
        
        self.logger.info(f"Deduplication complete: {self._format_stats()}")
        return results
    
    def process_single_code(self, code: ParsedCode) -> DeduplicationResult:
        """Process a single code for deduplication."""
        self.stats["codes_processed"] += 1
        
        # Step 1: Validate code quality
        if code.confidence_score < self.config["confidence_threshold"]:
            return DeduplicationResult(
                action=DeduplicationAction.SKIP_DUPLICATE,
                code=code,
                reason=f"Low confidence score: {code.confidence_score:.2f}"
            )
        
        # Step 2: Check for exact duplicates
        existing_code = self.code_repository.get_code_by_canonical(code.code_canonical)
        
        if existing_code:
            return self._handle_existing_code(code, existing_code)
        
        # Step 3: Check for fuzzy duplicates if enabled
        if self.config["enable_fuzzy_matching"]:
            fuzzy_matches = self._find_fuzzy_duplicates(code)
            if fuzzy_matches:
                best_match = max(fuzzy_matches, key=lambda x: x[1])  # Highest similarity
                if best_match[1] >= self.config["similarity_threshold"]:
                    return self._handle_fuzzy_duplicate(code, best_match[0], best_match[1])
        
        # Step 4: Check if code is expired on discovery
        if self._is_expired_on_discovery(code):
            code.status = CodeStatus.EXPIRED
            return DeduplicationResult(
                action=DeduplicationAction.MARK_EXPIRED,
                code=code,
                reason="Code expired on discovery"
            )
        
        # Step 5: New code - insert it
        return DeduplicationResult(
            action=DeduplicationAction.INSERT_NEW,
            code=code,
            reason="New code discovered"
        )
    
    def _handle_existing_code(self, new_code: ParsedCode, existing_code: ParsedCode) -> DeduplicationResult:
        """Handle a code that already exists in the database."""
        
        # Check if we should update metadata
        should_update, changes = self._should_update_metadata(new_code, existing_code)
        
        if should_update:
            # Merge metadata from new code into existing
            updated_code = self._merge_code_metadata(existing_code, new_code, changes)
            
            return DeduplicationResult(
                action=DeduplicationAction.UPDATE_METADATA,
                code=updated_code,
                existing_code=existing_code,
                reason=f"Metadata updated: {', '.join(changes.keys())}",
                metadata_changes=changes,
                confidence_change=new_code.confidence_score - existing_code.confidence_score
            )
        
        # Check if we should merge source information
        if self._should_merge_sources(new_code, existing_code):
            merged_code = self._merge_source_info(existing_code, new_code)
            
            return DeduplicationResult(
                action=DeduplicationAction.MERGE_SOURCES,
                code=merged_code,
                existing_code=existing_code,
                reason="Source information merged"
            )
        
        # No updates needed - skip duplicate
        return DeduplicationResult(
            action=DeduplicationAction.SKIP_DUPLICATE,
            code=existing_code,
            existing_code=existing_code,
            reason="Exact duplicate with no new information"
        )
    
    def _should_update_metadata(self, new_code: ParsedCode, existing_code: ParsedCode) -> Tuple[bool, Dict[str, Any]]:
        """Determine if metadata should be updated and what changes to make."""
        changes = {}
        
        # Check confidence score improvement
        confidence_improvement = new_code.confidence_score - existing_code.confidence_score
        if confidence_improvement > self.config["metadata_update_threshold"]:
            changes["confidence_improvement"] = confidence_improvement
        
        # Check reward type updates
        if (new_code.reward_type and 
            new_code.reward_type != existing_code.reward_type and
            new_code.confidence_score > existing_code.confidence_score):
            changes["reward_type"] = {
                "old": existing_code.reward_type,
                "new": new_code.reward_type
            }
        
        # Check platform updates
        new_platforms = set(new_code.platforms)
        existing_platforms = set(existing_code.platforms)
        
        if new_platforms != existing_platforms:
            # If new code has more specific platforms (not just "all")
            if "all" in existing_platforms and "all" not in new_platforms:
                changes["platforms"] = {
                    "old": existing_code.platforms,
                    "new": new_code.platforms
                }
            # If new code has additional platforms
            elif new_platforms - existing_platforms:
                merged_platforms = list(existing_platforms | new_platforms)
                if "all" in merged_platforms and len(merged_platforms) > 1:
                    merged_platforms.remove("all")
                changes["platforms"] = {
                    "old": existing_code.platforms,
                    "new": merged_platforms
                }
        
        # Check expiration date updates
        if self._should_update_expiration(new_code, existing_code):
            changes["expiration"] = {
                "old": existing_code.expires_at,
                "new": new_code.expires_at,
                "old_estimated": existing_code.metadata.is_expiration_estimated,
                "new_estimated": new_code.metadata.is_expiration_estimated
            }
        
        # Check context quality improvement
        if (len(new_code.context) > len(existing_code.context) * 1.5 and
            new_code.confidence_score >= existing_code.confidence_score * 0.9):
            changes["context"] = {
                "old_length": len(existing_code.context),
                "new_length": len(new_code.context)
            }
        
        return len(changes) > 0, changes
    
    def _should_update_expiration(self, new_code: ParsedCode, existing_code: ParsedCode) -> bool:
        """Determine if expiration date should be updated."""
        # If existing has no expiration but new does
        if not existing_code.expires_at and new_code.expires_at:
            return True
        
        # If new expiration is more precise (not estimated)
        if (existing_code.metadata.is_expiration_estimated and 
            not new_code.metadata.is_expiration_estimated and
            new_code.expires_at):
            return True
        
        # If new expiration is significantly different and more confident
        if (existing_code.expires_at and new_code.expires_at and
            abs((new_code.expires_at - existing_code.expires_at).total_seconds()) > 3600 and  # 1 hour difference
            new_code.confidence_score > existing_code.confidence_score):
            return True
        
        return False
    
    def _merge_code_metadata(self, existing_code: ParsedCode, new_code: ParsedCode, 
                           changes: Dict[str, Any]) -> ParsedCode:
        """Merge metadata from new code into existing code."""
        # Create a copy of existing code
        merged_code = ParsedCode(
            id=existing_code.id,
            code_canonical=existing_code.code_canonical,
            code_display=existing_code.code_display,
            reward_type=existing_code.reward_type,
            platforms=existing_code.platforms.copy(),
            expires_at=existing_code.expires_at,
            source_id=existing_code.source_id,
            context=existing_code.context,
            confidence_score=existing_code.confidence_score,
            metadata=existing_code.metadata,
            status=existing_code.status,
            first_seen_at=existing_code.first_seen_at,
            last_updated_at=existing_code.last_updated_at
        )
        
        # Apply changes
        if "reward_type" in changes:
            merged_code.reward_type = changes["reward_type"]["new"]
        
        if "platforms" in changes:
            merged_code.platforms = changes["platforms"]["new"]
        
        if "expiration" in changes:
            merged_code.expires_at = changes["expiration"]["new"]
            merged_code.metadata.expires_at = changes["expiration"]["new"]
            merged_code.metadata.is_expiration_estimated = changes["expiration"]["new_estimated"]
        
        if "context" in changes:
            merged_code.context = new_code.context
        
        if "confidence_improvement" in changes:
            merged_code.confidence_score = new_code.confidence_score
        
        # Update timestamps
        merged_code.last_updated_at = datetime.now(timezone.utc)
        merged_code.status = CodeStatus.UPDATED
        
        return merged_code
    
    def _should_merge_sources(self, new_code: ParsedCode, existing_code: ParsedCode) -> bool:
        """Determine if source information should be merged."""
        # If codes are from different sources
        if new_code.source_id != existing_code.source_id:
            # Check if we haven't exceeded the merge limit
            source_count = len(existing_code.metadata.additional_info.get("merged_sources", []))
            return source_count < self.config["max_source_merge"]
        
        return False
    
    def _merge_source_info(self, existing_code: ParsedCode, new_code: ParsedCode) -> ParsedCode:
        """Merge source information from multiple discoveries."""
        merged_code = existing_code
        
        # Track merged sources
        merged_sources = existing_code.metadata.additional_info.get("merged_sources", [])
        
        # Add new source if not already present
        new_source_info = {
            "source_id": new_code.source_id,
            "discovered_at": datetime.now(timezone.utc).isoformat(),
            "confidence": new_code.confidence_score
        }
        
        if not any(s["source_id"] == new_code.source_id for s in merged_sources):
            merged_sources.append(new_source_info)
            merged_code.metadata.additional_info["merged_sources"] = merged_sources
            merged_code.last_updated_at = datetime.now(timezone.utc)
        
        return merged_code
    
    def _find_fuzzy_duplicates(self, code: ParsedCode) -> List[Tuple[ParsedCode, float]]:
        """Find potential fuzzy duplicates using similarity matching."""
        # This is a simplified implementation - in practice, you might want
        # to use more sophisticated algorithms like Levenshtein distance
        
        # Get recent codes for comparison (last 1000)
        recent_codes = self.code_repository.get_recent_codes(hours=24 * 7, limit=1000)
        
        fuzzy_matches = []
        
        for existing_code in recent_codes:
            similarity = self._calculate_code_similarity(code.code_canonical, existing_code.code_canonical)
            if similarity > 0.7:  # Potential match threshold
                fuzzy_matches.append((existing_code, similarity))
        
        return fuzzy_matches
    
    def _calculate_code_similarity(self, code1: str, code2: str) -> float:
        """Calculate similarity between two codes."""
        # Simple character-based similarity
        if code1 == code2:
            return 1.0
        
        # Remove separators for comparison
        clean1 = code1.replace('-', '')
        clean2 = code2.replace('-', '')
        
        if len(clean1) != len(clean2):
            return 0.0
        
        # Calculate character match percentage
        matches = sum(1 for c1, c2 in zip(clean1, clean2) if c1 == c2)
        return matches / len(clean1)
    
    def _handle_fuzzy_duplicate(self, new_code: ParsedCode, existing_code: ParsedCode, 
                              similarity: float) -> DeduplicationResult:
        """Handle a fuzzy duplicate match."""
        return DeduplicationResult(
            action=DeduplicationAction.SKIP_DUPLICATE,
            code=existing_code,
            existing_code=existing_code,
            reason=f"Fuzzy duplicate detected (similarity: {similarity:.2f})"
        )
    
    def _is_expired_on_discovery(self, code: ParsedCode) -> bool:
        """Check if code is expired when discovered."""
        if not code.expires_at:
            return False
        
        return self.validator.check_expiration(code.metadata)
    
    def _update_stats(self, result: DeduplicationResult) -> None:
        """Update deduplication statistics."""
        if result.action == DeduplicationAction.INSERT_NEW:
            self.stats["new_codes"] += 1
        elif result.action == DeduplicationAction.SKIP_DUPLICATE:
            if "low confidence" in result.reason.lower():
                self.stats["low_confidence_rejected"] += 1
            else:
                self.stats["duplicates_found"] += 1
        elif result.action == DeduplicationAction.UPDATE_METADATA:
            self.stats["metadata_updates"] += 1
        elif result.action == DeduplicationAction.MARK_EXPIRED:
            self.stats["expired_codes"] += 1
    
    def _format_stats(self) -> str:
        """Format statistics for logging."""
        return (f"processed={self.stats['codes_processed']}, "
                f"new={self.stats['new_codes']}, "
                f"duplicates={self.stats['duplicates_found']}, "
                f"updates={self.stats['metadata_updates']}, "
                f"expired={self.stats['expired_codes']}, "
                f"rejected={self.stats['low_confidence_rejected']}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get deduplication statistics."""
        stats = self.stats.copy()
        
        if stats["codes_processed"] > 0:
            stats["new_code_rate"] = stats["new_codes"] / stats["codes_processed"]
            stats["duplicate_rate"] = stats["duplicates_found"] / stats["codes_processed"]
            stats["update_rate"] = stats["metadata_updates"] / stats["codes_processed"]
        
        return stats
    
    def reset_stats(self) -> None:
        """Reset statistics counters."""
        for key in self.stats:
            self.stats[key] = 0
    
    def update_config(self, new_config: Dict[str, Any]) -> None:
        """Update deduplication configuration."""
        self.config.update(new_config)
        self.logger.info(f"Deduplication config updated: {new_config}")
    
    def is_duplicate(self, code: str) -> bool:
        """Simple duplicate check for external use."""
        canonical_code = self.validator.normalize_code(code)
        return self.code_repository.code_exists(canonical_code)
    
    def should_update_metadata(self, code: str, new_metadata: CodeMetadata) -> bool:
        """Check if metadata should be updated for external use."""
        canonical_code = self.validator.normalize_code(code)
        existing_code = self.code_repository.get_code_by_canonical(canonical_code)
        
        if not existing_code:
            return False
        
        # Create a temporary ParsedCode for comparison
        temp_code = ParsedCode(
            code_canonical=canonical_code,
            code_display=code,
            metadata=new_metadata,
            confidence_score=new_metadata.confidence_score
        )
        
        should_update, _ = self._should_update_metadata(temp_code, existing_code)
        return should_update
    
    def mark_as_processed(self, code: str, metadata: CodeMetadata) -> None:
        """Mark code as processed for external use."""
        # This is handled by the repository layer
        pass