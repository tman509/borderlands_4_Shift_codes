"""
RSS/Atom feed fetcher with metadata extraction.
"""

import re
import logging
import xml.etree.ElementTree as ET
from typing import Iterator, List, Optional, Dict, Any
from datetime import datetime, timezone, timedelta
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

from .base import BaseFetcher
from models.content import RawContent

logger = logging.getLogger(__name__)


class RssFetcher(BaseFetcher):
    """Fetcher for RSS and Atom feeds."""
    
    def __init__(self, source_config):
        super().__init__(source_config)
        
        # Configuration from parser hints
        self.max_entries = self.source_config.parser_hints.get('max_entries', 25)
        self.include_content = self.source_config.parser_hints.get('include_content', True)
        self.follow_links = self.source_config.parser_hints.get('follow_links', False)
        self.cutoff_days = self.source_config.parser_hints.get('cutoff_days', 7)
        
        # Regex patterns for shift codes
        self.code_patterns = [
            re.compile(r'\b[A-Z0-9]{5}(?:-[A-Z0-9]{5}){4}\b', re.I),  # 5x5 format
            re.compile(r'\b[A-Z0-9]{4}(?:-[A-Z0-9]{4}){3,4}\b', re.I)  # 4x4 format
        ]
        
        # Common RSS/Atom namespaces
        self.namespaces = {
            'atom': 'http://www.w3.org/2005/Atom',
            'content': 'http://purl.org/rss/1.0/modules/content/',
            'dc': 'http://purl.org/dc/elements/1.1/',
            'media': 'http://search.yahoo.com/mrss/'
        }
    
    def fetch(self) -> Iterator[RawContent]:
        """Fetch content from RSS/Atom feed."""
        try:
            self.logger.info(f"Fetching RSS feed from: {self.source_config.url}")
            
            # Fetch the feed
            response = self._make_request(self.source_config.url)
            
            # Check if content has changed
            content_hash = self.get_source_hash(response.text)
            if self.should_skip_fetch(content_hash):
                self.logger.debug(f"Feed content unchanged for {self.source_config.url}, skipping")
                return
            
            # Parse the feed
            feed_entries = self._parse_feed(response.text)
            
            # Process each entry
            for entry in feed_entries:
                try:
                    raw_content = self._create_entry_content(entry)
                    if raw_content:
                        yield raw_content
                        
                        # Optionally follow entry links for full content
                        if self.follow_links and entry.get('link'):
                            yield from self._fetch_entry_link(entry['link'], entry)
                            
                except Exception as e:
                    self.logger.warning(f"Failed to process feed entry: {e}")
                    continue
                    
        except Exception as e:
            self.logger.error(f"RSS fetch failed for {self.source_config.url}: {e}")
            raise
    
    def _parse_feed(self, feed_content: str) -> List[Dict[str, Any]]:
        """Parse RSS or Atom feed content."""
        try:
            # Try to parse as XML
            root = ET.fromstring(feed_content)
            
            # Detect feed type
            if root.tag == 'rss' or root.find('.//item') is not None:
                return self._parse_rss_feed(root)
            elif root.tag.endswith('feed') or root.find('.//{http://www.w3.org/2005/Atom}entry') is not None:
                return self._parse_atom_feed(root)
            else:
                self.logger.warning("Unknown feed format")
                return []
                
        except ET.ParseError as e:
            self.logger.error(f"Failed to parse feed XML: {e}")
            return []
    
    def _parse_rss_feed(self, root: ET.Element) -> List[Dict[str, Any]]:
        """Parse RSS 2.0 feed."""
        entries = []
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=self.cutoff_days)
        
        for item in root.findall('.//item')[:self.max_entries]:
            try:
                entry = {
                    'title': self._get_element_text(item, 'title'),
                    'link': self._get_element_text(item, 'link'),
                    'description': self._get_element_text(item, 'description'),
                    'pub_date': self._parse_rss_date(self._get_element_text(item, 'pubDate')),
                    'guid': self._get_element_text(item, 'guid'),
                    'category': self._get_element_text(item, 'category'),
                    'author': self._get_element_text(item, 'author')
                }
                
                # Get content if available
                content_elem = item.find('.//content:encoded', self.namespaces)
                if content_elem is not None:
                    entry['content'] = content_elem.text
                
                # Check if entry is within cutoff date
                if entry['pub_date'] and entry['pub_date'] < cutoff_date:
                    continue
                
                # Only include entries that might contain codes
                if self._entry_might_contain_codes(entry):
                    entries.append(entry)
                    
            except Exception as e:
                self.logger.debug(f"Failed to parse RSS item: {e}")
                continue
        
        return entries
    
    def _parse_atom_feed(self, root: ET.Element) -> List[Dict[str, Any]]:
        """Parse Atom feed."""
        entries = []
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=self.cutoff_days)
        
        # Handle namespace
        atom_ns = {'atom': 'http://www.w3.org/2005/Atom'}
        
        for entry_elem in root.findall('.//atom:entry', atom_ns)[:self.max_entries]:
            try:
                entry = {
                    'title': self._get_element_text(entry_elem, 'atom:title', atom_ns),
                    'link': self._get_atom_link(entry_elem, atom_ns),
                    'summary': self._get_element_text(entry_elem, 'atom:summary', atom_ns),
                    'content': self._get_atom_content(entry_elem, atom_ns),
                    'pub_date': self._parse_atom_date(
                        self._get_element_text(entry_elem, 'atom:published', atom_ns) or
                        self._get_element_text(entry_elem, 'atom:updated', atom_ns)
                    ),
                    'id': self._get_element_text(entry_elem, 'atom:id', atom_ns),
                    'author': self._get_atom_author(entry_elem, atom_ns)
                }
                
                # Check if entry is within cutoff date
                if entry['pub_date'] and entry['pub_date'] < cutoff_date:
                    continue
                
                # Only include entries that might contain codes
                if self._entry_might_contain_codes(entry):
                    entries.append(entry)
                    
            except Exception as e:
                self.logger.debug(f"Failed to parse Atom entry: {e}")
                continue
        
        return entries
    
    def _entry_might_contain_codes(self, entry: Dict[str, Any]) -> bool:
        """Check if entry might contain shift codes."""
        # Check title and description for code-related keywords
        text_to_check = ' '.join(filter(None, [
            entry.get('title', ''),
            entry.get('description', ''),
            entry.get('summary', ''),
            entry.get('content', '')[:500]  # First 500 chars of content
        ])).lower()
        
        # Keywords that suggest shift codes
        code_keywords = [
            'shift', 'code', 'key', 'golden', 'diamond', 'vault',
            'borderlands', 'bl3', 'bl2', 'reward', 'redeem'
        ]
        
        # Check for keywords or actual code patterns
        has_keywords = any(keyword in text_to_check for keyword in code_keywords)
        has_code_pattern = any(pattern.search(text_to_check) for pattern in self.code_patterns)
        
        return has_keywords or has_code_pattern
    
    def _create_entry_content(self, entry: Dict[str, Any]) -> Optional[RawContent]:
        """Create RawContent from feed entry."""
        try:
            # Combine all text content
            content_parts = []
            
            if entry.get('title'):
                content_parts.append(f"Title: {entry['title']}")
            
            if entry.get('description'):
                content_parts.append(f"Description: {entry['description']}")
            
            if entry.get('summary'):
                content_parts.append(f"Summary: {entry['summary']}")
            
            if entry.get('content') and self.include_content:
                # Clean HTML from content
                clean_content = self._clean_html(entry['content'])
                content_parts.append(f"Content: {clean_content}")
            
            combined_content = '\n\n'.join(content_parts)
            
            # Create raw content object
            raw_content = self._create_raw_content(
                url=entry.get('link', self.source_config.url),
                content=combined_content,
                content_type='application/rss+xml'
            )
            
            # Add feed-specific metadata
            raw_content.metadata.update({
                'feed_entry': True,
                'entry_title': entry.get('title'),
                'entry_id': entry.get('guid') or entry.get('id'),
                'pub_date': entry.get('pub_date').isoformat() if entry.get('pub_date') else None,
                'author': entry.get('author'),
                'category': entry.get('category'),
                'has_full_content': bool(entry.get('content'))
            })
            
            return raw_content
            
        except Exception as e:
            self.logger.error(f"Failed to create content from entry: {e}")
            return None
    
    def _fetch_entry_link(self, link: str, entry: Dict[str, Any]) -> Iterator[RawContent]:
        """Fetch full content from entry link."""
        try:
            self.logger.debug(f"Following entry link: {link}")
            
            response = self._make_request(link)
            
            # Parse HTML content
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract main content
            content_selectors = [
                'article', '.article', '.post', '.entry',
                '.content', '.main-content', 'main'
            ]
            
            extracted_content = ""
            for selector in content_selectors:
                elements = soup.select(selector)
                if elements:
                    extracted_content = elements[0].get_text(separator='\n', strip=True)
                    break
            
            if not extracted_content:
                extracted_content = soup.get_text(separator='\n', strip=True)
            
            # Create raw content
            raw_content = self._create_raw_content(
                url=link,
                content=extracted_content,
                content_type='text/html'
            )
            
            # Add metadata indicating this came from a feed link
            raw_content.metadata.update({
                'from_feed_link': True,
                'original_feed_url': self.source_config.url,
                'feed_entry_title': entry.get('title'),
                'feed_entry_id': entry.get('guid') or entry.get('id')
            })
            
            yield raw_content
            
        except Exception as e:
            self.logger.warning(f"Failed to fetch entry link {link}: {e}")
    
    def _get_element_text(self, parent: ET.Element, tag: str, 
                         namespaces: Optional[Dict[str, str]] = None) -> Optional[str]:
        """Get text content of XML element."""
        element = parent.find(tag, namespaces or {})
        return element.text if element is not None else None
    
    def _get_atom_link(self, entry: ET.Element, namespaces: Dict[str, str]) -> Optional[str]:
        """Get link from Atom entry."""
        link_elem = entry.find('atom:link[@rel="alternate"]', namespaces)
        if link_elem is None:
            link_elem = entry.find('atom:link', namespaces)
        
        return link_elem.get('href') if link_elem is not None else None
    
    def _get_atom_content(self, entry: ET.Element, namespaces: Dict[str, str]) -> Optional[str]:
        """Get content from Atom entry."""
        content_elem = entry.find('atom:content', namespaces)
        return content_elem.text if content_elem is not None else None
    
    def _get_atom_author(self, entry: ET.Element, namespaces: Dict[str, str]) -> Optional[str]:
        """Get author from Atom entry."""
        author_elem = entry.find('atom:author/atom:name', namespaces)
        return author_elem.text if author_elem is not None else None
    
    def _parse_rss_date(self, date_str: Optional[str]) -> Optional[datetime]:
        """Parse RSS date format."""
        if not date_str:
            return None
        
        # Common RSS date formats
        formats = [
            '%a, %d %b %Y %H:%M:%S %z',  # RFC 2822
            '%a, %d %b %Y %H:%M:%S GMT',
            '%d %b %Y %H:%M:%S %z',
            '%Y-%m-%d %H:%M:%S'
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        
        self.logger.debug(f"Could not parse RSS date: {date_str}")
        return None
    
    def _parse_atom_date(self, date_str: Optional[str]) -> Optional[datetime]:
        """Parse Atom date format (ISO 8601)."""
        if not date_str:
            return None
        
        try:
            # Handle various ISO 8601 formats
            if date_str.endswith('Z'):
                date_str = date_str[:-1] + '+00:00'
            
            return datetime.fromisoformat(date_str)
        except ValueError:
            self.logger.debug(f"Could not parse Atom date: {date_str}")
            return None
    
    def _clean_html(self, html_content: str) -> str:
        """Clean HTML content to plain text."""
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            return soup.get_text(separator=' ', strip=True)
        except Exception:
            # Fallback: simple HTML tag removal
            return re.sub(r'<[^>]+>', '', html_content)
    
    def _extract_pagination_urls(self, content: str, base_url: str) -> List[str]:
        """Extract pagination URLs from feed (usually not applicable)."""
        # RSS feeds typically don't have pagination in the traditional sense
        # But some feeds might have "next" links
        try:
            root = ET.fromstring(content)
            
            # Look for Atom pagination links
            atom_ns = {'atom': 'http://www.w3.org/2005/Atom'}
            next_links = root.findall('.//atom:link[@rel="next"]', atom_ns)
            
            urls = []
            for link in next_links:
                href = link.get('href')
                if href:
                    urls.append(urljoin(base_url, href))
            
            return urls
            
        except Exception as e:
            self.logger.debug(f"Could not extract pagination from feed: {e}")
            return []