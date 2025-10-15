"""
Source fetchers for the Shift Code Bot.
"""

from .base import BaseFetcher, CircuitBreaker
from .html_fetcher import HtmlFetcher
from .rss_fetcher import RssFetcher
from .reddit_fetcher import RedditFetcher

__all__ = [
    "BaseFetcher",
    "CircuitBreaker",
    "HtmlFetcher",
    "RssFetcher",
    "RedditFetcher",
]