"""
Expiration reminder system for Shift Codes.

This module handles scheduling, managing, and sending expiration reminders
for codes that have expiration dates. It supports configurable timing,
cancellation for early invalidation, and integration with the notification system.
"""

import logging
import json
import threading
import time
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path
import sqlite3

from ..models.code import ParsedCode
from ..models.config import NotificationSettings
from .discord_notifier import DiscordNotifier
from .queue import QueuedMessage, MessagePriority
from ..storage.database import Database

logger = logging.getLogger(__name__)


class ReminderStatus(Enum):
    """Status of scheduled reminders."""
    SCHEDULED = "scheduled"
    SENT = "sent"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    FAILED = "failed"


@dataclass
class ScheduledReminder:
    """A scheduled expiration reminder."""
    id: str
    code_id: int
    code_canonical: str
    reminder_time: datetime
    expiration_time: datetime
    channels: List[str]
    status: ReminderStatus = ReminderStatus.SCHEDULED
    created_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc)
        
        # Ensure datetime objects are timezone-aware
        if self.reminder_time.tzinfo is None:
            self.reminder_time = self.reminder_time.replace(tzinfo=timezone.utc)
        
        if self.expiration_time.tzinfo is None:
            self.expiration_time = self.expiration_time.replace(tzinfo=timezone.utc)
        
        if self.created_at.tzinfo is None:
            self.created_at = self.created_at.replace(tzinfo=timezone.utc)
    
    def is_due(self) -> bool:
        """Check if reminder is due to be sent."""
        if self.status != ReminderStatus.SCHEDULED:
            return False
        
        now = datetime.now(timezone.utc)
        return now >= self.reminder_time
    
    def is_expired(self) -> bool:
        """Check if the code has already expired."""
        now = datetime.now(timezone.utc)
        return now >= self.expiration_time
    
    def can_retry(self) -> bool:
        """Check if reminder can be retried."""
        return (self.status == ReminderStatus.FAILED and 
                self.retry_count < self.max_retries and 
                not self.is_expired())
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        data = asdict(self)
        
        # Convert datetime objects to ISO strings
        for field in ['reminder_time', 'expiration_time', 'created_at', 'sent_at', 'cancelled_at']:
            if data[field]:
                data[field] = data[field].isoformat()
        
        # Convert enum to value
        data['status'] = self.status.value
        
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ScheduledReminder':
        """Create from dictionary."""
        # Convert ISO strings back to datetime objects
        for field in ['reminder_time', 'expiration_time', 'created_at', 'sent_at', 'cancelled_at']:
            if data.get(field):
                data[field] = datetime.fromisoformat(data[field])
        
        # Convert enum value back to enum
        if 'status' in data:
            data['status'] = ReminderStatus(data['status'])
        
        return cls(**data)


class ExpirationReminderSystem:
    """System for managing expiration reminders for Shift Codes."""
    
    def __init__(self, 
                 database: Database,
                 discord_notifier: DiscordNotifier,
                 notification_settings: NotificationSettings):
        
        self.database = database
        self.discord_notifier = discord_notifier
        self.notification_settings = notification_settings
        
        # In-memory reminder storage
        self._reminders: Dict[str, ScheduledReminder] = {}
        self._lock = threading.RLock()
        
        # Background processing
        self._running = False
        self._processor_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        
        # Statistics
        self.stats = {
            "reminders_scheduled": 0,
            "reminders_sent": 0,
            "reminders_cancelled": 0,
            "reminders_failed": 0,
            "reminders_expired": 0
        }
        
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        
        # Initialize database schema
        self._initialize_schema()
        
        # Load existing reminders
        self._load_reminders()
    
    def _initialize_schema(self) -> None:
        """Initialize reminder database schema."""
        with self.database.get_connection() as conn:
            try:
                # Create reminders table
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS reminders (
                        id TEXT PRIMARY KEY,
                        code_id INTEGER NOT NULL,
                        code_canonical TEXT NOT NULL,
                        reminder_time TIMESTAMP NOT NULL,
                        expiration_time TIMESTAMP NOT NULL,
                        channels TEXT NOT NULL, -- JSON array
                        status TEXT CHECK(status IN ('scheduled', 'sent', 'cancelled', 'expired', 'failed')) DEFAULT 'scheduled',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        sent_at TIMESTAMP,
                        cancelled_at TIMESTAMP,
                        error_message TEXT,
                        retry_count INTEGER DEFAULT 0,
                        max_retries INTEGER DEFAULT 3,
                        FOREIGN KEY (code_id) REFERENCES codes(id)
                    )
                """)
                
                # Create indexes
                conn.execute("CREATE INDEX IF NOT EXISTS idx_reminders_reminder_time ON reminders(reminder_time)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_reminders_status ON reminders(status)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_reminders_code_id ON reminders(code_id)")
                
                conn.commit()
                self.logger.debug("Reminder database schema initialized")
                
            except Exception as e:
                conn.rollback()
                self.logger.error(f"Failed to initialize reminder schema: {e}")
                raise
    
    def schedule_reminder(self, code: ParsedCode, channels: List[str]) -> Optional[str]:
        """Schedule an expiration reminder for a code."""
        
        # Check if reminders are enabled
        if not self.notification_settings.enable_expiration_reminders:
            self.logger.debug("Expiration reminders are disabled")
            return None
        
        # Check if code has expiration date
        if not code.expires_at:
            self.logger.debug(f"Code {code.code_canonical} has no expiration date, skipping reminder")
            return None
        
        # Calculate reminder time
        reminder_time = code.expires_at - timedelta(hours=self.notification_settings.reminder_hours_before)
        
        # Don't schedule if reminder time is in the past
        now = datetime.now(timezone.utc)
        if reminder_time <= now:
            self.logger.debug(f"Reminder time for code {code.code_canonical} is in the past, skipping")
            return None
        
        # Create reminder
        reminder_id = f"reminder_{code.id}_{int(time.time() * 1000)}"
        reminder = ScheduledReminder(
            id=reminder_id,
            code_id=code.id,
            code_canonical=code.code_canonical,
            reminder_time=reminder_time,
            expiration_time=code.expires_at,
            channels=channels.copy(),
            max_retries=self.notification_settings.max_retries
        )
        
        with self._lock:
            try:
                # Store in database
                self._save_reminder_to_db(reminder)
                
                # Store in memory
                self._reminders[reminder_id] = reminder
                
                # Update statistics
                self.stats["reminders_scheduled"] += 1
                
                self.logger.info(f"Scheduled reminder {reminder_id} for code {code.code_canonical} "
                               f"at {reminder_time.isoformat()}")
                
                return reminder_id
                
            except Exception as e:
                self.logger.error(f"Failed to schedule reminder for code {code.code_canonical}: {e}")
                return None
    
    def cancel_reminder(self, code_canonical: str, reason: str = "Code invalidated") -> bool:
        """Cancel all reminders for a specific code."""
        
        with self._lock:
            cancelled_count = 0
            
            for reminder_id, reminder in self._reminders.items():
                if (reminder.code_canonical == code_canonical and 
                    reminder.status == ReminderStatus.SCHEDULED):
                    
                    # Update reminder status
                    reminder.status = ReminderStatus.CANCELLED
                    reminder.cancelled_at = datetime.now(timezone.utc)
                    reminder.error_message = reason
                    
                    # Update in database
                    self._update_reminder_in_db(reminder)
                    
                    cancelled_count += 1
                    
                    self.logger.info(f"Cancelled reminder {reminder_id} for code {code_canonical}: {reason}")
            
            if cancelled_count > 0:
                self.stats["reminders_cancelled"] += cancelled_count
                return True
            
            return False
    
    def cancel_reminder_by_id(self, reminder_id: str, reason: str = "Manual cancellation") -> bool:
        """Cancel a specific reminder by ID."""
        
        with self._lock:
            if reminder_id in self._reminders:
                reminder = self._reminders[reminder_id]
                
                if reminder.status == ReminderStatus.SCHEDULED:
                    reminder.status = ReminderStatus.CANCELLED
                    reminder.cancelled_at = datetime.now(timezone.utc)
                    reminder.error_message = reason
                    
                    # Update in database
                    self._update_reminder_in_db(reminder)
                    
                    self.stats["reminders_cancelled"] += 1
                    
                    self.logger.info(f"Cancelled reminder {reminder_id}: {reason}")
                    return True
            
            return False
    
    def get_due_reminders(self) -> List[ScheduledReminder]:
        """Get all reminders that are due to be sent."""
        
        with self._lock:
            due_reminders = []
            
            for reminder in self._reminders.values():
                if reminder.is_due() and not reminder.is_expired():
                    due_reminders.append(reminder)
            
            # Sort by reminder time (earliest first)
            due_reminders.sort(key=lambda r: r.reminder_time)
            
            return due_reminders
    
    def process_due_reminders(self) -> Dict[str, Any]:
        """Process all due reminders."""
        
        due_reminders = self.get_due_reminders()
        
        if not due_reminders:
            return {
                "processed": 0,
                "sent": 0,
                "failed": 0,
                "expired": 0
            }
        
        processed = 0
        sent = 0
        failed = 0
        expired = 0
        
        for reminder in due_reminders:
            try:
                # Check if code has expired since scheduling
                if reminder.is_expired():
                    self._mark_reminder_expired(reminder)
                    expired += 1
                    processed += 1
                    continue
                
                # Get code details from database
                code = self._get_code_by_id(reminder.code_id)
                if not code:
                    self._mark_reminder_failed(reminder, "Code not found in database")
                    failed += 1
                    processed += 1
                    continue
                
                # Check if code is still valid (not expired or invalidated)
                if code.status in ['expired', 'invalid']:
                    self._mark_reminder_cancelled(reminder, f"Code status is {code.status}")
                    processed += 1
                    continue
                
                # Send reminder
                result = self._send_reminder(reminder, code)
                
                if result:
                    self._mark_reminder_sent(reminder)
                    sent += 1
                else:
                    self._mark_reminder_failed(reminder, "Failed to send notification")
                    failed += 1
                
                processed += 1
                
            except Exception as e:
                self.logger.error(f"Error processing reminder {reminder.id}: {e}")
                self._mark_reminder_failed(reminder, str(e))
                failed += 1
                processed += 1
        
        if processed > 0:
            self.logger.info(f"Processed {processed} reminders: {sent} sent, {failed} failed, {expired} expired")
        
        return {
            "processed": processed,
            "sent": sent,
            "failed": failed,
            "expired": expired
        }
    
    def _send_reminder(self, reminder: ScheduledReminder, code: ParsedCode) -> bool:
        """Send a reminder notification."""
        
        try:
            # Send expiration reminder via Discord
            results = self.discord_notifier.send_expiration_reminder(code, reminder.channels)
            
            # Check if at least one channel succeeded
            success_count = sum(1 for result in results.values() if result.is_success())
            
            if success_count > 0:
                self.logger.info(f"Sent expiration reminder for code {code.code_canonical} "
                               f"to {success_count}/{len(reminder.channels)} channels")
                return True
            else:
                error_messages = [f"{ch}: {res.error}" for ch, res in results.items() if res.error]
                self.logger.warning(f"Failed to send reminder for code {code.code_canonical}: "
                                  f"{'; '.join(error_messages)}")
                return False
                
        except Exception as e:
            self.logger.error(f"Exception sending reminder for code {code.code_canonical}: {e}")
            return False
    
    def _mark_reminder_sent(self, reminder: ScheduledReminder) -> None:
        """Mark a reminder as successfully sent."""
        
        reminder.status = ReminderStatus.SENT
        reminder.sent_at = datetime.now(timezone.utc)
        
        self._update_reminder_in_db(reminder)
        self.stats["reminders_sent"] += 1
    
    def _mark_reminder_failed(self, reminder: ScheduledReminder, error: str) -> None:
        """Mark a reminder as failed."""
        
        reminder.retry_count += 1
        reminder.error_message = error
        
        if reminder.can_retry():
            # Schedule retry with exponential backoff
            retry_delay = min(300 * (2 ** reminder.retry_count), 3600)  # Max 1 hour
            reminder.reminder_time = datetime.now(timezone.utc) + timedelta(seconds=retry_delay)
            
            self.logger.info(f"Scheduling retry {reminder.retry_count} for reminder {reminder.id} "
                           f"in {retry_delay} seconds")
        else:
            reminder.status = ReminderStatus.FAILED
            self.stats["reminders_failed"] += 1
            
            self.logger.warning(f"Reminder {reminder.id} permanently failed after "
                              f"{reminder.retry_count} retries: {error}")
        
        self._update_reminder_in_db(reminder)
    
    def _mark_reminder_expired(self, reminder: ScheduledReminder) -> None:
        """Mark a reminder as expired (code expired before reminder was sent)."""
        
        reminder.status = ReminderStatus.EXPIRED
        
        self._update_reminder_in_db(reminder)
        self.stats["reminders_expired"] += 1
        
        self.logger.debug(f"Reminder {reminder.id} expired (code already expired)")
    
    def _mark_reminder_cancelled(self, reminder: ScheduledReminder, reason: str) -> None:
        """Mark a reminder as cancelled."""
        
        reminder.status = ReminderStatus.CANCELLED
        reminder.cancelled_at = datetime.now(timezone.utc)
        reminder.error_message = reason
        
        self._update_reminder_in_db(reminder)
        self.stats["reminders_cancelled"] += 1
    
    def _save_reminder_to_db(self, reminder: ScheduledReminder) -> None:
        """Save a reminder to the database."""
        
        with self.database.get_connection() as conn:
            conn.execute("""
                INSERT INTO reminders (
                    id, code_id, code_canonical, reminder_time, expiration_time,
                    channels, status, created_at, retry_count, max_retries
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                reminder.id,
                reminder.code_id,
                reminder.code_canonical,
                reminder.reminder_time.isoformat(),
                reminder.expiration_time.isoformat(),
                json.dumps(reminder.channels),
                reminder.status.value,
                reminder.created_at.isoformat(),
                reminder.retry_count,
                reminder.max_retries
            ))
            conn.commit()
    
    def _update_reminder_in_db(self, reminder: ScheduledReminder) -> None:
        """Update a reminder in the database."""
        
        with self.database.get_connection() as conn:
            conn.execute("""
                UPDATE reminders SET
                    status = ?,
                    sent_at = ?,
                    cancelled_at = ?,
                    error_message = ?,
                    retry_count = ?,
                    reminder_time = ?
                WHERE id = ?
            """, (
                reminder.status.value,
                reminder.sent_at.isoformat() if reminder.sent_at else None,
                reminder.cancelled_at.isoformat() if reminder.cancelled_at else None,
                reminder.error_message,
                reminder.retry_count,
                reminder.reminder_time.isoformat(),
                reminder.id
            ))
            conn.commit()
    
    def _load_reminders(self) -> None:
        """Load existing reminders from database."""
        
        with self.database.get_connection() as conn:
            cursor = conn.execute("""
                SELECT * FROM reminders 
                WHERE status IN ('scheduled', 'failed')
                ORDER BY reminder_time
            """)
            
            loaded_count = 0
            
            for row in cursor.fetchall():
                try:
                    reminder = ScheduledReminder(
                        id=row['id'],
                        code_id=row['code_id'],
                        code_canonical=row['code_canonical'],
                        reminder_time=datetime.fromisoformat(row['reminder_time']),
                        expiration_time=datetime.fromisoformat(row['expiration_time']),
                        channels=json.loads(row['channels']),
                        status=ReminderStatus(row['status']),
                        created_at=datetime.fromisoformat(row['created_at']) if row['created_at'] else None,
                        sent_at=datetime.fromisoformat(row['sent_at']) if row['sent_at'] else None,
                        cancelled_at=datetime.fromisoformat(row['cancelled_at']) if row['cancelled_at'] else None,
                        error_message=row['error_message'],
                        retry_count=row['retry_count'],
                        max_retries=row['max_retries']
                    )
                    
                    self._reminders[reminder.id] = reminder
                    loaded_count += 1
                    
                except Exception as e:
                    self.logger.warning(f"Failed to load reminder {row['id']}: {e}")
            
            if loaded_count > 0:
                self.logger.info(f"Loaded {loaded_count} existing reminders from database")
    
    def _get_code_by_id(self, code_id: int) -> Optional[ParsedCode]:
        """Get code details from database by ID."""
        
        with self.database.get_connection() as conn:
            cursor = conn.execute("""
                SELECT * FROM codes WHERE id = ?
            """, (code_id,))
            
            row = cursor.fetchone()
            if not row:
                return None
            
            # Convert database row to ParsedCode
            return ParsedCode(
                id=row['id'],
                code_canonical=row['code_canonical'],
                code_display=row['code_display'],
                reward_type=row['reward_type'],
                platforms=json.loads(row['platforms']) if row['platforms'] else [],
                expires_at=datetime.fromisoformat(row['expires_at_utc']) if row['expires_at_utc'] else None,
                source_id=row['source_id'],
                context=row['context'],
                confidence_score=row['confidence_score'],
                status=row['status']
            )
    
    def start_background_processing(self, check_interval: int = 60) -> None:
        """Start background processing of reminders."""
        
        if self._running:
            self.logger.warning("Background processing is already running")
            return
        
        self._running = True
        self._stop_event.clear()
        
        def processor():
            self.logger.info(f"Started reminder background processing (check interval: {check_interval}s)")
            
            while not self._stop_event.wait(check_interval):
                try:
                    # Process due reminders
                    self.process_due_reminders()
                    
                    # Clean up old completed reminders
                    self.cleanup_old_reminders()
                    
                except Exception as e:
                    self.logger.error(f"Error in reminder background processing: {e}")
            
            self.logger.info("Stopped reminder background processing")
        
        self._processor_thread = threading.Thread(target=processor, daemon=True)
        self._processor_thread.start()
    
    def stop_background_processing(self) -> None:
        """Stop background processing of reminders."""
        
        if not self._running:
            return
        
        self._running = False
        self._stop_event.set()
        
        if self._processor_thread and self._processor_thread.is_alive():
            self._processor_thread.join(timeout=5.0)
        
        self.logger.info("Stopped reminder background processing")
    
    def cleanup_old_reminders(self, days: int = 7) -> int:
        """Clean up old completed reminders."""
        
        cutoff_time = datetime.now(timezone.utc) - timedelta(days=days)
        
        with self._lock:
            # Remove from memory
            old_reminder_ids = []
            for reminder_id, reminder in self._reminders.items():
                if (reminder.status in [ReminderStatus.SENT, ReminderStatus.EXPIRED, ReminderStatus.CANCELLED] and
                    reminder.created_at and reminder.created_at < cutoff_time):
                    old_reminder_ids.append(reminder_id)
            
            for reminder_id in old_reminder_ids:
                del self._reminders[reminder_id]
            
            # Remove from database
            with self.database.get_connection() as conn:
                cursor = conn.execute("""
                    DELETE FROM reminders 
                    WHERE status IN ('sent', 'expired', 'cancelled')
                    AND created_at < ?
                """, (cutoff_time.isoformat(),))
                
                deleted_count = cursor.rowcount
                conn.commit()
            
            if deleted_count > 0:
                self.logger.info(f"Cleaned up {deleted_count} old reminders")
            
            return deleted_count
    
    def get_reminder_stats(self) -> Dict[str, Any]:
        """Get reminder system statistics."""
        
        with self._lock:
            stats = self.stats.copy()
            
            # Add current counts
            status_counts = {}
            for reminder in self._reminders.values():
                status = reminder.status.value
                status_counts[status] = status_counts.get(status, 0) + 1
            
            stats.update({
                "active_reminders": len(self._reminders),
                "status_counts": status_counts,
                "background_processing": self._running
            })
            
            return stats
    
    def get_reminders_for_code(self, code_canonical: str) -> List[ScheduledReminder]:
        """Get all reminders for a specific code."""
        
        with self._lock:
            return [r for r in self._reminders.values() if r.code_canonical == code_canonical]
    
    def health_check(self) -> Dict[str, Any]:
        """Perform health check of reminder system."""
        
        health = {
            "status": "healthy",
            "components": {
                "database": "ok",
                "background_processor": "ok" if self._running else "stopped",
                "memory_storage": "ok"
            },
            "stats": self.get_reminder_stats()
        }
        
        # Check for issues
        stats = self.get_reminder_stats()
        
        # Check if too many reminders are failing
        if stats.get("reminders_failed", 0) > stats.get("reminders_sent", 1) * 0.1:  # >10% failure rate
            health["components"]["background_processor"] = "warning"
            health["warnings"] = health.get("warnings", [])
            health["warnings"].append("High reminder failure rate detected")
        
        # Check if background processing is running when it should be
        if not self._running and stats.get("active_reminders", 0) > 0:
            health["components"]["background_processor"] = "warning"
            health["warnings"] = health.get("warnings", [])
            health["warnings"].append("Background processing stopped but reminders are pending")
        
        return health