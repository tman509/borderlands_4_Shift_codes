"""
Base fetcher interface and common functionality.
"""

import hashlib
import logging
import time
import requests
from abc import ABC, abstractmethod
from typing import Iterator, Optional, Dict, Any
from datetime import datetime, timezone
from urllib.robotparser import RobotFileParser
from urllib.parse import urljoin, urlparse

from models.content import RawContent
from models.config import SourceConfig
from utils.retry import retry_with_backoff

logger = logging.getLogger(__name__)


class CircuitBreaker:
    """Simple circuit breaker implementation for fetcher resilience."""
    
    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = 0
        self.state = "closed"  # closed, open, half-open
    
    def call(self, func, *args, **kwargs):
        """Execute function with circuit breaker protection."""
        if self.state == "open":
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = "half-open"
            else:
                raise Exception("Circuit breaker is open")
        
        try:
            result = func(*args, **kwargs)
            if self.state == "half-open":
                self.reset()
            return result
        except Exception as e:
            self.record_failure()
            raise
    
    def record_failure(self):
        """Record a failure and potentially open the circuit."""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.failure_threshold:
            self.state = "open"
            logger.warning(f"Circuit breaker opened after {self.failure_count} failures")
    
    def reset(self):
        """Reset the circuit breaker."""
        self.failure_count = 0
        self.state = "closed"
        logger.info("Circuit breaker reset")


class BaseFetcher(ABC):
    """Base class for all source fetchers."""
    
    def __init__(self, source_config: SourceConfig):
        self.source_config = source_config
        self.name = f"{source_config.type.value}_{source_config.id}"
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        
        # Rate limiting
        self._last_request_time = 0.0
        self._request_count = 0
        self._request_window_start = time.time()
        
        # Circuit breaker for resilience
        self.circuit_breaker = CircuitBreaker()
        
        # HTTP session for connection pooling
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'ShiftCodeBot/2.0 (+https://github.com/your-repo/shift-code-bot)'
        })
        
        # Robots.txt cache
        self._robots_cache: Dict[str, RobotFileParser] = {}
    
    @abstractmethod
    def fetch(self) -> Iterator[RawContent]:
        """Fetch content from the source."""
        pass
    
    def get_source_hash(self, content: str) -> str:
        """Generate hash for content change detection."""
        return hashlib.sha256(content.encode('utf-8')).hexdigest()
    
    def should_skip_fetch(self, content_hash: str) -> bool:
        """Check if fetch should be skipped based on content hash."""
        if not self.source_config.last_content_hash:
            return False
        
        return self.source_config.last_content_hash == content_hash
    
    def can_fetch_url(self, url: str) -> bool:
        """Check if URL can be fetched according to robots.txt."""
        try:
            parsed_url = urlparse(url)
            base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
            
            if base_url not in self._robots_cache:
                robots_url = urljoin(base_url, '/robots.txt')
                rp = RobotFileParser()
                rp.set_url(robots_url)
                
                try:
                    rp.read()
                    self._robots_cache[base_url] = rp
                except Exception as e:
                    self.logger.debug(f"Could not read robots.txt for {base_url}: {e}")
                    # If we can't read robots.txt, assume we can fetch
                    return True
            
            rp = self._robots_cache[base_url]
            user_agent = self.session.headers.get('User-Agent', '*')
            return rp.can_fetch(user_agent, url)
            
        except Exception as e:
            self.logger.debug(f"Error checking robots.txt for {url}: {e}")
            return True  # Default to allowing fetch if check fails
    
    def _enforce_rate_limit(self) -> None:
        """Enforce rate limiting between requests."""
        current_time = time.time()
        
        # Reset request count if we're in a new window
        if current_time - self._request_window_start >= 60:  # 1 minute window
            self._request_count = 0
            self._request_window_start = current_time
        
        # Check requests per minute limit
        if self._request_count >= self.source_config.rate_limit.requests_per_minute:
            sleep_time = 60 - (current_time - self._request_window_start)
            if sleep_time > 0:
                self.logger.debug(f"Rate limit reached, sleeping for {sleep_time:.2f}s")
                time.sleep(sleep_time)
                self._request_count = 0
                self._request_window_start = time.time()
        
        # Enforce delay between requests
        if self.source_config.rate_limit.delay_between_requests > 0:
            time_since_last = current_time - self._last_request_time
            required_delay = self.source_config.rate_limit.delay_between_requests
            
            if time_since_last < required_delay:
                sleep_time = required_delay - time_since_last
                self.logger.debug(f"Enforcing delay: sleeping for {sleep_time:.2f}s")
                time.sleep(sleep_time)
        
        self._last_request_time = time.time()
        self._request_count += 1
    
    @retry_with_backoff(max_attempts=3, initial_delay=1.0, exceptions=(requests.RequestException,))
    def _make_request(self, url: str, **kwargs) -> requests.Response:
        """Make HTTP request with retry logic and circuit breaker."""
        def _request():
            self._enforce_rate_limit()
            
            # Check robots.txt
            if not self.can_fetch_url(url):
                raise requests.RequestException(f"Robots.txt disallows fetching {url}")
            
            # Set default timeout if not provided
            if 'timeout' not in kwargs:
                kwargs['timeout'] = 30
            
            response = self.session.get(url, **kwargs)
            response.raise_for_status()
            return response
        
        return self.circuit_breaker.call(_request)
    
    def _create_raw_content(self, url: str, content: str, content_type: str = "text/html", 
                           headers: Optional[Dict[str, str]] = None) -> RawContent:
        """Create RawContent object with metadata."""
        content_hash = self.get_source_hash(content)
        
        return RawContent(
            url=url,
            content=content,
            content_type=content_type,
            source_id=self.source_config.id,
            fetch_timestamp=datetime.now(timezone.utc).isoformat(),
            content_hash=content_hash,
            headers=headers or {},
            metadata={
                "source_name": self.source_config.name,
                "source_type": self.source_config.type.value,
                "fetcher_name": self.name,
                "content_length": len(content),
                "circuit_breaker_state": self.circuit_breaker.state
            }
        )
    
    def _extract_pagination_urls(self, content: str, base_url: str) -> list[str]:
        """Extract pagination URLs from content. Override in subclasses."""
        return []
    
    def _should_continue_pagination(self, page_num: int, content: str) -> bool:
        """Determine if pagination should continue. Override in subclasses."""
        max_pages = self.source_config.parser_hints.get('max_pages', 5)
        return page_num < max_pages
    
    def health_check(self) -> Dict[str, Any]:
        """Perform health check for this fetcher."""
        health_info = {
            "fetcher_name": self.name,
            "source_id": self.source_config.id,
            "source_name": self.source_config.name,
            "enabled": self.source_config.enabled,
            "circuit_breaker_state": self.circuit_breaker.state,
            "failure_count": self.circuit_breaker.failure_count,
            "last_request_time": self._last_request_time,
            "request_count_current_window": self._request_count
        }
        
        # Test basic connectivity if enabled
        if self.source_config.enabled:
            try:
                # Simple HEAD request to test connectivity
                response = self.session.head(
                    self.source_config.url, 
                    timeout=10,
                    allow_redirects=True
                )
                health_info["connectivity"] = "ok"
                health_info["last_status_code"] = response.status_code
            except Exception as e:
                health_info["connectivity"] = "failed"
                health_info["connectivity_error"] = str(e)
        else:
            health_info["connectivity"] = "disabled"
        
        return health_info
    
    def cleanup(self):
        """Clean up resources."""
        if hasattr(self, 'session'):
            self.session.close()
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.cleanup()