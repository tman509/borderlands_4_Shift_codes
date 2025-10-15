"""
HTML fetcher with improved parsing and fallback strategies.
"""

import re
import logging
from typing import Iterator, List, Optional, Dict, Any
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup, Tag

from .base import BaseFetcher
from ..models.content import RawContent

logger = logging.getLogger(__name__)


class HtmlFetcher(BaseFetcher):
    """Fetcher for HTML web pages with multiple parsing strategies."""
    
    def __init__(self, source_config):
        super().__init__(source_config)
        
        # Default selectors for common shift code patterns
        self.default_selectors = [
            '.tweet-text',
            '.content',
            '.post-content',
            '.entry-content',
            '.article-content',
            'article',
            'main',
            '.main-content',
            'p',
            'div'
        ]
        
        # Get selectors from parser hints
        self.selectors = self.source_config.parser_hints.get('selectors', self.default_selectors)
        self.use_fallback_regex = self.source_config.parser_hints.get('fallback_regex', True)
        self.max_pages = self.source_config.parser_hints.get('max_pages', 3)
        
        # Regex patterns for shift codes
        self.code_patterns = [
            re.compile(r'\b[A-Z0-9]{5}(?:-[A-Z0-9]{5}){4}\b', re.I),  # 5x5 format
            re.compile(r'\b[A-Z0-9]{4}(?:-[A-Z0-9]{4}){3,4}\b', re.I)  # 4x4 format
        ]
    
    def fetch(self) -> Iterator[RawContent]:
        """Fetch content from HTML source with pagination support."""
        try:
            self.logger.info(f"Fetching HTML from: {self.source_config.url}")
            
            # Fetch main page
            yield from self._fetch_page(self.source_config.url)
            
            # Handle pagination if enabled
            if self.source_config.parser_hints.get('enable_pagination', False):
                yield from self._fetch_paginated_content()
                
        except Exception as e:
            self.logger.error(f"HTML fetch failed for {self.source_config.url}: {e}")
            raise
    
    def _fetch_page(self, url: str) -> Iterator[RawContent]:
        """Fetch a single HTML page."""
        try:
            response = self._make_request(url)
            
            # Check if content has changed
            content_hash = self.get_source_hash(response.text)
            if self.should_skip_fetch(content_hash):
                self.logger.debug(f"Content unchanged for {url}, skipping")
                return
            
            # Create raw content object
            raw_content = self._create_raw_content(
                url=url,
                content=response.text,
                content_type=response.headers.get('content-type', 'text/html'),
                headers=dict(response.headers)
            )
            
            # Parse and enhance content
            enhanced_content = self._enhance_content(raw_content)
            yield enhanced_content
            
        except requests.RequestException as e:
            self.logger.error(f"Failed to fetch {url}: {e}")
            raise
    
    def _enhance_content(self, raw_content: RawContent) -> RawContent:
        """Enhance raw content with parsed information."""
        try:
            soup = BeautifulSoup(raw_content.content, 'html.parser')
            
            # Extract text using multiple strategies
            extracted_text = self._extract_text_with_strategies(soup)
            
            # Find potential shift codes
            potential_codes = self._find_potential_codes(extracted_text)
            
            # Update metadata with parsing results
            raw_content.metadata.update({
                'extracted_text_length': len(extracted_text),
                'potential_codes_found': len(potential_codes),
                'parsing_strategies_used': self._get_strategies_used(soup),
                'page_title': self._extract_page_title(soup),
                'last_modified': self._extract_last_modified(soup)
            })
            
            # Replace content with enhanced text if we found codes
            if potential_codes:
                raw_content.content = extracted_text
                raw_content.metadata['enhanced_content'] = True
            
            return raw_content
            
        except Exception as e:
            self.logger.warning(f"Content enhancement failed: {e}")
            return raw_content
    
    def _extract_text_with_strategies(self, soup: BeautifulSoup) -> str:
        """Extract text using multiple parsing strategies."""
        extracted_texts = []
        
        # Strategy 1: Use configured selectors
        for selector in self.selectors:
            try:
                elements = soup.select(selector)
                for element in elements[:10]:  # Limit to first 10 matches
                    text = element.get_text(separator=' ', strip=True)
                    if text and len(text) > 10:  # Only meaningful text
                        extracted_texts.append(text)
            except Exception as e:
                self.logger.debug(f"Selector '{selector}' failed: {e}")
                continue
        
        # Strategy 2: Look for specific shift code containers
        code_containers = soup.find_all(
            text=re.compile(r'shift|code|key|reward', re.I)
        )
        for container in code_containers[:5]:  # Limit results
            if container.parent:
                text = container.parent.get_text(separator=' ', strip=True)
                if text:
                    extracted_texts.append(text)
        
        # Strategy 3: Fallback to full page text if enabled
        if self.use_fallback_regex and not extracted_texts:
            full_text = soup.get_text(separator='\n', strip=True)
            extracted_texts.append(full_text)
        
        # Combine and deduplicate
        combined_text = '\n\n'.join(set(extracted_texts))
        return combined_text
    
    def _find_potential_codes(self, text: str) -> List[str]:
        """Find potential shift codes in text."""
        potential_codes = set()
        
        for pattern in self.code_patterns:
            matches = pattern.findall(text)
            potential_codes.update(matches)
        
        return list(potential_codes)
    
    def _get_strategies_used(self, soup: BeautifulSoup) -> List[str]:
        """Get list of parsing strategies that found content."""
        strategies = []
        
        for selector in self.selectors:
            try:
                if soup.select(selector):
                    strategies.append(f"selector:{selector}")
            except:
                continue
        
        return strategies
    
    def _extract_page_title(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract page title."""
        title_tag = soup.find('title')
        return title_tag.get_text(strip=True) if title_tag else None
    
    def _extract_last_modified(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract last modified date from meta tags."""
        # Look for common last-modified meta tags
        meta_tags = [
            'last-modified',
            'article:modified_time',
            'article:published_time',
            'date'
        ]
        
        for tag_name in meta_tags:
            meta_tag = soup.find('meta', {'name': tag_name}) or soup.find('meta', {'property': tag_name})
            if meta_tag and meta_tag.get('content'):
                return meta_tag['content']
        
        return None
    
    def _fetch_paginated_content(self) -> Iterator[RawContent]:
        """Fetch paginated content if pagination is detected."""
        try:
            # First, fetch the main page to detect pagination
            response = self._make_request(self.source_config.url)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find pagination URLs
            pagination_urls = self._extract_pagination_urls(response.text, self.source_config.url)
            
            page_count = 0
            for url in pagination_urls:
                if page_count >= self.max_pages:
                    break
                
                try:
                    yield from self._fetch_page(url)
                    page_count += 1
                except Exception as e:
                    self.logger.warning(f"Failed to fetch paginated page {url}: {e}")
                    continue
                    
        except Exception as e:
            self.logger.error(f"Pagination fetch failed: {e}")
    
    def _extract_pagination_urls(self, content: str, base_url: str) -> List[str]:
        """Extract pagination URLs from HTML content."""
        soup = BeautifulSoup(content, 'html.parser')
        pagination_urls = []
        
        # Common pagination selectors
        pagination_selectors = [
            'a[href*="page"]',
            'a[href*="p="]',
            '.pagination a',
            '.pager a',
            '.page-numbers a',
            'a[rel="next"]'
        ]
        
        for selector in pagination_selectors:
            try:
                links = soup.select(selector)
                for link in links[:self.max_pages]:  # Limit pagination
                    href = link.get('href')
                    if href:
                        # Convert relative URLs to absolute
                        full_url = urljoin(base_url, href)
                        if full_url not in pagination_urls and full_url != base_url:
                            pagination_urls.append(full_url)
            except Exception as e:
                self.logger.debug(f"Pagination selector '{selector}' failed: {e}")
                continue
        
        return pagination_urls
    
    def _should_continue_pagination(self, page_num: int, content: str) -> bool:
        """Determine if pagination should continue based on content."""
        # Stop if we've reached max pages
        if page_num >= self.max_pages:
            return False
        
        # Stop if no potential codes found on this page
        potential_codes = self._find_potential_codes(content)
        if not potential_codes:
            return False
        
        return True
    
    def _extract_context_around_codes(self, soup: BeautifulSoup, code: str) -> str:
        """Extract context around a specific code for better metadata extraction."""
        # Find text nodes containing the code
        code_elements = soup.find_all(text=re.compile(re.escape(code), re.I))
        
        contexts = []
        for element in code_elements[:3]:  # Limit to first 3 occurrences
            if element.parent:
                # Get parent element text
                parent_text = element.parent.get_text(separator=' ', strip=True)
                
                # Get surrounding siblings
                siblings = []
                if element.parent.parent:
                    for sibling in element.parent.parent.find_all(recursive=False):
                        if isinstance(sibling, Tag):
                            sibling_text = sibling.get_text(separator=' ', strip=True)
                            if sibling_text and len(sibling_text) < 500:  # Reasonable length
                                siblings.append(sibling_text)
                
                context = f"{parent_text}\n" + "\n".join(siblings[:3])
                contexts.append(context)
        
        return "\n\n".join(contexts) if contexts else ""