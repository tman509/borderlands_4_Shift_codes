"""
Message queue system with priority handling and persistence.
"""

import logging
import json
import time
from typing import List, Optional, Dict, Any, Callable
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, asdict
from enum import Enum, IntEnum
from queue import PriorityQueue, Empty
import threading
from pathlib import Path

logger = logging.getLogger(__name__)


class MessagePriority(IntEnum):
    """Message priority levels (lower numbers = higher priority)."""
    CRITICAL = 1    # System alerts, errors
    HIGH = 2        # New codes, important updates
    NORMAL = 3      # Regular notifications
    LOW = 4         # Reminders, maintenance messages


class MessageStatus(Enum):
    """Status of queued messages."""
    PENDING = "pending"
    PROCESSING = "processing"
    SENT = "sent"
    FAILED = "failed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


@dataclass
class QueuedMessage:
    """A message in the notification queue."""
    id: str
    channel_id: str
    content: str
    priority: MessagePriority
    created_at: datetime
    scheduled_for: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    retry_count: int = 0
    max_retries: int = 3
    status: MessageStatus = MessageStatus.PENDING
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
        
        # Ensure datetime objects are timezone-aware
        if self.created_at.tzinfo is None:
            self.created_at = self.created_at.replace(tzinfo=timezone.utc)
        
        if self.scheduled_for and self.scheduled_for.tzinfo is None:
            self.scheduled_for = self.scheduled_for.replace(tzinfo=timezone.utc)
        
        if self.expires_at and self.expires_at.tzinfo is None:
            self.expires_at = self.expires_at.replace(tzinfo=timezone.utc)
    
    def __lt__(self, other):
        """Comparison for priority queue (lower priority number = higher priority)."""
        if not isinstance(other, QueuedMessage):
            return NotImplemented
        
        # First compare by priority
        if self.priority != other.priority:
            return self.priority < other.priority
        
        # Then by scheduled time (earlier = higher priority)
        self_time = self.scheduled_for or self.created_at
        other_time = other.scheduled_for or other.created_at
        return self_time < other_time
    
    def is_ready_to_send(self) -> bool:
        """Check if message is ready to be sent."""
        if self.status != MessageStatus.PENDING:
            return False
        
        now = datetime.now(timezone.utc)
        
        # Check if expired
        if self.expires_at and now > self.expires_at:
            return False
        
        # Check if scheduled time has arrived
        if self.scheduled_for and now < self.scheduled_for:
            return False
        
        return True
    
    def is_expired(self) -> bool:
        """Check if message has expired."""
        if not self.expires_at:
            return False
        
        return datetime.now(timezone.utc) > self.expires_at
    
    def can_retry(self) -> bool:
        """Check if message can be retried."""
        return self.retry_count < self.max_retries and not self.is_expired()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        data = asdict(self)
        
        # Convert datetime objects to ISO strings
        for field in ['created_at', 'scheduled_for', 'expires_at']:
            if data[field]:
                data[field] = data[field].isoformat()
        
        # Convert enums to values
        data['priority'] = self.priority.value
        data['status'] = self.status.value
        
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'QueuedMessage':
        """Create from dictionary."""
        # Convert ISO strings back to datetime objects
        for field in ['created_at', 'scheduled_for', 'expires_at']:
            if data.get(field):
                data[field] = datetime.fromisoformat(data[field])
        
        # Convert enum values back to enums
        if 'priority' in data:
            data['priority'] = MessagePriority(data['priority'])
        
        if 'status' in data:
            data['status'] = MessageStatus(data['status'])
        
        return cls(**data)


class MessageQueue:
    """Thread-safe message queue with priority handling and persistence."""
    
    def __init__(self, persistence_file: Optional[str] = None, max_size: int = 10000):
        self.max_size = max_size
        self.persistence_file = persistence_file
        
        # Thread-safe priority queue
        self._queue = PriorityQueue(maxsize=max_size)
        self._lock = threading.RLock()
        
        # Message tracking
        self._messages: Dict[str, QueuedMessage] = {}
        self._processing: Dict[str, QueuedMessage] = {}
        
        # Statistics
        self.stats = {
            "messages_queued": 0,
            "messages_sent": 0,
            "messages_failed": 0,
            "messages_expired": 0,
            "messages_cancelled": 0,
            "queue_size": 0,
            "processing_count": 0
        }
        
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        
        # Load persisted messages if file exists
        if self.persistence_file:
            self._load_persisted_messages()
    
    def enqueue(self, message: QueuedMessage) -> bool:
        """Add a message to the queue."""
        with self._lock:
            try:
                # Check if queue is full
                if self._queue.full():
                    self.logger.warning("Message queue is full, dropping oldest low-priority message")
                    self._drop_lowest_priority_message()
                
                # Add to queue and tracking
                self._queue.put(message, block=False)
                self._messages[message.id] = message
                
                # Update statistics
                self.stats["messages_queued"] += 1
                self.stats["queue_size"] = self._queue.qsize()
                
                self.logger.debug(f"Enqueued message {message.id} with priority {message.priority.name}")
                
                # Persist if enabled
                if self.persistence_file:
                    self._persist_messages()
                
                return True
                
            except Exception as e:
                self.logger.error(f"Failed to enqueue message {message.id}: {e}")
                return False
    
    def dequeue(self, timeout: Optional[float] = None) -> Optional[QueuedMessage]:
        """Get the next message from the queue."""
        try:
            # Get message from priority queue
            message = self._queue.get(timeout=timeout)
            
            with self._lock:
                # Move to processing
                self._processing[message.id] = message
                message.status = MessageStatus.PROCESSING
                
                # Update statistics
                self.stats["queue_size"] = self._queue.qsize()
                self.stats["processing_count"] = len(self._processing)
                
                self.logger.debug(f"Dequeued message {message.id}")
                
                return message
                
        except Empty:
            return None
        except Exception as e:
            self.logger.error(f"Failed to dequeue message: {e}")
            return None
    
    def mark_sent(self, message_id: str) -> bool:
        """Mark a message as successfully sent."""
        with self._lock:
            if message_id in self._processing:
                message = self._processing.pop(message_id)
                message.status = MessageStatus.SENT
                
                # Update statistics
                self.stats["messages_sent"] += 1
                self.stats["processing_count"] = len(self._processing)
                
                self.logger.debug(f"Marked message {message_id} as sent")
                
                # Persist if enabled
                if self.persistence_file:
                    self._persist_messages()
                
                return True
            
            return False
    
    def mark_failed(self, message_id: str, error: str = "") -> bool:
        """Mark a message as failed and potentially retry."""
        with self._lock:
            if message_id in self._processing:
                message = self._processing.pop(message_id)
                message.retry_count += 1
                
                if message.can_retry():
                    # Re-queue for retry
                    message.status = MessageStatus.PENDING
                    message.scheduled_for = datetime.now(timezone.utc) + timedelta(
                        seconds=min(60 * (2 ** message.retry_count), 3600)  # Exponential backoff, max 1 hour
                    )
                    
                    self._queue.put(message)
                    self._messages[message.id] = message
                    
                    self.logger.info(f"Re-queued message {message_id} for retry {message.retry_count}")
                else:
                    # Mark as permanently failed
                    message.status = MessageStatus.FAILED
                    message.metadata["error"] = error
                    
                    self.stats["messages_failed"] += 1
                    self.logger.warning(f"Message {message_id} permanently failed after {message.retry_count} retries")
                
                # Update statistics
                self.stats["processing_count"] = len(self._processing)
                
                # Persist if enabled
                if self.persistence_file:
                    self._persist_messages()
                
                return True
            
            return False
    
    def cancel_message(self, message_id: str) -> bool:
        """Cancel a pending message."""
        with self._lock:
            if message_id in self._messages:
                message = self._messages[message_id]
                
                if message.status == MessageStatus.PENDING:
                    message.status = MessageStatus.CANCELLED
                    
                    # Update statistics
                    self.stats["messages_cancelled"] += 1
                    
                    self.logger.debug(f"Cancelled message {message_id}")
                    
                    # Persist if enabled
                    if self.persistence_file:
                        self._persist_messages()
                    
                    return True
            
            return False
    
    def get_pending_messages(self) -> List[QueuedMessage]:
        """Get all pending messages (for inspection)."""
        with self._lock:
            return [msg for msg in self._messages.values() if msg.status == MessageStatus.PENDING]
    
    def get_ready_messages(self) -> List[QueuedMessage]:
        """Get messages that are ready to be sent."""
        with self._lock:
            ready_messages = []
            for message in self._messages.values():
                if message.status == MessageStatus.PENDING and message.is_ready_to_send():
                    ready_messages.append(message)
            
            return sorted(ready_messages)  # Sort by priority
    
    def cleanup_expired_messages(self) -> int:
        """Remove expired messages from the queue."""
        with self._lock:
            expired_count = 0
            expired_ids = []
            
            for message_id, message in self._messages.items():
                if message.is_expired() and message.status == MessageStatus.PENDING:
                    message.status = MessageStatus.EXPIRED
                    expired_ids.append(message_id)
                    expired_count += 1
            
            # Update statistics
            self.stats["messages_expired"] += expired_count
            
            if expired_count > 0:
                self.logger.info(f"Cleaned up {expired_count} expired messages")
                
                # Persist if enabled
                if self.persistence_file:
                    self._persist_messages()
            
            return expired_count
    
    def _drop_lowest_priority_message(self) -> None:
        """Drop the lowest priority pending message to make room."""
        lowest_priority_msg = None
        lowest_priority = MessagePriority.CRITICAL
        
        for message in self._messages.values():
            if (message.status == MessageStatus.PENDING and 
                message.priority >= lowest_priority):
                lowest_priority = message.priority
                lowest_priority_msg = message
        
        if lowest_priority_msg:
            lowest_priority_msg.status = MessageStatus.CANCELLED
            self.stats["messages_cancelled"] += 1
            self.logger.warning(f"Dropped message {lowest_priority_msg.id} due to queue overflow")
    
    def _persist_messages(self) -> None:
        """Persist messages to file."""
        if not self.persistence_file:
            return
        
        try:
            # Only persist non-sent messages
            messages_to_persist = []
            for message in self._messages.values():
                if message.status in [MessageStatus.PENDING, MessageStatus.PROCESSING, MessageStatus.FAILED]:
                    messages_to_persist.append(message.to_dict())
            
            # Write to file
            persistence_path = Path(self.persistence_file)
            persistence_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(persistence_path, 'w') as f:
                json.dump(messages_to_persist, f, indent=2)
            
            self.logger.debug(f"Persisted {len(messages_to_persist)} messages to {self.persistence_file}")
            
        except Exception as e:
            self.logger.error(f"Failed to persist messages: {e}")
    
    def _load_persisted_messages(self) -> None:
        """Load persisted messages from file."""
        if not self.persistence_file or not Path(self.persistence_file).exists():
            return
        
        try:
            with open(self.persistence_file, 'r') as f:
                messages_data = json.load(f)
            
            loaded_count = 0
            for message_data in messages_data:
                try:
                    message = QueuedMessage.from_dict(message_data)
                    
                    # Only load pending and failed messages
                    if message.status in [MessageStatus.PENDING, MessageStatus.FAILED]:
                        self._messages[message.id] = message
                        
                        if message.status == MessageStatus.PENDING:
                            self._queue.put(message)
                        
                        loaded_count += 1
                
                except Exception as e:
                    self.logger.warning(f"Failed to load persisted message: {e}")
            
            self.logger.info(f"Loaded {loaded_count} persisted messages from {self.persistence_file}")
            
        except Exception as e:
            self.logger.error(f"Failed to load persisted messages: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get queue statistics."""
        with self._lock:
            stats = self.stats.copy()
            stats["queue_size"] = self._queue.qsize()
            stats["processing_count"] = len(self._processing)
            stats["total_messages"] = len(self._messages)
            
            # Calculate rates if we have data
            if stats["messages_queued"] > 0:
                stats["success_rate"] = stats["messages_sent"] / stats["messages_queued"]
                stats["failure_rate"] = stats["messages_failed"] / stats["messages_queued"]
            
            return stats
    
    def clear_completed_messages(self, older_than_hours: int = 24) -> int:
        """Clear completed messages older than specified hours."""
        with self._lock:
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=older_than_hours)
            cleared_count = 0
            
            messages_to_remove = []
            for message_id, message in self._messages.items():
                if (message.status in [MessageStatus.SENT, MessageStatus.EXPIRED, MessageStatus.CANCELLED] and
                    message.created_at < cutoff_time):
                    messages_to_remove.append(message_id)
            
            for message_id in messages_to_remove:
                del self._messages[message_id]
                cleared_count += 1
            
            if cleared_count > 0:
                self.logger.info(f"Cleared {cleared_count} completed messages")
                
                # Persist if enabled
                if self.persistence_file:
                    self._persist_messages()
            
            return cleared_count
    
    def size(self) -> int:
        """Get current queue size."""
        return self._queue.qsize()
    
    def is_empty(self) -> bool:
        """Check if queue is empty."""
        return self._queue.empty()
    
    def is_full(self) -> bool:
        """Check if queue is full."""
        return self._queue.full()