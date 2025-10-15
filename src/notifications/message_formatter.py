"""
Message formatting system with templates and variable substitution.
"""

import logging
import re
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from dataclasses import dataclass
from string import Template

from ..models.code import ParsedCode

logger = logging.getLogger(__name__)


@dataclass
class MessageTemplate:
    """Template for formatting messages."""
    name: str
    content_template: str
    embed_template: Optional[Dict[str, Any]] = None
    variables: Dict[str, str] = None
    
    def __post_init__(self):
        if self.variables is None:
            self.variables = {}


class MessageFormatter:
    """Advanced message formatter with template support and rich formatting."""
    
    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        
        # Built-in templates
        self.templates = {
            "new_code": MessageTemplate(
                name="new_code",
                content_template="🎮 **New SHiFT Code Found!**\n"
                               "**Code:** `$code`\n"
                               "**Reward:** $reward\n"
                               "**Platform(s):** $platforms\n"
                               "$expiration_info"
                               "**Source:** $source\n"
                               "**Redeem:** https://shift.gearboxsoftware.com/rewards",
                embed_template={
                    "title": "🎮 New SHiFT Code",
                    "color": 0x00ff00,  # Green
                    "fields": [
                        {"name": "Code", "value": "`$code`", "inline": True},
                        {"name": "Reward", "value": "$reward", "inline": True},
                        {"name": "Platform(s)", "value": "$platforms", "inline": True},
                    ],
                    "footer": {"text": "Source: $source"},
                    "timestamp": "$timestamp"
                }
            ),
            
            "code_update": MessageTemplate(
                name="code_update",
                content_template="🔄 **SHiFT Code Updated**\n"
                               "**Code:** `$code`\n"
                               "**Changes:** $changes\n"
                               "$expiration_info"
                               "**Redeem:** https://shift.gearboxsoftware.com/rewards",
                embed_template={
                    "title": "🔄 Code Updated",
                    "color": 0xffaa00,  # Orange
                    "fields": [
                        {"name": "Code", "value": "`$code`", "inline": True},
                        {"name": "Changes", "value": "$changes", "inline": False},
                    ],
                    "timestamp": "$timestamp"
                }
            ),
            
            "expiration_reminder": MessageTemplate(
                name="expiration_reminder",
                content_template="⏰ **SHiFT Code Expiring Soon!**\n"
                               "**Code:** `$code`\n"
                               "**Reward:** $reward\n"
                               "**Expires:** $expiration_time\n"
                               "**Redeem:** https://shift.gearboxsoftware.com/rewards",
                embed_template={
                    "title": "⏰ Code Expiring Soon",
                    "color": 0xff6600,  # Orange-red
                    "fields": [
                        {"name": "Code", "value": "`$code`", "inline": True},
                        {"name": "Reward", "value": "$reward", "inline": True},
                        {"name": "Expires", "value": "$expiration_time", "inline": True},
                    ],
                    "timestamp": "$timestamp"
                }
            ),
            
            "summary": MessageTemplate(
                name="summary",
                content_template="📊 **SHiFT Code Summary**\n"
                               "Found **$code_count** codes $time_period\n\n"
                               "$code_list\n"
                               "**Redeem:** https://shift.gearboxsoftware.com/rewards\n"
                               "_Individual notifications disabled to prevent spam_",
                embed_template={
                    "title": "📊 Code Summary",
                    "color": 0x0099ff,  # Blue
                    "description": "Found **$code_count** codes $time_period",
                    "fields": [
                        {"name": "Codes Found", "value": "$code_list", "inline": False},
                    ],
                    "footer": {"text": "Individual notifications disabled to prevent spam"},
                    "timestamp": "$timestamp"
                }
            ),
            
            "error": MessageTemplate(
                name="error",
                content_template="❌ **Error**\n$error_message",
                embed_template={
                    "title": "❌ Error",
                    "color": 0xff0000,  # Red
                    "description": "$error_message",
                    "timestamp": "$timestamp"
                }
            )
        }
        
        # Timezone for display
        self.display_timezone = "America/Denver"  # Configurable
    
    def format_new_code(self, code: ParsedCode, source_name: str = "", 
                       use_embed: bool = True) -> Dict[str, Any]:
        """Format a new code announcement."""
        
        variables = self._extract_code_variables(code, source_name)
        template = self.templates["new_code"]
        
        return self._format_message(template, variables, use_embed)
    
    def format_code_update(self, code: ParsedCode, changes: Dict[str, Any], 
                          use_embed: bool = True) -> Dict[str, Any]:
        """Format a code update notification."""
        
        variables = self._extract_code_variables(code)
        variables["changes"] = self._format_changes(changes)
        
        template = self.templates["code_update"]
        return self._format_message(template, variables, use_embed)
    
    def format_expiration_reminder(self, code: ParsedCode, 
                                 use_embed: bool = True) -> Dict[str, Any]:
        """Format an expiration reminder."""
        
        variables = self._extract_code_variables(code)
        template = self.templates["expiration_reminder"]
        
        return self._format_message(template, variables, use_embed)
    
    def format_summary(self, codes: List[ParsedCode], time_period: str = "recently",
                      use_embed: bool = True) -> Dict[str, Any]:
        """Format a summary of multiple codes."""
        
        variables = {
            "code_count": str(len(codes)),
            "time_period": time_period,
            "code_list": self._format_code_list(codes),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        template = self.templates["summary"]
        return self._format_message(template, variables, use_embed)
    
    def format_error(self, error_message: str, use_embed: bool = True) -> Dict[str, Any]:
        """Format an error message."""
        
        variables = {
            "error_message": error_message,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        template = self.templates["error"]
        return self._format_message(template, variables, use_embed)
    
    def format_custom(self, template_name: str, variables: Dict[str, Any],
                     use_embed: bool = True) -> Dict[str, Any]:
        """Format a message using a custom template."""
        
        if template_name not in self.templates:
            raise ValueError(f"Template '{template_name}' not found")
        
        # Add default timestamp if not provided
        if "timestamp" not in variables:
            variables["timestamp"] = datetime.now(timezone.utc).isoformat()
        
        template = self.templates[template_name]
        return self._format_message(template, variables, use_embed)
    
    def add_template(self, template: MessageTemplate) -> None:
        """Add a custom template."""
        self.templates[template.name] = template
        self.logger.info(f"Added custom template: {template.name}")
    
    def _extract_code_variables(self, code: ParsedCode, source_name: str = "") -> Dict[str, Any]:
        """Extract variables from a ParsedCode object."""
        
        # Format platforms
        platforms_str = self._format_platforms(code.platforms)
        
        # Format expiration info
        expiration_info = self._format_expiration_info(code)
        
        # Format reward
        reward_str = code.reward_type.title() if code.reward_type else "Unknown"
        
        # Format source
        if not source_name:
            source_name = f"Source {code.source_id}"
        
        return {
            "code": code.code_display,
            "reward": reward_str,
            "platforms": platforms_str,
            "expiration_info": expiration_info,
            "expiration_time": self._format_expiration_time(code.expires_at),
            "source": source_name,
            "confidence": f"{code.confidence_score:.1%}",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    def _format_platforms(self, platforms: List[str]) -> str:
        """Format platform list for display."""
        if not platforms or "all" in platforms:
            return "All Platforms"
        
        platform_names = {
            "pc": "PC",
            "xbox": "Xbox",
            "playstation": "PlayStation", 
            "nintendo": "Nintendo Switch"
        }
        
        formatted = [platform_names.get(p, p.title()) for p in platforms]
        
        if len(formatted) == 1:
            return formatted[0]
        elif len(formatted) == 2:
            return f"{formatted[0]} & {formatted[1]}"
        else:
            return ", ".join(formatted[:-1]) + f" & {formatted[-1]}"
    
    def _format_expiration_info(self, code: ParsedCode) -> str:
        """Format expiration information."""
        if not code.expires_at:
            return ""
        
        expiration_str = self._format_expiration_time(code.expires_at)
        estimated_str = " (estimated)" if code.metadata.is_expiration_estimated else ""
        
        return f"**Expires:** {expiration_str}{estimated_str}\n"
    
    def _format_expiration_time(self, expires_at: Optional[datetime]) -> str:
        """Format expiration time with timezone conversion."""
        if not expires_at:
            return "No expiration"
        
        # Ensure timezone awareness
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        
        # Format in UTC and local time
        utc_str = expires_at.strftime("%Y-%m-%d %H:%M UTC")
        
        # Convert to display timezone (simplified - would use pytz in practice)
        # For now, just show UTC
        return utc_str
    
    def _format_changes(self, changes: Dict[str, Any]) -> str:
        """Format changes for update notifications."""
        change_descriptions = []
        
        for change_type, change_data in changes.items():
            if change_type == "reward_type":
                old_reward = change_data["old"] or "Unknown"
                new_reward = change_data["new"] or "Unknown"
                change_descriptions.append(f"Reward: {old_reward} → {new_reward}")
            
            elif change_type == "platforms":
                old_platforms = self._format_platforms(change_data["old"])
                new_platforms = self._format_platforms(change_data["new"])
                change_descriptions.append(f"Platforms: {old_platforms} → {new_platforms}")
            
            elif change_type == "expiration":
                old_exp = self._format_expiration_time(change_data["old"])
                new_exp = self._format_expiration_time(change_data["new"])
                change_descriptions.append(f"Expiration: {old_exp} → {new_exp}")
            
            elif change_type == "confidence_improvement":
                improvement = change_data * 100
                change_descriptions.append(f"Confidence improved by {improvement:.1f}%")
        
        return "\n".join(change_descriptions) if change_descriptions else "Metadata updated"
    
    def _format_code_list(self, codes: List[ParsedCode], max_codes: int = 10) -> str:
        """Format a list of codes for summary display."""
        if not codes:
            return "No codes found"
        
        code_lines = []
        for i, code in enumerate(codes[:max_codes]):
            reward = code.reward_type.title() if code.reward_type else "Unknown"
            code_lines.append(f"• `{code.code_display}` - {reward}")
        
        if len(codes) > max_codes:
            remaining = len(codes) - max_codes
            code_lines.append(f"• ... and {remaining} more codes")
        
        return "\n".join(code_lines)
    
    def _format_message(self, template: MessageTemplate, variables: Dict[str, Any],
                       use_embed: bool) -> Dict[str, Any]:
        """Format a message using template and variables."""
        
        # Substitute variables in content
        content = Template(template.content_template).safe_substitute(variables)
        
        message = {
            "content": content,
            "username": "SHiFT Code Bot",
            "avatar_url": None  # Could be configured
        }
        
        # Add embed if requested and template has one
        if use_embed and template.embed_template:
            embed = self._format_embed(template.embed_template, variables)
            message["embeds"] = [embed]
        
        return message
    
    def _format_embed(self, embed_template: Dict[str, Any], 
                     variables: Dict[str, Any]) -> Dict[str, Any]:
        """Format an embed using template and variables."""
        
        embed = {}
        
        # Process each field in the embed template
        for key, value in embed_template.items():
            if isinstance(value, str):
                embed[key] = Template(value).safe_substitute(variables)
            elif isinstance(value, dict):
                embed[key] = self._format_embed(value, variables)
            elif isinstance(value, list):
                embed[key] = []
                for item in value:
                    if isinstance(item, dict):
                        formatted_item = {}
                        for item_key, item_value in item.items():
                            if isinstance(item_value, str):
                                formatted_item[item_key] = Template(item_value).safe_substitute(variables)
                            else:
                                formatted_item[item_key] = item_value
                        embed[key].append(formatted_item)
                    else:
                        embed[key].append(item)
            else:
                embed[key] = value
        
        return embed
    
    def validate_template(self, template: MessageTemplate) -> List[str]:
        """Validate a template and return any issues found."""
        issues = []
        
        # Check for required fields
        if not template.name:
            issues.append("Template name is required")
        
        if not template.content_template:
            issues.append("Content template is required")
        
        # Check for valid template syntax
        try:
            Template(template.content_template)
        except Exception as e:
            issues.append(f"Invalid content template syntax: {e}")
        
        # Validate embed template if present
        if template.embed_template:
            try:
                # Test with dummy variables
                test_vars = {"test": "value", "timestamp": "2024-01-01T00:00:00Z"}
                self._format_embed(template.embed_template, test_vars)
            except Exception as e:
                issues.append(f"Invalid embed template: {e}")
        
        return issues
    
    def get_available_variables(self) -> Dict[str, str]:
        """Get list of available variables for templates."""
        return {
            "code": "The shift code (e.g., ABCDE-12345-FGHIJ-67890-KLMNO)",
            "reward": "The reward type (e.g., Golden Key, Diamond Key)",
            "platforms": "Formatted platform list (e.g., PC & Xbox)",
            "expiration_info": "Formatted expiration information with label",
            "expiration_time": "Just the expiration time",
            "source": "Source name where code was found",
            "confidence": "Confidence score as percentage",
            "timestamp": "Current timestamp in ISO format",
            "changes": "Formatted list of changes (for updates)",
            "code_count": "Number of codes (for summaries)",
            "time_period": "Time period description (for summaries)",
            "code_list": "Formatted list of codes (for summaries)",
            "error_message": "Error description (for errors)"
        }