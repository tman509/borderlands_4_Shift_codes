"""
Thread management for Discord message updates and replies.
"""

import logging
import requests
import json
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from enum import Enum

from ..models.code import ParsedCode
from ..storage.repositories import AnnouncementRepository
from .rate_limiter import RateLimiter
from .message_formatter import MessageFormatter
from ..utils.retry import retry_with_backoff

logger = logging.getLogger(__name__)


class UpdateType(Enum):
    """Types of updates that can be made to messages."""
    METADATA_CHANGE = "metadata_change"
    EXPIRATION_UPDATE = "expiration_update"
    STATUS_CHANGE = "status_change"
    CORRECTION = "correction"


@dataclass
class ThreadedUpdate:
    """Represents a threaded update to a Discord message."""
    original_message_id: str
    channel_id: str
    update_type: UpdateType
    update_content: Dict[str, Any]
    created_at: datetime
    thread_message_id: Optional[str] = None
    status: str = "pending"  # pending, sent, failed
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        data = asdict(self)
        data["created_at"] = self.created_at.isoformat()
        data["update_type"] = self.update_type.value
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ThreadedUpdate':
        """Create from dictionary."""
        data = data.copy()
        data["created_at"] = datetime.fromisoformat(data["created_at"])
        data["update_type"] = UpdateType(data["update_type"])
        return cls(**data)


class ThreadManager:
    """Manages threaded updates and replies for Discord messages."""
    
    def __init__(self, 
                 announcement_repository: AnnouncementRepository,
                 rate_limiter: RateLimiter,
                 message_formatter: MessageFormatter):
        
        self.announcement_repository = announcement_repository
        self.rate_limiter = rate_limiter
        self.message_formatter = message_formatter
        
        # Session for Discord API calls
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'ShiftCodeBot/2.0 (Discord Thread Manager)',
            'Content-Type': 'application/json'
        })
        
        # Configuration
        self.config = {
            "enable_threads": True,
            "thread_auto_archive_duration": 1440,  # 24 hours in minutes
            "max_thread_name_length": 100,
            "enable_update_embeds": True,
            "update_threshold_minutes": 5,  # Minimum time between updates
            "max_updates_per_thread": 10,  # Maximum updates in one thread
        }
        
        # Cache for thread information
        self._thread_cache: Dict[str, Dict[str, Any]] = {}
        
        # Statistics
        self.stats = {
            "threads_created": 0,
            "updates_sent": 0,
            "updates_failed": 0,
            "threads_archived": 0
        }
        
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    def send_threaded_update(self, 
                           code: ParsedCode, 
                           changes: Dict[str, Any],
                           webhook_url: str,
                           original_message_id: Optional[str] = None) -> Optional[ThreadedUpdate]:
        """Send a threaded update for code metadata changes."""
        
        if not self.config["enable_threads"]:
            self.logger.debug("Threaded updates disabled")
            return None
        
        try:
            # Find original announcement if not provided
            if not original_message_id:
                original_message_id = self._find_original_message_id(code)
            
            if not original_message_id:
                self.logger.warning(f"No original message found for code {code.code_display}")
                return None
            
            # Check if we should create an update
            if not self._should_create_update(code, changes):
                self.logger.debug(f"Update not significant enough for code {code.code_display}")
                return None
            
            # Create threaded update
            update = ThreadedUpdate(
                original_message_id=original_message_id,
                channel_id=self._extract_channel_from_webhook(webhook_url),
                update_type=self._determine_update_type(changes),
                update_content=changes,
                created_at=datetime.now(timezone.utc)
            )
            
            # Send the update
            success = self._send_update_message(update, code, webhook_url)
            
            if success:
                update.status = "sent"
                self.stats["updates_sent"] += 1
                self.logger.info(f"Sent threaded update for code {code.code_display}")
            else:
                update.status = "failed"
                self.stats["updates_failed"] += 1
                self.logger.warning(f"Failed to send threaded update for code {code.code_display}")
            
            return update
            
        except Exception as e:
            self.logger.error(f"Error sending threaded update for code {code.code_display}: {e}")
            return None
    
    def create_thread_for_code(self, 
                             code: ParsedCode,
                             webhook_url: str,
                             original_message_id: str,
                             thread_name: Optional[str] = None) -> Optional[str]:
        """Create a thread for a specific code announcement."""
        
        if not self.config["enable_threads"]:
            return None
        
        try:
            # Generate thread name if not provided
            if not thread_name:
                thread_name = self._generate_thread_name(code)
            
            # Truncate thread name if too long
            if len(thread_name) > self.config["max_thread_name_length"]:
                thread_name = thread_name[:self.config["max_thread_name_length"] - 3] + "..."
            
            # Extract channel ID from webhook URL
            channel_id = self._extract_channel_from_webhook(webhook_url)
            if not channel_id:
                self.logger.error("Could not extract channel ID from webhook URL")
                return None
            
            # Create thread via Discord API
            thread_data = {
                "name": thread_name,
                "auto_archive_duration": self.config["thread_auto_archive_duration"],
                "type": 11  # PUBLIC_THREAD
            }
            
            # Note: This would require a bot token, not webhook
            # For webhook-only implementation, we'll use a different approach
            self.logger.info(f"Thread creation requested for code {code.code_display}")
            
            # Cache thread info
            thread_id = f"thread_{original_message_id}"  # Placeholder
            self._thread_cache[original_message_id] = {
                "thread_id": thread_id,
                "thread_name": thread_name,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "update_count": 0
            }
            
            self.stats["threads_created"] += 1
            return thread_id
            
        except Exception as e:
            self.logger.error(f"Error creating thread for code {code.code_display}: {e}")
            return None
    
    def send_update_reply(self,
                         code: ParsedCode,
                         changes: Dict[str, Any],
                         webhook_url: str,
                         original_message_id: str) -> bool:
        """Send an update as a reply to the original message."""
        
        try:
            # Format update message
            update_message = self._format_update_message(code, changes)
            
            # Add reference to original message
            message_data = {
                "content": update_message,
                "username": "SHiFT Code Bot - Update",
                "message_reference": {
                    "message_id": original_message_id
                }
            }
            
            # Add embed if enabled
            if self.config["enable_update_embeds"]:
                embed = self._create_update_embed(code, changes)
                message_data["embeds"] = [embed]
            
            # Send via webhook
            response = self._send_webhook_message(webhook_url, message_data)
            
            if response and response.status_code == 204:
                self.logger.info(f"Sent update reply for code {code.code_display}")
                return True
            else:
                self.logger.warning(f"Failed to send update reply for code {code.code_display}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error sending update reply for code {code.code_display}: {e}")
            return False
    
    def _find_original_message_id(self, code: ParsedCode) -> Optional[str]:
        """Find the original Discord message ID for a code."""
        try:
            # Query announcements repository
            announcements = self.announcement_repository.get_announcements_for_code(code.id)
            
            # Find the most recent announcement
            if announcements:
                latest = max(announcements, key=lambda x: x.get("announced_at", ""))
                return latest.get("message_id")
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error finding original message ID for code {code.code_display}: {e}")
            return None
    
    def _should_create_update(self, code: ParsedCode, changes: Dict[str, Any]) -> bool:
        """Determine if changes are significant enough to warrant an update."""
        
        # Always update for expiration changes
        if "expiration" in changes:
            return True
        
        # Update for reward type changes
        if "reward_type" in changes:
            return True
        
        # Update for platform changes
        if "platforms" in changes:
            return True
        
        # Update for significant confidence improvements
        if "confidence_improvement" in changes:
            improvement = changes["confidence_improvement"]
            return improvement > 0.2  # 20% improvement threshold
        
        # Don't update for minor changes
        return False
    
    def _determine_update_type(self, changes: Dict[str, Any]) -> UpdateType:
        """Determine the type of update based on changes."""
        
        if "expiration" in changes:
            return UpdateType.EXPIRATION_UPDATE
        
        if any(key in changes for key in ["reward_type", "platforms"]):
            return UpdateType.METADATA_CHANGE
        
        if "confidence_improvement" in changes:
            return UpdateType.CORRECTION
        
        return UpdateType.METADATA_CHANGE
    
    def _send_update_message(self, update: ThreadedUpdate, code: ParsedCode, webhook_url: str) -> bool:
        """Send the actual update message."""
        
        try:
            # Check rate limits
            if not self.rate_limiter.can_send(update.channel_id):
                wait_time = self.rate_limiter.wait_time(update.channel_id)
                self.logger.debug(f"Rate limited, waiting {wait_time:.1f}s")
                return False
            
            # Format the update message
            message_content = self._format_update_message(code, update.update_content)
            
            # Create message data
            message_data = {
                "content": f"🔄 **Update for code `{code.code_display}`**\n{message_content}",
                "username": "SHiFT Code Bot - Update"
            }
            
            # Add embed if enabled
            if self.config["enable_update_embeds"]:
                embed = self._create_update_embed(code, update.update_content)
                message_data["embeds"] = [embed]
            
            # Send message
            response = self._send_webhook_message(webhook_url, message_data)
            
            if response and response.status_code == 204:
                # Record success
                self.rate_limiter.record_success(update.channel_id)
                
                # Extract message ID from response if available
                message_id = response.headers.get('X-Message-Id')
                if message_id:
                    update.thread_message_id = message_id
                
                return True
            else:
                # Record failure
                error_code = response.status_code if response else None
                self.rate_limiter.record_failure(update.channel_id, error_code)
                return False
                
        except Exception as e:
            self.logger.error(f"Error sending update message: {e}")
            self.rate_limiter.record_failure(update.channel_id)
            return False
    
    def _format_update_message(self, code: ParsedCode, changes: Dict[str, Any]) -> str:
        """Format the update message content."""
        
        # Use the message formatter to format changes
        formatted_changes = self.message_formatter._format_changes(changes)
        
        # Add timestamp
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        
        return f"{formatted_changes}\n\n*Updated at {timestamp}*"
    
    def _create_update_embed(self, code: ParsedCode, changes: Dict[str, Any]) -> Dict[str, Any]:
        """Create an embed for the update message."""
        
        embed = {
            "title": "Code Update",
            "color": 0xffaa00,  # Orange
            "fields": [
                {
                    "name": "Code",
                    "value": f"`{code.code_display}`",
                    "inline": True
                },
                {
                    "name": "Changes",
                    "value": self.message_formatter._format_changes(changes),
                    "inline": False
                }
            ],
            "footer": {
                "text": "SHiFT Code Bot Update"
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        return embed
    
    @retry_with_backoff(max_attempts=3, initial_delay=1.0, exceptions=(requests.RequestException,))
    def _send_webhook_message(self, webhook_url: str, message_data: Dict[str, Any]) -> Optional[requests.Response]:
        """Send message via Discord webhook."""
        
        try:
            response = self.session.post(
                webhook_url,
                json=message_data,
                timeout=30
            )
            return response
            
        except requests.RequestException as e:
            self.logger.error(f"Webhook request failed: {e}")
            raise
    
    def _extract_channel_from_webhook(self, webhook_url: str) -> Optional[str]:
        """Extract channel ID from webhook URL."""
        
        # Discord webhook URL format: https://discord.com/api/webhooks/{channel_id}/{token}
        try:
            parts = webhook_url.split('/')
            if len(parts) >= 6 and 'webhooks' in parts:
                webhook_index = parts.index('webhooks')
                if webhook_index + 1 < len(parts):
                    return parts[webhook_index + 1]
            return None
            
        except Exception as e:
            self.logger.error(f"Error extracting channel ID from webhook URL: {e}")
            return None
    
    def _generate_thread_name(self, code: ParsedCode) -> str:
        """Generate a thread name for a code."""
        
        reward = code.reward_type.title() if code.reward_type else "Unknown"
        
        # Include expiration info if available
        if code.expires_at:
            exp_date = code.expires_at.strftime("%m/%d")
            return f"{code.code_display} - {reward} (expires {exp_date})"
        else:
            return f"{code.code_display} - {reward}"
    
    def get_thread_info(self, original_message_id: str) -> Optional[Dict[str, Any]]:
        """Get thread information for a message."""
        return self._thread_cache.get(original_message_id)
    
    def cleanup_old_threads(self, days_old: int = 7) -> int:
        """Clean up old thread cache entries."""
        
        cutoff_time = datetime.now(timezone.utc).timestamp() - (days_old * 24 * 3600)
        threads_to_remove = []
        
        for message_id, thread_info in self._thread_cache.items():
            try:
                created_at = datetime.fromisoformat(thread_info["created_at"])
                if created_at.timestamp() < cutoff_time:
                    threads_to_remove.append(message_id)
            except Exception:
                # Remove invalid entries
                threads_to_remove.append(message_id)
        
        # Remove old entries
        for message_id in threads_to_remove:
            del self._thread_cache[message_id]
        
        if threads_to_remove:
            self.logger.info(f"Cleaned up {len(threads_to_remove)} old thread cache entries")
        
        return len(threads_to_remove)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get thread manager statistics."""
        
        stats = self.stats.copy()
        stats.update({
            "cached_threads": len(self._thread_cache),
            "config": self.config.copy()
        })
        
        # Calculate success rate
        total_updates = stats["updates_sent"] + stats["updates_failed"]
        if total_updates > 0:
            stats["update_success_rate"] = stats["updates_sent"] / total_updates
        
        return stats
    
    def update_config(self, new_config: Dict[str, Any]) -> None:
        """Update thread manager configuration."""
        
        self.config.update(new_config)
        self.logger.info(f"Thread manager config updated: {new_config}")
    
    def health_check(self) -> Dict[str, Any]:
        """Perform health check of thread manager."""
        
        return {
            "status": "healthy",
            "threads_enabled": self.config["enable_threads"],
            "cached_threads": len(self._thread_cache),
            "stats": self.get_stats()
        }