"""
Reddit fetcher with enhanced error handling and pagination support.
"""

import logging
import time
from typing import Iterator, List, Optional, Dict, Any
from datetime import datetime, timezone, timedelta

from .base import BaseFetcher
from models.content import RawContent, ContentType
from utils.retry import retry_with_backoff

logger = logging.getLogger(__name__)

# Optional Reddit import with graceful fallback
try:
    import praw
    from prawcore.exceptions import (
        PrawcoreException, ResponseException, RequestException,
        ServerError, TooManyRequests, Forbidden, NotFound
    )
    PRAW_AVAILABLE = True
except ImportError:
    praw = None
    PrawcoreException = Exception
    ResponseException = Exception
    RequestException = Exception
    ServerError = Exception
    TooManyRequests = Exception
    Forbidden = Exception
    NotFound = Exception
    PRAW_AVAILABLE = False


class RedditFetcher(BaseFetcher):
    """Fetcher for Reddit content with enhanced error handling."""
    
    def __init__(self, source_config):
        super().__init__(source_config)
        
        # Check if Reddit integration is available
        if not PRAW_AVAILABLE:
            self.logger.error("PRAW library not available. Install with: pip install praw")
            self.enabled = False
            return
        
        # Configuration from parser hints
        self.subreddit_name = self.source_config.parser_hints.get('subreddit', 'borderlands3')
        self.post_limit = self.source_config.parser_hints.get('post_limit', 25)
        self.include_comments = self.source_config.parser_hints.get('include_comments', True)
        self.comment_limit = self.source_config.parser_hints.get('comment_limit', 10)
        self.cutoff_days = self.source_config.parser_hints.get('cutoff_days', 7)
        self.sort_method = self.source_config.parser_hints.get('sort_method', 'new')  # new, hot, top
        self.max_retries = self.source_config.parser_hints.get('max_retries', 3)
        self.retry_delay = self.source_config.parser_hints.get('retry_delay', 5)
        
        # Error tracking
        self.consecutive_errors = 0
        self.last_error_time = None
        self.error_threshold = 5
        
        # Initialize Reddit client
        self.reddit = None
        self.enabled = False
        self._initialize_reddit_client()
    
    def _initialize_reddit_client(self) -> None:
        """Initialize Reddit client with credentials from environment."""
        import os
        
        try:
            client_id = os.getenv('REDDIT_CLIENT_ID')
            client_secret = os.getenv('REDDIT_CLIENT_SECRET')
            user_agent = os.getenv('REDDIT_USER_AGENT', 'ShiftCodeBot/2.0')
            
            if not client_id or not client_secret:
                self.logger.warning("Reddit credentials not found in environment variables")
                return
            
            self.reddit = praw.Reddit(
                client_id=client_id,
                client_secret=client_secret,
                user_agent=user_agent,
                ratelimit_seconds=300  # 5 minute cooldown on rate limit
            )
            
            # Test the connection
            self.reddit.user.me()
            self.enabled = True
            self.logger.info(f"Reddit client initialized successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize Reddit client: {e}")
            self.enabled = False
    
    def fetch(self) -> Iterator[RawContent]:
        """Fetch content from Reddit subreddit with enhanced error handling."""
        if not self.enabled:
            self.logger.warning("Reddit fetcher is disabled")
            return
        
        try:
            self.logger.info(f"Fetching from r/{self.subreddit_name}")
            
            # Reset error count on successful start
            self.consecutive_errors = 0
            
            # Get subreddit with retry
            subreddit = self._get_subreddit_with_retry()
            if not subreddit:
                return
            
            # Fetch posts based on sort method
            posts = self._get_posts_with_retry(subreddit)
            if not posts:
                return
            
            posts_processed = 0
            posts_skipped = 0
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=self.cutoff_days)
            
            for post in posts:
                try:
                    # Check if post is within cutoff date
                    post_date = datetime.fromtimestamp(post.created_utc, tz=timezone.utc)
                    if post_date < cutoff_date:
                        self.logger.debug(f"Post {post.id} is older than cutoff, skipping")
                        posts_skipped += 1
                        continue
                    
                    # Process the post with retry
                    raw_content = self._process_post_with_retry(post)
                    if raw_content:
                        yield raw_content
                        posts_processed += 1
                    
                    # Enforce rate limiting
                    self._enforce_rate_limit()
                    
                except Exception as e:
                    self._handle_post_error(post, e)
                    continue
            
            self.logger.info(f"Processed {posts_processed} posts, skipped {posts_skipped} from r/{self.subreddit_name}")
            
        except TooManyRequests as e:
            self._handle_rate_limit_error(e)
        except (Forbidden, NotFound) as e:
            self._handle_access_error(e)
        except PrawcoreException as e:
            self._handle_api_error(e)
        except Exception as e:
            self._handle_general_error(e)
    
    def _get_posts(self, subreddit):
        """Get posts from subreddit based on sort method."""
        try:
            if self.sort_method == 'new':
                return subreddit.new(limit=self.post_limit)
            elif self.sort_method == 'hot':
                return subreddit.hot(limit=self.post_limit)
            elif self.sort_method == 'top':
                # Get top posts from the last week
                return subreddit.top(time_filter='week', limit=self.post_limit)
            else:
                self.logger.warning(f"Unknown sort method: {self.sort_method}, using 'new'")
                return subreddit.new(limit=self.post_limit)
                
        except Exception as e:
            self.logger.error(f"Failed to get posts with sort method '{self.sort_method}': {e}")
            # Fallback to new posts
            return subreddit.new(limit=self.post_limit)
    
    def _process_post(self, post) -> Optional[RawContent]:
        """Process a single Reddit post."""
        try:
            # Build content from post
            content_parts = [
                f"Title: {post.title}",
                f"Author: u/{post.author.name if post.author else '[deleted]'}",
                f"Score: {post.score}",
                f"Created: {datetime.fromtimestamp(post.created_utc, tz=timezone.utc).isoformat()}"
            ]
            
            # Add post text if available
            if hasattr(post, 'selftext') and post.selftext:
                content_parts.append(f"Text: {post.selftext}")
            
            # Add URL if it's a link post
            if post.url and not post.is_self:
                content_parts.append(f"URL: {post.url}")
            
            # Add comments if enabled
            if self.include_comments:
                comments_text = self._extract_comments(post)
                if comments_text:
                    content_parts.append(f"Comments:\n{comments_text}")
            
            combined_content = '\n\n'.join(content_parts)
            
            # Only process if content might contain codes
            if not self._might_contain_codes(combined_content):
                return None
            
            # Create raw content object with Reddit-specific metadata
            reddit_metadata = {
                'reddit_post': True,
                'post_id': post.id,
                'subreddit': self.subreddit_name,
                'author': post.author.name if post.author else '[deleted]',
                'score': post.score,
                'num_comments': post.num_comments,
                'created_utc': post.created_utc,
                'is_self_post': post.is_self,
                'post_flair': post.link_flair_text,
                'is_stickied': post.stickied,
                'upvote_ratio': getattr(post, 'upvote_ratio', None),
                'post_url': post.url if not post.is_self else None,
                'permalink': post.permalink
            }
            
            raw_content = self._create_raw_content_reddit(
                url=f"https://reddit.com{post.permalink}",
                content=combined_content,
                metadata=reddit_metadata
            )
            
            return raw_content
            
        except Exception as e:
            self.logger.error(f"Failed to process post {post.id}: {e}")
            return None
    
    def _extract_comments(self, post) -> str:
        """Extract comments from Reddit post."""
        try:
            # Expand comment tree
            post.comments.replace_more(limit=0)
            
            comments = []
            comment_count = 0
            
            for comment in post.comments.list():
                if comment_count >= self.comment_limit:
                    break
                
                try:
                    # Skip deleted comments
                    if not hasattr(comment, 'body') or comment.body in ['[deleted]', '[removed]']:
                        continue
                    
                    # Only include comments that might contain codes
                    if self._might_contain_codes(comment.body):
                        comment_text = (
                            f"u/{comment.author.name if comment.author else '[deleted]'} "
                            f"(Score: {comment.score}): {comment.body}"
                        )
                        comments.append(comment_text)
                        comment_count += 1
                
                except Exception as e:
                    self.logger.debug(f"Failed to process comment: {e}")
                    continue
            
            return '\n\n'.join(comments)
            
        except Exception as e:
            self.logger.warning(f"Failed to extract comments from post {post.id}: {e}")
            return ""
    
    def _might_contain_codes(self, text: str) -> bool:
        """Check if text might contain shift codes."""
        if not text:
            return False
        
        text_lower = text.lower()
        
        # Keywords that suggest shift codes
        code_keywords = [
            'shift', 'code', 'key', 'golden', 'diamond', 'vault',
            'borderlands', 'bl3', 'bl2', 'reward', 'redeem', 'gearbox'
        ]
        
        # Check for keywords
        has_keywords = any(keyword in text_lower for keyword in code_keywords)
        
        # Check for code-like patterns
        import re
        code_patterns = [
            re.compile(r'\b[A-Z0-9]{5}(?:-[A-Z0-9]{5}){4}\b', re.I),  # 5x5 format
            re.compile(r'\b[A-Z0-9]{4}(?:-[A-Z0-9]{4}){3,4}\b', re.I)  # 4x4 format
        ]
        
        has_code_pattern = any(pattern.search(text) for pattern in code_patterns)
        
        return has_keywords or has_code_pattern
    
    def _search_subreddit(self, query: str, time_filter: str = 'week') -> Iterator[RawContent]:
        """Search subreddit for specific terms."""
        try:
            subreddit = self.reddit.subreddit(self.subreddit_name)
            
            # Search for posts
            search_results = subreddit.search(
                query=query,
                sort='new',
                time_filter=time_filter,
                limit=self.post_limit
            )
            
            for post in search_results:
                raw_content = self._process_post(post)
                if raw_content:
                    yield raw_content
                    
        except Exception as e:
            self.logger.error(f"Reddit search failed for query '{query}': {e}")
    
    def search_for_codes(self) -> Iterator[RawContent]:
        """Search specifically for shift code related posts."""
        search_queries = [
            'shift code',
            'golden key',
            'diamond key',
            'vault card',
            'borderlands code'
        ]
        
        for query in search_queries:
            try:
                yield from self._search_subreddit(query)
                # Add delay between searches
                time.sleep(1)
            except Exception as e:
                self.logger.warning(f"Search failed for '{query}': {e}")
                continue
    
    def get_user_posts(self, username: str) -> Iterator[RawContent]:
        """Get posts from a specific user (e.g., official accounts)."""
        try:
            user = self.reddit.redditor(username)
            
            for post in user.submissions.new(limit=self.post_limit):
                # Only process posts in relevant subreddits
                if post.subreddit.display_name.lower() in ['borderlands3', 'borderlands', 'gearbox']:
                    raw_content = self._process_post(post)
                    if raw_content:
                        yield raw_content
                        
        except Exception as e:
            self.logger.error(f"Failed to get posts from user {username}: {e}")
    
    def health_check(self) -> Dict[str, Any]:
        """Perform comprehensive health check for Reddit fetcher."""
        health_info = super().health_check()
        
        health_info.update({
            'praw_available': PRAW_AVAILABLE,
            'reddit_client_initialized': self.enabled,
            'subreddit': self.subreddit_name,
            'consecutive_errors': self.consecutive_errors,
            'last_error_time': self.last_error_time.isoformat() if self.last_error_time else None,
            'error_threshold': self.error_threshold
        })
        
        if self.enabled and self.reddit:
            try:
                # Test API access
                subreddit = self.reddit.subreddit(self.subreddit_name)
                subreddit_info = {
                    'display_name': subreddit.display_name,
                    'subscribers': getattr(subreddit, 'subscribers', 'unknown'),
                    'over18': getattr(subreddit, 'over18', False)
                }
                
                health_info['api_access'] = 'ok'
                health_info['subreddit_info'] = subreddit_info
                
                # Test recent posts access
                try:
                    recent_posts = list(subreddit.new(limit=1))
                    health_info['recent_posts_access'] = 'ok'
                    health_info['has_recent_posts'] = len(recent_posts) > 0
                except Exception as e:
                    health_info['recent_posts_access'] = 'failed'
                    health_info['recent_posts_error'] = str(e)
                
            except Exception as e:
                health_info['api_access'] = 'failed'
                health_info['api_error'] = str(e)
        else:
            health_info['api_access'] = 'disabled'
        
        return health_info
    
    @retry_with_backoff(max_attempts=3, initial_delay=2.0, exceptions=(PrawcoreException,))
    def _get_subreddit_with_retry(self):
        """Get subreddit with retry logic."""
        try:
            subreddit = self.reddit.subreddit(self.subreddit_name)
            # Test access by getting display name
            _ = subreddit.display_name
            return subreddit
        except Exception as e:
            self.logger.error(f"Failed to access subreddit r/{self.subreddit_name}: {e}")
            raise
    
    @retry_with_backoff(max_attempts=3, initial_delay=1.0, exceptions=(PrawcoreException,))
    def _get_posts_with_retry(self, subreddit):
        """Get posts with retry logic."""
        try:
            return self._get_posts(subreddit)
        except Exception as e:
            self.logger.error(f"Failed to get posts from r/{self.subreddit_name}: {e}")
            raise
    
    def _process_post_with_retry(self, post) -> Optional[RawContent]:
        """Process post with retry logic."""
        max_attempts = 2  # Fewer retries for individual posts
        
        for attempt in range(max_attempts):
            try:
                return self._process_post(post)
            except Exception as e:
                if attempt == max_attempts - 1:
                    self.logger.warning(f"Failed to process post {post.id} after {max_attempts} attempts: {e}")
                    return None
                else:
                    self.logger.debug(f"Retrying post {post.id} processing (attempt {attempt + 1})")
                    time.sleep(1)
        
        return None
    
    def _handle_post_error(self, post, error: Exception) -> None:
        """Handle individual post processing errors."""
        self.consecutive_errors += 1
        self.last_error_time = datetime.now(timezone.utc)
        
        error_type = type(error).__name__
        self.logger.warning(f"Post processing error for {post.id} ({error_type}): {error}")
        
        # If too many consecutive errors, consider disabling temporarily
        if self.consecutive_errors >= self.error_threshold:
            self.logger.error(f"Too many consecutive errors ({self.consecutive_errors}), may need attention")
    
    def _handle_rate_limit_error(self, error: Exception) -> None:
        """Handle Reddit rate limit errors."""
        self.logger.warning(f"Reddit rate limit exceeded: {error}")
        
        # Extract wait time if available
        wait_time = getattr(error, 'seconds_to_reset', 60)
        self.logger.info(f"Waiting {wait_time} seconds for rate limit reset")
        time.sleep(wait_time)
    
    def _handle_access_error(self, error: Exception) -> None:
        """Handle access-related errors (403, 404)."""
        error_type = type(error).__name__
        
        if isinstance(error, Forbidden):
            self.logger.error(f"Access forbidden to r/{self.subreddit_name}: {error}")
            self.enabled = False  # Disable until configuration is fixed
        elif isinstance(error, NotFound):
            self.logger.error(f"Subreddit r/{self.subreddit_name} not found: {error}")
            self.enabled = False  # Disable until configuration is fixed
        else:
            self.logger.error(f"Access error ({error_type}): {error}")
    
    def _handle_api_error(self, error: Exception) -> None:
        """Handle general Reddit API errors."""
        self.consecutive_errors += 1
        self.last_error_time = datetime.now(timezone.utc)
        
        error_type = type(error).__name__
        self.logger.error(f"Reddit API error ({error_type}): {error}")
        
        # For server errors, wait before retrying
        if isinstance(error, ServerError):
            self.logger.info("Server error detected, waiting before retry")
            time.sleep(self.retry_delay)
    
    def _handle_general_error(self, error: Exception) -> None:
        """Handle general errors."""
        self.consecutive_errors += 1
        self.last_error_time = datetime.now(timezone.utc)
        
        error_type = type(error).__name__
        self.logger.error(f"Reddit fetch failed ({error_type}): {error}")
        
        # If too many errors, temporarily disable
        if self.consecutive_errors >= self.error_threshold:
            self.logger.error("Too many consecutive errors, temporarily disabling Reddit fetcher")
            self.enabled = False
    
    def _create_raw_content_reddit(self, url: str, content: str, metadata: Dict[str, Any]) -> RawContent:
        """Create RawContent object specifically for Reddit content."""
        content_hash = self.get_source_hash(content)
        
        return RawContent(
            url=url,
            content=content,
            content_type=ContentType.TEXT,
            source_id=self.source_config.id,
            headers={},
            content_hash=content_hash,
            metadata={
                **metadata,
                "source_name": self.source_config.name,
                "source_type": "reddit",
                "fetcher_name": self.name,
                "content_length": len(content),
                "subreddit": self.subreddit_name
            }
        )
    
    def get_subreddit_info(self) -> Dict[str, Any]:
        """Get information about the configured subreddit."""
        if not self.enabled:
            return {"error": "Reddit fetcher disabled"}
        
        try:
            subreddit = self.reddit.subreddit(self.subreddit_name)
            
            return {
                "name": subreddit.display_name,
                "title": subreddit.title,
                "description": subreddit.public_description,
                "subscribers": subreddit.subscribers,
                "created_utc": subreddit.created_utc,
                "over18": subreddit.over18,
                "subreddit_type": subreddit.subreddit_type
            }
        except Exception as e:
            return {"error": f"Failed to get subreddit info: {e}"}
    
    def get_recent_activity_summary(self) -> Dict[str, Any]:
        """Get summary of recent activity in the subreddit."""
        if not self.enabled:
            return {"error": "Reddit fetcher disabled"}
        
        try:
            subreddit = self.reddit.subreddit(self.subreddit_name)
            
            # Get recent posts
            recent_posts = list(subreddit.new(limit=10))
            
            # Analyze for shift code related content
            code_related_posts = 0
            total_posts = len(recent_posts)
            
            for post in recent_posts:
                post_text = f"{post.title} {getattr(post, 'selftext', '')}"
                if self._might_contain_codes(post_text):
                    code_related_posts += 1
            
            return {
                "total_recent_posts": total_posts,
                "code_related_posts": code_related_posts,
                "code_relevance_ratio": code_related_posts / total_posts if total_posts > 0 else 0,
                "last_post_time": recent_posts[0].created_utc if recent_posts else None
            }
        except Exception as e:
            return {"error": f"Failed to get activity summary: {e}"}
    
    def cleanup(self):
        """Clean up Reddit client resources."""
        super().cleanup()
        # PRAW doesn't require explicit cleanup, but we can reset the client
        self.reddit = None