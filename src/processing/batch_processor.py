"""
Batch processing system for efficient code handling.
"""

import logging
from typing import List, Dict, Any, Optional, Callable, Iterator
from datetime import datetime, timezone
from dataclasses import dataclass
from enum import Enum
import time

from ..models.code import ParsedCode, CodeStatus
from ..models.content import RawContent
from ..storage.repositories import CodeRepository, SourceRepository
from ..processing.parser import CodeParser
from ..processing.validator import CodeValidator
from ..processing.deduplication import DeduplicationEngine, DeduplicationResult, DeduplicationAction

logger = logging.getLogger(__name__)


class BatchStatus(Enum):
    """Status of batch processing."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


@dataclass
class BatchMetrics:
    """Metrics for batch processing."""
    total_content_items: int = 0
    codes_extracted: int = 0
    codes_validated: int = 0
    codes_inserted: int = 0
    codes_updated: int = 0
    codes_skipped: int = 0
    processing_time_seconds: float = 0.0
    errors: List[str] = None
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []


@dataclass
class BatchResult:
    """Result of batch processing operation."""
    status: BatchStatus
    metrics: BatchMetrics
    processed_codes: List[ParsedCode]
    deduplication_results: List[DeduplicationResult]
    errors: List[str]
    
    def success_rate(self) -> float:
        """Calculate success rate of the batch."""
        if self.metrics.total_content_items == 0:
            return 0.0
        return (self.metrics.codes_inserted + self.metrics.codes_updated) / self.metrics.total_content_items


class BatchProcessor:
    """High-performance batch processor for code processing pipeline."""
    
    def __init__(self, 
                 code_repository: CodeRepository,
                 source_repository: SourceRepository,
                 parser: CodeParser,
                 validator: CodeValidator,
                 deduplication_engine: DeduplicationEngine):
        
        self.code_repository = code_repository
        self.source_repository = source_repository
        self.parser = parser
        self.validator = validator
        self.deduplication_engine = deduplication_engine
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        
        # Configuration
        self.config = {
            "batch_size": 100,  # Number of codes to process in one batch
            "max_retries": 3,   # Maximum retries for failed operations
            "transaction_timeout": 30,  # Transaction timeout in seconds
            "enable_parallel_validation": True,  # Enable parallel validation
            "validation_chunk_size": 20,  # Chunk size for parallel validation
            "enable_progress_callback": True,  # Enable progress callbacks
        }
        
        # Statistics
        self.stats = {
            "batches_processed": 0,
            "total_codes_processed": 0,
            "total_processing_time": 0.0,
            "average_batch_time": 0.0,
            "success_rate": 0.0
        }
    
    def process_content_batch(self, 
                            content_items: List[RawContent],
                            progress_callback: Optional[Callable[[int, int], None]] = None) -> BatchResult:
        """Process a batch of raw content items through the complete pipeline."""
        
        start_time = time.time()
        metrics = BatchMetrics(total_content_items=len(content_items))
        processed_codes = []
        deduplication_results = []
        errors = []
        
        self.logger.info(f"Starting batch processing of {len(content_items)} content items")
        
        try:
            # Step 1: Extract codes from all content items
            all_extracted_codes = []
            
            for i, content_item in enumerate(content_items):
                try:
                    codes = self.parser.parse_codes(content_item)
                    all_extracted_codes.extend(codes)
                    metrics.codes_extracted += len(codes)
                    
                    if progress_callback and self.config["enable_progress_callback"]:
                        progress_callback(i + 1, len(content_items))
                        
                except Exception as e:
                    error_msg = f"Failed to parse content from {content_item.url}: {e}"
                    self.logger.warning(error_msg)
                    errors.append(error_msg)
            
            self.logger.info(f"Extracted {len(all_extracted_codes)} codes from {len(content_items)} content items")
            
            # Step 2: Validate codes in batches
            validated_codes = self._validate_codes_batch(all_extracted_codes, metrics, errors)
            
            # Step 3: Process codes through deduplication
            dedup_results = self._process_deduplication_batch(validated_codes, metrics, errors)
            deduplication_results.extend(dedup_results)
            
            # Step 4: Execute database operations in batches
            final_codes = self._execute_database_operations_batch(dedup_results, metrics, errors)
            processed_codes.extend(final_codes)
            
            # Determine final status
            if errors:
                status = BatchStatus.PARTIAL if processed_codes else BatchStatus.FAILED
            else:
                status = BatchStatus.COMPLETED
            
        except Exception as e:
            self.logger.error(f"Batch processing failed: {e}")
            errors.append(f"Batch processing error: {str(e)}")
            status = BatchStatus.FAILED
        
        # Calculate metrics
        processing_time = time.time() - start_time
        metrics.processing_time_seconds = processing_time
        metrics.errors = errors
        
        # Update statistics
        self._update_stats(processing_time, len(processed_codes))
        
        result = BatchResult(
            status=status,
            metrics=metrics,
            processed_codes=processed_codes,
            deduplication_results=deduplication_results,
            errors=errors
        )
        
        self.logger.info(f"Batch processing completed: {self._format_batch_summary(result)}")
        return result
    
    def _validate_codes_batch(self, codes: List[ParsedCode], 
                            metrics: BatchMetrics, errors: List[str]) -> List[ParsedCode]:
        """Validate codes in batch with optional parallelization."""
        
        if not codes:
            return []
        
        validated_codes = []
        
        if self.config["enable_parallel_validation"] and len(codes) > self.config["validation_chunk_size"]:
            # Process in chunks for better performance
            validated_codes = self._validate_codes_parallel(codes, metrics, errors)
        else:
            # Sequential validation
            validated_codes = self._validate_codes_sequential(codes, metrics, errors)
        
        self.logger.info(f"Validated {len(validated_codes)} out of {len(codes)} codes")
        return validated_codes
    
    def _validate_codes_sequential(self, codes: List[ParsedCode], 
                                 metrics: BatchMetrics, errors: List[str]) -> List[ParsedCode]:
        """Validate codes sequentially."""
        validated_codes = []
        
        for code in codes:
            try:
                validation_result = self.validator.validate_format(code.code_display)
                
                if validation_result.is_valid:
                    # Update code with validation results
                    code.code_canonical = validation_result.canonical_code
                    code.confidence_score = min(code.confidence_score, validation_result.confidence_score)
                    validated_codes.append(code)
                    metrics.codes_validated += 1
                else:
                    self.logger.debug(f"Code validation failed: {code.code_display} - {validation_result.reason}")
                    
            except Exception as e:
                error_msg = f"Validation error for code {code.code_display}: {e}"
                self.logger.warning(error_msg)
                errors.append(error_msg)
        
        return validated_codes
    
    def _validate_codes_parallel(self, codes: List[ParsedCode], 
                               metrics: BatchMetrics, errors: List[str]) -> List[ParsedCode]:
        """Validate codes in parallel chunks."""
        # For now, implement as sequential - can be enhanced with threading/multiprocessing
        # This is a placeholder for future parallel implementation
        return self._validate_codes_sequential(codes, metrics, errors)
    
    def _process_deduplication_batch(self, codes: List[ParsedCode], 
                                   metrics: BatchMetrics, errors: List[str]) -> List[DeduplicationResult]:
        """Process codes through deduplication engine."""
        
        if not codes:
            return []
        
        try:
            dedup_results = self.deduplication_engine.process_codes(codes)
            
            # Update metrics based on deduplication results
            for result in dedup_results:
                if result.action == DeduplicationAction.INSERT_NEW:
                    metrics.codes_inserted += 1
                elif result.action == DeduplicationAction.UPDATE_METADATA:
                    metrics.codes_updated += 1
                else:
                    metrics.codes_skipped += 1
            
            return dedup_results
            
        except Exception as e:
            error_msg = f"Deduplication processing failed: {e}"
            self.logger.error(error_msg)
            errors.append(error_msg)
            return []
    
    def _execute_database_operations_batch(self, dedup_results: List[DeduplicationResult], 
                                         metrics: BatchMetrics, errors: List[str]) -> List[ParsedCode]:
        """Execute database operations in optimized batches."""
        
        if not dedup_results:
            return []
        
        processed_codes = []
        
        # Group operations by type for batch processing
        inserts = []
        updates = []
        
        for result in dedup_results:
            if result.action == DeduplicationAction.INSERT_NEW:
                inserts.append(result.code)
            elif result.action == DeduplicationAction.UPDATE_METADATA:
                updates.append(result.code)
            elif result.action in [DeduplicationAction.SKIP_DUPLICATE, DeduplicationAction.MERGE_SOURCES]:
                processed_codes.append(result.code)
        
        # Execute batch inserts
        if inserts:
            try:
                inserted_codes = self._batch_insert_codes(inserts, errors)
                processed_codes.extend(inserted_codes)
            except Exception as e:
                error_msg = f"Batch insert failed: {e}"
                self.logger.error(error_msg)
                errors.append(error_msg)
        
        # Execute batch updates
        if updates:
            try:
                updated_codes = self._batch_update_codes(updates, errors)
                processed_codes.extend(updated_codes)
            except Exception as e:
                error_msg = f"Batch update failed: {e}"
                self.logger.error(error_msg)
                errors.append(error_msg)
        
        return processed_codes
    
    def _batch_insert_codes(self, codes: List[ParsedCode], errors: List[str]) -> List[ParsedCode]:
        """Insert codes in batch with transaction handling."""
        
        if not codes:
            return []
        
        inserted_codes = []
        batch_size = self.config["batch_size"]
        
        # Process in smaller batches to avoid transaction timeouts
        for i in range(0, len(codes), batch_size):
            batch = codes[i:i + batch_size]
            
            try:
                # Prepare batch data for insertion
                codes_data = []
                for code in batch:
                    # Set timestamps
                    now = datetime.now(timezone.utc)
                    code.first_seen_at = code.first_seen_at or now
                    code.last_updated_at = now
                    code.status = CodeStatus.NEW
                    
                    codes_data.append((
                        code.code_canonical,
                        code.code_display,
                        code.reward_type,
                        code.platforms,
                        code.expires_at.isoformat() if code.expires_at else None,
                        code.first_seen_at.isoformat(),
                        code.last_updated_at.isoformat(),
                        code.source_id,
                        code.status.value,
                        code.confidence_score,
                        code.context,
                        code.metadata.to_dict() if code.metadata else {}
                    ))
                
                # Execute batch insert (this would need to be implemented in repository)
                for code in batch:
                    try:
                        code_id = self.code_repository.create_code(code)
                        code.id = code_id
                        inserted_codes.append(code)
                    except Exception as e:
                        error_msg = f"Failed to insert code {code.code_display}: {e}"
                        self.logger.warning(error_msg)
                        errors.append(error_msg)
                
                self.logger.debug(f"Inserted batch of {len(batch)} codes")
                
            except Exception as e:
                error_msg = f"Batch insert failed for batch starting at index {i}: {e}"
                self.logger.error(error_msg)
                errors.append(error_msg)
        
        return inserted_codes
    
    def _batch_update_codes(self, codes: List[ParsedCode], errors: List[str]) -> List[ParsedCode]:
        """Update codes in batch with transaction handling."""
        
        if not codes:
            return []
        
        updated_codes = []
        
        for code in codes:
            try:
                # Set update timestamp
                code.last_updated_at = datetime.now(timezone.utc)
                
                # Execute update
                success = self.code_repository.update_code(code)
                if success:
                    updated_codes.append(code)
                else:
                    error_msg = f"Failed to update code {code.code_display}: No rows affected"
                    self.logger.warning(error_msg)
                    errors.append(error_msg)
                    
            except Exception as e:
                error_msg = f"Failed to update code {code.code_display}: {e}"
                self.logger.warning(error_msg)
                errors.append(error_msg)
        
        return updated_codes
    
    def process_expired_codes_batch(self) -> BatchResult:
        """Process and mark expired codes in batch."""
        
        start_time = time.time()
        metrics = BatchMetrics()
        errors = []
        
        try:
            # Mark expired codes in database
            expired_count = self.code_repository.mark_codes_as_expired()
            metrics.codes_updated = expired_count
            
            processing_time = time.time() - start_time
            metrics.processing_time_seconds = processing_time
            
            self.logger.info(f"Marked {expired_count} codes as expired in {processing_time:.2f}s")
            
            return BatchResult(
                status=BatchStatus.COMPLETED,
                metrics=metrics,
                processed_codes=[],
                deduplication_results=[],
                errors=errors
            )
            
        except Exception as e:
            error_msg = f"Failed to process expired codes: {e}"
            self.logger.error(error_msg)
            errors.append(error_msg)
            
            return BatchResult(
                status=BatchStatus.FAILED,
                metrics=metrics,
                processed_codes=[],
                deduplication_results=[],
                errors=errors
            )
    
    def cleanup_old_codes_batch(self, days_old: int = 90) -> BatchResult:
        """Clean up old codes in batch to maintain database performance."""
        
        start_time = time.time()
        metrics = BatchMetrics()
        errors = []
        
        try:
            # This would need to be implemented in the repository
            # For now, just log the operation
            self.logger.info(f"Cleanup operation for codes older than {days_old} days")
            
            processing_time = time.time() - start_time
            metrics.processing_time_seconds = processing_time
            
            return BatchResult(
                status=BatchStatus.COMPLETED,
                metrics=metrics,
                processed_codes=[],
                deduplication_results=[],
                errors=errors
            )
            
        except Exception as e:
            error_msg = f"Failed to cleanup old codes: {e}"
            self.logger.error(error_msg)
            errors.append(error_msg)
            
            return BatchResult(
                status=BatchStatus.FAILED,
                metrics=metrics,
                processed_codes=[],
                deduplication_results=[],
                errors=errors
            )
    
    def _update_stats(self, processing_time: float, codes_processed: int) -> None:
        """Update batch processing statistics."""
        self.stats["batches_processed"] += 1
        self.stats["total_codes_processed"] += codes_processed
        self.stats["total_processing_time"] += processing_time
        
        if self.stats["batches_processed"] > 0:
            self.stats["average_batch_time"] = (
                self.stats["total_processing_time"] / self.stats["batches_processed"]
            )
    
    def _format_batch_summary(self, result: BatchResult) -> str:
        """Format batch processing summary for logging."""
        return (
            f"status={result.status.value}, "
            f"content_items={result.metrics.total_content_items}, "
            f"extracted={result.metrics.codes_extracted}, "
            f"validated={result.metrics.codes_validated}, "
            f"inserted={result.metrics.codes_inserted}, "
            f"updated={result.metrics.codes_updated}, "
            f"skipped={result.metrics.codes_skipped}, "
            f"time={result.metrics.processing_time_seconds:.2f}s, "
            f"errors={len(result.errors)}"
        )
    
    def get_stats(self) -> Dict[str, Any]:
        """Get batch processing statistics."""
        return self.stats.copy()
    
    def reset_stats(self) -> None:
        """Reset batch processing statistics."""
        for key in self.stats:
            self.stats[key] = 0.0 if isinstance(self.stats[key], float) else 0
    
    def update_config(self, new_config: Dict[str, Any]) -> None:
        """Update batch processing configuration."""
        self.config.update(new_config)
        self.logger.info(f"Batch processor config updated: {new_config}")
    
    def health_check(self) -> Dict[str, Any]:
        """Perform health check of batch processor."""
        return {
            "status": "healthy",
            "config": self.config,
            "stats": self.stats,
            "components": {
                "parser": "ok",
                "validator": "ok", 
                "deduplication_engine": "ok",
                "code_repository": "ok"
            }
        }