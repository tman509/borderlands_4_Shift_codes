"""
Enhanced Discord notification system with webhooks, rate limiting, and rich formatting.
"""

import logging
import requests
import json
import time
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime, timezone
from dataclasses import dataclass
from enum import Enum

from ..models.code import ParsedCode
from ..models.config import ChannelConfig
from .rate_limiter import RateLimiter, RateLimitConfig
from .message_formatter import MessageFormatter
from .queue import MessageQueue, QueuedMessage, MessagePriority
from ..utils.retry import retry_with_backoff

logger = logging.getLogger(__name__)


class NotificationResult(Enum):
    """Result of notification attempt."""
    SUCCESS = "success"
    RATE_LIMITED = "rate_limited"
    FAILED = "failed"
    QUEUED = "queued"
    SKIPPED = "skipped"


@dataclass
class NotificationResponse:
    """Response from notification attempt."""
    result: NotificationResult
    message_id: Optional[str] = None
    error: Optional[str] = None
    retry_after: Optional[int] = None
    
    def is_success(self) -> bool:
        return self.result == NotificationResult.SUCCESS


class DiscordNotifier:
    """Enhanced Discord notifier with rate limiting, queuing, and rich formatting."""
    
    def __init__(self, 
                 rate_limiter: Optional[RateLimiter] = None,
                 message_queue: Optional[MessageQueue] = None,
                 message_formatter: Optional[MessageFormatter] = None):
        
        self.rate_limiter = rate_limiter or RateLimiter(
            RateLimitConfig(
                requests_per_second=0.5,  # Discord webhook limit is ~5/sec, be conservative
                burst_capacity=5,
                refill_rate=0.5,
                adaptive=True
            )
        )
        
        self.message_queue = message_queue or MessageQueue(
            persistence_file="data/message_queue.json",
            max_size=1000
        )
        
        self.message_formatter = message_formatter or MessageFormatter()
        
        # Session for connection pooling
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'ShiftCodeBot/2.0 (Discord Webhook)',
            'Content-Type': 'application/json'
        })
        
        # Configuration
        self.config = {
            "max_retries": 3,
            "timeout": 30,
            "enable_embeds": True,
            "enable_queuing": True,
            "max_content_length": 2000,
            "max_embed_length": 6000,
            "enable_thread_updates": True
        }
        
        # Channel configurations
        self.channels: Dict[str, ChannelConfig] = {}
        
        # Statistics
        self.stats = {
            "messages_sent": 0,
            "messages_failed": 0,
            "messages_queued": 0,
            "rate_limit_hits": 0,
            "webhook_errors": 0
        }
        
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    def add_channel(self, channel_config: ChannelConfig) -> None:
        """Add a Discord channel configuration."""
        self.channels[channel_config.id] = channel_config
        
        # Set custom rate limit if specified in channel config
        if hasattr(channel_config, 'rate_limit') and channel_config.rate_limit:
            self.rate_limiter.set_channel_config(
                channel_config.id,
                RateLimitConfig(**channel_config.rate_limit)
            )
        
        self.logger.info(f"Added Discord channel: {channel_config.name} ({channel_config.id})")
    
    def send_new_code(self, code: ParsedCode, channels: Optional[List[str]] = None) -> Dict[str, NotificationResponse]:
        """Send new code notification to specified channels."""
        
        if channels is None:
            channels = list(self.channels.keys())
        
        # Format message
        message_data = self.message_formatter.format_new_code(
            code, 
            use_embed=self.config["enable_embeds"]
        )
        
        return self._send_to_channels(message_data, channels, MessagePriority.HIGH)
    
    def send_code_update(self, code: ParsedCode, changes: Dict[str, Any], 
                        channels: Optional[List[str]] = None) -> Dict[str, NotificationResponse]:
        """Send code update notification to specified channels."""
        
        if channels is None:
            channels = list(self.channels.keys())
        
        # Format message
        message_data = self.message_formatter.format_code_update(
            code, 
            changes,
            use_embed=self.config["enable_embeds"]
        )
        
        return self._send_to_channels(message_data, channels, MessagePriority.NORMAL)
    
    def send_expiration_reminder(self, code: ParsedCode, 
                               channels: Optional[List[str]] = None) -> Dict[str, NotificationResponse]:
        """Send expiration reminder to specified channels."""
        
        if channels is None:
            channels = list(self.channels.keys())
        
        # Format message
        message_data = self.message_formatter.format_expiration_reminder(
            code,
            use_embed=self.config["enable_embeds"]
        )
        
        return self._send_to_channels(message_data, channels, MessagePriority.LOW)
    
    def send_summary(self, codes: List[ParsedCode], time_period: str = "recently",
                    channels: Optional[List[str]] = None) -> Dict[str, NotificationResponse]:
        """Send summary of multiple codes to specified channels."""
        
        if channels is None:
            channels = list(self.channels.keys())
        
        # Format message
        message_data = self.message_formatter.format_summary(
            codes,
            time_period,
            use_embed=self.config["enable_embeds"]
        )
        
        return self._send_to_channels(message_data, channels, MessagePriority.NORMAL)
    
    def send_error(self, error_message: str, 
                  channels: Optional[List[str]] = None) -> Dict[str, NotificationResponse]:
        """Send error notification to specified channels."""
        
        if channels is None:
            channels = list(self.channels.keys())
        
        # Format message
        message_data = self.message_formatter.format_error(
            error_message,
            use_embed=self.config["enable_embeds"]
        )
        
        return self._send_to_channels(message_data, channels, MessagePriority.CRITICAL)
    
    def send_custom(self, message_data: Dict[str, Any], 
                   channels: Optional[List[str]] = None,
                   priority: MessagePriority = MessagePriority.NORMAL) -> Dict[str, NotificationResponse]:
        """Send custom message to specified channels."""
        
        if channels is None:
            channels = list(self.channels.keys())
        
        return self._send_to_channels(message_data, channels, priority)
    
    def _send_to_channels(self, message_data: Dict[str, Any], 
                         channels: List[str], 
                         priority: MessagePriority) -> Dict[str, NotificationResponse]:
        """Send message to multiple channels."""
        
        results = {}
        
        for channel_id in channels:
            if channel_id not in self.channels:
                results[channel_id] = NotificationResponse(
                    result=NotificationResult.FAILED,
                    error=f"Channel {channel_id} not configured"
                )
                continue
            
            try:
                result = self._send_to_channel(message_data, channel_id, priority)
                results[channel_id] = result
                
            except Exception as e:
                self.logger.error(f"Failed to send to channel {channel_id}: {e}")
                results[channel_id] = NotificationResponse(
                    result=NotificationResult.FAILED,
                    error=str(e)
                )
        
        return results
    
    def _send_to_channel(self, message_data: Dict[str, Any], 
                        channel_id: str, 
                        priority: MessagePriority) -> NotificationResponse:
        """Send message to a single channel."""
        
        channel_config = self.channels[channel_id]
        
        # Check if we can send immediately
        if self.rate_limiter.can_send(channel_id):
            return self._send_webhook_message(channel_config, message_data)
        
        # If queuing is enabled, queue the message
        if self.config["enable_queuing"]:
            return self._queue_message(message_data, channel_id, priority)
        
        # Otherwise, wait and try again
        wait_time = self.rate_limiter.wait_time(channel_id)
        if wait_time > 0 and wait_time < 60:  # Only wait up to 1 minute
            time.sleep(wait_time)
            return self._send_webhook_message(channel_config, message_data)
        
        return NotificationResponse(
            result=NotificationResult.RATE_LIMITED,
            error=f"Rate limited, wait time: {wait_time:.1f}s"
        )
    
    @retry_with_backoff(max_attempts=3, initial_delay=1.0, exceptions=(requests.RequestException,))
    def _send_webhook_message(self, channel_config: ChannelConfig, 
                            message_data: Dict[str, Any]) -> NotificationResponse:
        """Send message via Discord webhook."""
        
        try:
            # Validate and truncate message if needed
            validated_data = self._validate_message_data(message_data)
            
            # Send webhook request
            response = self.session.post(
                channel_config.webhook_url,
                json=validated_data,
                timeout=self.config["timeout"]
            )
            
            # Handle response
            if response.status_code == 204:  # Success
                self.rate_limiter.record_success(channel_config.id)
                self.stats["messages_sent"] += 1
                
                return NotificationResponse(
                    result=NotificationResult.SUCCESS,
                    message_id=response.headers.get('X-Message-Id')
                )
            
            elif response.status_code == 429:  # Rate limited
                retry_after = int(response.headers.get('Retry-After', 60))
                self.rate_limiter.record_failure(channel_config.id, 429)
                self.stats["rate_limit_hits"] += 1
                
                return NotificationResponse(
                    result=NotificationResult.RATE_LIMITED,
                    retry_after=retry_after,
                    error=f"Rate limited by Discord, retry after {retry_after}s"
                )
            
            else:  # Other error
                error_text = response.text
                self.rate_limiter.record_failure(channel_config.id, response.status_code)
                self.stats["webhook_errors"] += 1
                
                return NotificationResponse(
                    result=NotificationResult.FAILED,
                    error=f"HTTP {response.status_code}: {error_text}"
                )
        
        except requests.RequestException as e:
            self.rate_limiter.record_failure(channel_config.id)
            self.stats["messages_failed"] += 1
            
            return NotificationResponse(
                result=NotificationResult.FAILED,
                error=f"Request failed: {str(e)}"
            )
    
    def _queue_message(self, message_data: Dict[str, Any], 
                      channel_id: str, 
                      priority: MessagePriority) -> NotificationResponse:
        """Queue a message for later delivery."""
        
        # Create queued message
        queued_message = QueuedMessage(
            id=f"{channel_id}_{int(time.time() * 1000)}",
            channel_id=channel_id,
            content=json.dumps(message_data),
            priority=priority,
            created_at=datetime.now(timezone.utc),
            scheduled_for=datetime.now(timezone.utc),  # Send ASAP
            max_retries=self.config["max_retries"]
        )
        
        # Add to queue
        if self.message_queue.enqueue(queued_message):
            self.stats["messages_queued"] += 1
            
            return NotificationResponse(
                result=NotificationResult.QUEUED,
                message_id=queued_message.id
            )
        else:
            return NotificationResponse(
                result=NotificationResult.FAILED,
                error="Failed to queue message"
            )
    
    def _validate_message_data(self, message_data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and truncate message data to Discord limits."""
        
        validated = message_data.copy()
        
        # Truncate content if too long
        if "content" in validated and len(validated["content"]) > self.config["max_content_length"]:
            validated["content"] = validated["content"][:self.config["max_content_length"] - 3] + "..."
            self.logger.warning("Truncated message content due to length limit")
        
        # Validate embeds
        if "embeds" in validated:
            for embed in validated["embeds"]:
                # Truncate embed description
                if "description" in embed and len(embed["description"]) > 4096:
                    embed["description"] = embed["description"][:4093] + "..."
                
                # Truncate embed fields
                if "fields" in embed:
                    for field in embed["fields"]:
                        if "value" in field and len(field["value"]) > 1024:
                            field["value"] = field["value"][:1021] + "..."
        
        return validated
    
    def process_queue(self, max_messages: int = 10) -> Dict[str, Any]:
        """Process queued messages."""
        
        processed = 0
        successful = 0
        failed = 0
        
        while processed < max_messages:
            # Get next message
            message = self.message_queue.dequeue(timeout=0.1)
            if not message:
                break
            
            processed += 1
            
            try:
                # Parse message data
                message_data = json.loads(message.content)
                channel_config = self.channels.get(message.channel_id)
                
                if not channel_config:
                    self.message_queue.mark_failed(message.id, "Channel not found")
                    failed += 1
                    continue
                
                # Check rate limit
                if not self.rate_limiter.can_send(message.channel_id):
                    # Put message back in queue for later
                    self.message_queue.mark_failed(message.id, "Rate limited")
                    continue
                
                # Send message
                result = self._send_webhook_message(channel_config, message_data)
                
                if result.is_success():
                    self.message_queue.mark_sent(message.id)
                    successful += 1
                else:
                    self.message_queue.mark_failed(message.id, result.error or "Unknown error")
                    failed += 1
            
            except Exception as e:
                self.logger.error(f"Error processing queued message {message.id}: {e}")
                self.message_queue.mark_failed(message.id, str(e))
                failed += 1
        
        return {
            "processed": processed,
            "successful": successful,
            "failed": failed,
            "queue_size": self.message_queue.size()
        }
    
    def cleanup_old_messages(self, hours: int = 24) -> int:
        """Clean up old completed messages."""
        return self.message_queue.clear_completed_messages(hours)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get notification statistics."""
        stats = self.stats.copy()
        
        # Add queue stats
        queue_stats = self.message_queue.get_stats()
        stats.update({
            "queue_size": queue_stats["queue_size"],
            "queue_processing": queue_stats["processing_count"],
            "queue_success_rate": queue_stats.get("success_rate", 0.0)
        })
        
        # Add rate limiter stats
        rate_stats = self.rate_limiter.get_global_stats()
        stats.update({
            "rate_limit_success_rate": rate_stats.get("success_rate", 0.0),
            "channels_in_backoff": rate_stats.get("channels_in_backoff", 0)
        })
        
        return stats
    
    def get_channel_stats(self, channel_id: str) -> Dict[str, Any]:
        """Get statistics for a specific channel."""
        if channel_id not in self.channels:
            return {"error": "Channel not found"}
        
        return self.rate_limiter.get_channel_stats(channel_id)
    
    def reset_channel(self, channel_id: str) -> bool:
        """Reset rate limiting for a channel."""
        return self.rate_limiter.reset_channel(channel_id)
    
    def health_check(self) -> Dict[str, Any]:
        """Perform health check of Discord notifier."""
        
        health = {
            "status": "healthy",
            "components": {
                "rate_limiter": "ok",
                "message_queue": "ok",
                "message_formatter": "ok",
                "session": "ok"
            },
            "stats": self.get_stats()
        }
        
        # Check queue health
        if self.message_queue.size() > 500:  # Large queue might indicate issues
            health["components"]["message_queue"] = "warning"
            health["warnings"] = health.get("warnings", [])
            health["warnings"].append("Large message queue detected")
        
        # Check rate limiting health
        rate_stats = self.rate_limiter.get_global_stats()
        if rate_stats.get("channels_in_backoff", 0) > len(self.channels) * 0.5:
            health["components"]["rate_limiter"] = "warning"
            health["warnings"] = health.get("warnings", [])
            health["warnings"].append("Many channels in backoff state")
        
        return health