"""
Advanced expiration date parsing for shift codes.
"""

import re
import logging
from typing import Optional, Tuple, Dict, List
from datetime import datetime, timezone, timedelta
from dateutil import parser as date_parser
import calendar

logger = logging.getLogger(__name__)


class ExpirationParser:
    """Advanced parser for expiration dates with multiple format support."""
    
    # Comprehensive date patterns with their corresponding formats
    DATE_PATTERNS = [
        # Standard formats
        (r"expires?\s+(?:on\s+)?(\w+\s+\d{1,2},?\s+\d{4})", "month_day_year"),
        (r"expires?\s+(\d{4}-\d{2}-\d{2})", "iso_date"),
        (r"expires?\s+(\d{1,2}/\d{1,2}/\d{4})", "us_date"),
        (r"expires?\s+(\d{1,2}-\d{1,2}-\d{4})", "dash_date"),
        (r"expires?\s+(\d{1,2}\.\d{1,2}\.\d{4})", "dot_date"),
        
        # With time
        (r"expires?\s+(\w+\s+\d{1,2},?\s+\d{4}\s+(?:at\s+)?\d{1,2}:\d{2}(?::\d{2})?(?:\s*[AP]M)?)", "month_day_year_time"),
        (r"expires?\s+(\d{4}-\d{2}-\d{2}\s+\d{1,2}:\d{2}(?::\d{2})?)", "iso_datetime"),
        (r"expires?\s+(\d{1,2}/\d{1,2}/\d{4}\s+\d{1,2}:\d{2}(?::\d{2})?(?:\s*[AP]M)?)", "us_datetime"),
        
        # Timezone aware
        (r"expires?\s+(\w+\s+\d{1,2},?\s+\d{4}\s+\d{1,2}:\d{2}(?::\d{2})?\s+[A-Z]{3,4})", "month_day_year_tz"),
        (r"expires?\s+(\d{4}-\d{2}-\d{2}T\d{1,2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2}))", "iso_full"),
        
        # Relative dates
        (r"expires?\s+in\s+(\d+)\s+days?", "relative_days"),
        (r"expires?\s+in\s+(\d+)\s+hours?", "relative_hours"),
        (r"expires?\s+in\s+(\d+)\s+minutes?", "relative_minutes"),
        (r"expires?\s+in\s+(\d+)\s+weeks?", "relative_weeks"),
        
        # Alternative phrasings
        (r"(?:valid\s+)?until\s+(\w+\s+\d{1,2},?\s+\d{4})", "month_day_year"),
        (r"ends?\s+(?:on\s+)?(\w+\s+\d{1,2},?\s+\d{4})", "month_day_year"),
        (r"available\s+until\s+(\w+\s+\d{1,2},?\s+\d{4})", "month_day_year"),
        (r"good\s+until\s+(\w+\s+\d{1,2},?\s+\d{4})", "month_day_year"),
        
        # Specific time mentions
        (r"expires?\s+(?:at\s+)?midnight\s+(?:on\s+)?(\w+\s+\d{1,2},?\s+\d{4})", "month_day_year_midnight"),
        (r"expires?\s+(?:at\s+)?(\d{1,2}(?::\d{2})?(?:\s*[AP]M)?)\s+(?:on\s+)?(\w+\s+\d{1,2},?\s+\d{4})", "time_date"),
        
        # Fuzzy patterns
        (r"(\w+\s+\d{1,2},?\s+\d{4}).*?expir", "fuzzy_month_day_year"),
        (r"expir.*?(\w+\s+\d{1,2},?\s+\d{4})", "fuzzy_month_day_year_after"),
    ]
    
    # Month name mappings for different languages/formats
    MONTH_MAPPINGS = {
        # English full names
        "january": 1, "february": 2, "march": 3, "april": 4,
        "may": 5, "june": 6, "july": 7, "august": 8,
        "september": 9, "october": 10, "november": 11, "december": 12,
        
        # English abbreviations
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
        
        # Alternative abbreviations
        "sept": 9, "janu": 1, "febr": 2,
    }
    
    # Timezone mappings
    TIMEZONE_MAPPINGS = {
        "UTC": timezone.utc,
        "GMT": timezone.utc,
        "EST": timezone(timedelta(hours=-5)),
        "EDT": timezone(timedelta(hours=-4)),
        "CST": timezone(timedelta(hours=-6)),
        "CDT": timezone(timedelta(hours=-5)),
        "MST": timezone(timedelta(hours=-7)),
        "MDT": timezone(timedelta(hours=-6)),
        "PST": timezone(timedelta(hours=-8)),
        "PDT": timezone(timedelta(hours=-7)),
    }
    
    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        
        # Compile patterns for better performance
        self.compiled_patterns = [
            (re.compile(pattern, re.I), format_type)
            for pattern, format_type in self.DATE_PATTERNS
        ]
    
    def parse_expiration(self, text: str) -> Tuple[Optional[datetime], bool]:
        """
        Parse expiration date from text.
        
        Returns:
            Tuple of (datetime, is_estimated) where is_estimated indicates
            if the date was estimated/approximated rather than explicitly stated.
        """
        if not text:
            return None, False
        
        text_lower = text.lower()
        
        # Try each pattern in order of specificity
        for pattern, format_type in self.compiled_patterns:
            match = pattern.search(text_lower)
            if match:
                try:
                    result = self._parse_match(match, format_type, text_lower)
                    if result[0]:  # If we got a valid datetime
                        self.logger.debug(f"Parsed expiration: {result[0]} (format: {format_type})")
                        return result
                except Exception as e:
                    self.logger.debug(f"Failed to parse with format {format_type}: {e}")
                    continue
        
        # Fallback: try to find any date-like strings and parse with dateutil
        return self._fallback_parse(text_lower)
    
    def _parse_match(self, match: re.Match, format_type: str, text: str) -> Tuple[Optional[datetime], bool]:
        """Parse a regex match based on its format type."""
        
        if format_type == "relative_days":
            days = int(match.group(1))
            expires_at = datetime.now(timezone.utc) + timedelta(days=days)
            return expires_at, True
        
        elif format_type == "relative_hours":
            hours = int(match.group(1))
            expires_at = datetime.now(timezone.utc) + timedelta(hours=hours)
            return expires_at, True
        
        elif format_type == "relative_minutes":
            minutes = int(match.group(1))
            expires_at = datetime.now(timezone.utc) + timedelta(minutes=minutes)
            return expires_at, True
        
        elif format_type == "relative_weeks":
            weeks = int(match.group(1))
            expires_at = datetime.now(timezone.utc) + timedelta(weeks=weeks)
            return expires_at, True
        
        elif format_type == "iso_date":
            date_str = match.group(1)
            expires_at = datetime.strptime(date_str, "%Y-%m-%d")
            expires_at = expires_at.replace(tzinfo=timezone.utc, hour=23, minute=59, second=59)
            return expires_at, False
        
        elif format_type == "iso_datetime":
            date_str = match.group(1)
            expires_at = datetime.fromisoformat(date_str)
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            return expires_at, False
        
        elif format_type == "iso_full":
            date_str = match.group(1)
            expires_at = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            return expires_at, False
        
        elif format_type in ["us_date", "dash_date", "dot_date"]:
            date_str = match.group(1)
            separators = {'us_date': '/', 'dash_date': '-', 'dot_date': '.'}
            separator = separators[format_type]
            
            parts = date_str.split(separator)
            if len(parts) == 3:
                month, day, year = map(int, parts)
                expires_at = datetime(year, month, day, 23, 59, 59, tzinfo=timezone.utc)
                return expires_at, False
        
        elif format_type in ["us_datetime"]:
            date_str = match.group(1)
            # Try to parse with dateutil for flexibility
            expires_at = date_parser.parse(date_str)
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            return expires_at, False
        
        elif format_type in ["month_day_year", "fuzzy_month_day_year", "fuzzy_month_day_year_after"]:
            date_str = match.group(1)
            expires_at = self._parse_month_day_year(date_str)
            if expires_at:
                # Set to end of day if no time specified
                expires_at = expires_at.replace(hour=23, minute=59, second=59)
                return expires_at, False
        
        elif format_type == "month_day_year_time":
            date_str = match.group(1)
            expires_at = self._parse_month_day_year_time(date_str)
            if expires_at:
                return expires_at, False
        
        elif format_type == "month_day_year_tz":
            date_str = match.group(1)
            expires_at = self._parse_month_day_year_tz(date_str)
            if expires_at:
                return expires_at, False
        
        elif format_type == "month_day_year_midnight":
            date_str = match.group(1)
            expires_at = self._parse_month_day_year(date_str)
            if expires_at:
                # Set to midnight (start of next day)
                expires_at = expires_at.replace(hour=0, minute=0, second=0)
                expires_at += timedelta(days=1)
                return expires_at, False
        
        elif format_type == "time_date":
            time_str = match.group(1)
            date_str = match.group(2)
            expires_at = self._parse_time_date(time_str, date_str)
            if expires_at:
                return expires_at, False
        
        return None, False
    
    def _parse_month_day_year(self, date_str: str) -> Optional[datetime]:
        """Parse month day year format (e.g., 'January 15, 2024')."""
        try:
            # Clean up the string
            date_str = re.sub(r'[,\.]', '', date_str.strip())
            parts = date_str.split()
            
            if len(parts) >= 3:
                month_str = parts[0].lower()
                day = int(parts[1])
                year = int(parts[2])
                
                # Map month name to number
                month = self.MONTH_MAPPINGS.get(month_str)
                if month:
                    return datetime(year, month, day, tzinfo=timezone.utc)
        
        except Exception as e:
            self.logger.debug(f"Failed to parse month/day/year '{date_str}': {e}")
        
        return None
    
    def _parse_month_day_year_time(self, date_str: str) -> Optional[datetime]:
        """Parse month day year with time (e.g., 'January 15, 2024 at 11:59 PM')."""
        try:
            # Use dateutil parser for flexibility
            expires_at = date_parser.parse(date_str)
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            return expires_at
        
        except Exception as e:
            self.logger.debug(f"Failed to parse month/day/year with time '{date_str}': {e}")
        
        return None
    
    def _parse_month_day_year_tz(self, date_str: str) -> Optional[datetime]:
        """Parse month day year with timezone (e.g., 'January 15, 2024 11:59 PM EST')."""
        try:
            # Extract timezone
            tz_match = re.search(r'\b([A-Z]{3,4})\b$', date_str)
            if tz_match:
                tz_str = tz_match.group(1)
                date_without_tz = date_str[:tz_match.start()].strip()
                
                # Parse the date part
                expires_at = date_parser.parse(date_without_tz)
                
                # Apply timezone
                if tz_str in self.TIMEZONE_MAPPINGS:
                    tz = self.TIMEZONE_MAPPINGS[tz_str]
                    expires_at = expires_at.replace(tzinfo=tz)
                    # Convert to UTC
                    expires_at = expires_at.astimezone(timezone.utc)
                else:
                    # Unknown timezone, assume UTC
                    expires_at = expires_at.replace(tzinfo=timezone.utc)
                
                return expires_at
        
        except Exception as e:
            self.logger.debug(f"Failed to parse month/day/year with timezone '{date_str}': {e}")
        
        return None
    
    def _parse_time_date(self, time_str: str, date_str: str) -> Optional[datetime]:
        """Parse separate time and date strings."""
        try:
            # Parse date first
            date_dt = self._parse_month_day_year(date_str)
            if not date_dt:
                return None
            
            # Parse time
            time_match = re.match(r'(\d{1,2})(?::(\d{2}))?(?:\s*([AP]M))?', time_str.upper())
            if time_match:
                hour = int(time_match.group(1))
                minute = int(time_match.group(2)) if time_match.group(2) else 0
                ampm = time_match.group(3)
                
                # Handle AM/PM
                if ampm == 'PM' and hour != 12:
                    hour += 12
                elif ampm == 'AM' and hour == 12:
                    hour = 0
                
                # Combine date and time
                expires_at = date_dt.replace(hour=hour, minute=minute, second=0)
                return expires_at
        
        except Exception as e:
            self.logger.debug(f"Failed to parse time/date '{time_str}' '{date_str}': {e}")
        
        return None
    
    def _fallback_parse(self, text: str) -> Tuple[Optional[datetime], bool]:
        """Fallback parsing using dateutil for any date-like strings."""
        try:
            # Look for date-like patterns
            date_patterns = [
                r'\b\d{4}-\d{2}-\d{2}\b',
                r'\b\d{1,2}/\d{1,2}/\d{4}\b',
                r'\b\w+\s+\d{1,2},?\s+\d{4}\b'
            ]
            
            for pattern in date_patterns:
                matches = re.findall(pattern, text)
                for match in matches:
                    try:
                        expires_at = date_parser.parse(match)
                        if expires_at.tzinfo is None:
                            expires_at = expires_at.replace(tzinfo=timezone.utc)
                        
                        # Only return dates in the future
                        if expires_at > datetime.now(timezone.utc):
                            return expires_at, True  # Mark as estimated since it's fallback
                    
                    except Exception:
                        continue
        
        except Exception as e:
            self.logger.debug(f"Fallback parsing failed: {e}")
        
        return None, False
    
    def estimate_expiration(self, text: str, code_first_seen: datetime) -> Tuple[Optional[datetime], bool]:
        """
        Estimate expiration based on common patterns and code age.
        
        This is used when no explicit expiration is found but we want to
        provide a reasonable estimate based on historical patterns.
        """
        try:
            # Check for keywords that suggest duration
            if any(keyword in text.lower() for keyword in ["limited time", "temporary", "event"]):
                # Event codes typically last 1-2 weeks
                estimated = code_first_seen + timedelta(days=10)
                return estimated, True
            
            elif any(keyword in text.lower() for keyword in ["permanent", "forever", "always"]):
                # No expiration
                return None, False
            
            elif any(keyword in text.lower() for keyword in ["weekend", "week"]):
                # Weekend/weekly codes
                estimated = code_first_seen + timedelta(days=7)
                return estimated, True
            
            elif any(keyword in text.lower() for keyword in ["daily", "today"]):
                # Daily codes
                estimated = code_first_seen + timedelta(days=1)
                return estimated, True
            
            else:
                # Default: assume codes last about 30 days if no other info
                estimated = code_first_seen + timedelta(days=30)
                return estimated, True
        
        except Exception as e:
            self.logger.debug(f"Expiration estimation failed: {e}")
        
        return None, False
    
    def validate_expiration(self, expires_at: Optional[datetime]) -> bool:
        """Validate that an expiration date is reasonable."""
        if not expires_at:
            return True  # No expiration is valid
        
        now = datetime.now(timezone.utc)
        
        # Check if date is in the past (with small tolerance)
        if expires_at < now - timedelta(hours=1):
            return False
        
        # Check if date is too far in the future (more than 2 years)
        if expires_at > now + timedelta(days=730):
            return False
        
        return True