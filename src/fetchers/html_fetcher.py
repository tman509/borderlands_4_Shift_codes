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
from ..models.content import RawContent, ContentType

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
            raw_content = RawContent(
                url=url,
                content=response.text,
                content_type=ContentType.HTML,
                source_id=self.source_config.id,
                headers=dict(response.headers),
                content_hash=content_hash
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
            
            # Extract additional meta information
            meta_info = self._extract_meta_information(soup)
            
            # Update metadata with parsing results
            raw_content.metadata.update({
                'extracted_text_length': len(extracted_text),
                'potential_codes_found': len(potential_codes),
                'potential_codes_details': potential_codes,
                'parsing_strategies_used': getattr(self, '_last_strategies_used', []),
                'page_title': self._extract_page_title(soup),
                'last_modified': self._extract_last_modified(soup),
                'content_quality_score': self._calculate_content_quality(extracted_text, potential_codes),
                'meta_information': meta_info,
                'enhancement_success': True
            })
            
            # Replace content with enhanced text if we found high-confidence codes
            high_confidence_codes = [code for code in potential_codes if code['confidence'] > 0.7]
            if high_confidence_codes:
                raw_content.content = extracted_text
                raw_content.metadata['enhanced_content'] = True
                raw_content.metadata['high_confidence_codes'] = len(high_confidence_codes)
            
            return raw_content
            
        except Exception as e:
            self.logger.warning(f"Content enhancement failed for {raw_content.url}: {e}")
            raw_content.metadata.update({
                'enhancement_success': False,
                'enhancement_error': str(e),
                'error_type': type(e).__name__
            })
            return raw_content
    
    def _extract_text_with_strategies(self, soup: BeautifulSoup) -> str:
        """Extract text using multiple parsing strategies."""
        extracted_texts = []
        strategies_used = []
        
        # Strategy 1: Use configured selectors
        for selector in self.selectors:
            try:
                elements = soup.select(selector)
                for element in elements[:10]:  # Limit to first 10 matches
                    text = element.get_text(separator=' ', strip=True)
                    if text and len(text) > 10:  # Only meaningful text
                        extracted_texts.append(text)
                        strategies_used.append(f"selector:{selector}")
            except Exception as e:
                self.logger.debug(f"Selector '{selector}' failed: {e}")
                continue
        
        # Strategy 2: Look for specific shift code containers
        code_keywords = ['shift', 'code', 'key', 'reward', 'borderlands', 'gearbox']
        for keyword in code_keywords:
            try:
                code_containers = soup.find_all(
                    text=re.compile(keyword, re.I)
                )
                for container in code_containers[:3]:  # Limit results per keyword
                    if container.parent:
                        text = container.parent.get_text(separator=' ', strip=True)
                        if text and len(text) > 20:  # Ensure meaningful content
                            extracted_texts.append(text)
                            strategies_used.append(f"keyword:{keyword}")
            except Exception as e:
                self.logger.debug(f"Keyword search for '{keyword}' failed: {e}")
                continue
        
        # Strategy 3: Look for code-like patterns in attributes
        try:
            code_pattern_elements = soup.find_all(attrs={
                "class": re.compile(r'code|shift|key', re.I),
                "id": re.compile(r'code|shift|key', re.I)
            })
            for element in code_pattern_elements[:5]:
                text = element.get_text(separator=' ', strip=True)
                if text and len(text) > 10:
                    extracted_texts.append(text)
                    strategies_used.append("attribute_pattern")
        except Exception as e:
            self.logger.debug(f"Attribute pattern search failed: {e}")
        
        # Strategy 4: Look for structured data (JSON-LD, microdata)
        try:
            json_ld_scripts = soup.find_all('script', type='application/ld+json')
            for script in json_ld_scripts[:3]:
                if script.string:
                    extracted_texts.append(script.string)
                    strategies_used.append("json_ld")
        except Exception as e:
            self.logger.debug(f"JSON-LD extraction failed: {e}")
        
        # Strategy 5: Fallback to full page text if enabled and no other strategies worked
        if self.use_fallback_regex and not extracted_texts:
            try:
                # Remove script and style elements first
                for script in soup(["script", "style", "nav", "footer", "header"]):
                    script.decompose()
                
                full_text = soup.get_text(separator='\n', strip=True)
                if full_text:
                    extracted_texts.append(full_text)
                    strategies_used.append("fallback_full_text")
            except Exception as e:
                self.logger.debug(f"Fallback text extraction failed: {e}")
        
        # Store strategies used for debugging
        self._last_strategies_used = strategies_used
        
        # Combine and deduplicate while preserving order
        seen = set()
        unique_texts = []
        for text in extracted_texts:
            if text not in seen and len(text.strip()) > 10:
                seen.add(text)
                unique_texts.append(text)
        
        combined_text = '\n\n'.join(unique_texts)
        return combined_text
    
    def _find_potential_codes(self, text: str) -> List[Dict[str, Any]]:
        """Find potential shift codes in text with context."""
        potential_codes = []
        
        for pattern in self.code_patterns:
            for match in pattern.finditer(text):
                code = match.group(0)
                start_pos = match.start()
                end_pos = match.end()
                
                # Extract context around the code (100 chars before and after)
                context_start = max(0, start_pos - 100)
                context_end = min(len(text), end_pos + 100)
                context = text[context_start:context_end].strip()
                
                # Calculate confidence based on surrounding text
                confidence = self._calculate_code_confidence(code, context)
                
                potential_codes.append({
                    'code': code,
                    'context': context,
                    'confidence': confidence,
                    'position': {'start': start_pos, 'end': end_pos}
                })
        
        # Sort by confidence and remove duplicates
        seen_codes = set()
        unique_codes = []
        for code_info in sorted(potential_codes, key=lambda x: x['confidence'], reverse=True):
            if code_info['code'] not in seen_codes:
                seen_codes.add(code_info['code'])
                unique_codes.append(code_info)
        
        return unique_codes
    
    def _calculate_code_confidence(self, code: str, context: str) -> float:
        """Calculate confidence score for a potential code based on context."""
        confidence = 0.5  # Base confidence
        
        context_lower = context.lower()
        
        # Positive indicators
        positive_keywords = [
            'shift', 'code', 'key', 'reward', 'borderlands', 'gearbox',
            'golden', 'diamond', 'vault', 'expires', 'redeem', 'claim'
        ]
        
        for keyword in positive_keywords:
            if keyword in context_lower:
                confidence += 0.1
        
        # Negative indicators
        negative_keywords = [
            'example', 'test', 'sample', 'placeholder', 'fake', 'demo',
            'xxxxx', '00000', '11111', 'abcde'
        ]
        
        for keyword in negative_keywords:
            if keyword in context_lower:
                confidence -= 0.2
        
        # Code format validation
        if self._is_valid_code_format(code):
            confidence += 0.2
        else:
            confidence -= 0.3
        
        # Check for suspicious patterns
        if self._is_suspicious_code(code):
            confidence -= 0.4
        
        return max(0.1, min(1.0, confidence))
    
    def _is_valid_code_format(self, code: str) -> bool:
        """Check if code matches valid Shift Code format patterns."""
        # Remove any separators and check length
        clean_code = re.sub(r'[^A-Z0-9]', '', code.upper())
        
        # Valid lengths for Shift Codes
        valid_lengths = [16, 20, 25]  # 4x4, 4x5, 5x5
        
        if len(clean_code) not in valid_lengths:
            return False
        
        # Check for reasonable character distribution
        unique_chars = len(set(clean_code))
        if unique_chars < 3:  # Too few unique characters
            return False
        
        return True
    
    def _is_suspicious_code(self, code: str) -> bool:
        """Check if code appears to be a test or example code."""
        clean_code = re.sub(r'[^A-Z0-9]', '', code.upper())
        
        # Common test patterns
        test_patterns = [
            r'^X+$',  # All X's
            r'^0+$',  # All 0's
            r'^1+$',  # All 1's
            r'^(ABCDE|FGHIJ|KLMNO|PQRST|UVWXY)+$',  # Alphabetical
            r'^(12345|67890)+$',  # Sequential numbers
        ]
        
        for pattern in test_patterns:
            if re.match(pattern, clean_code):
                return True
        
        # Check for repeated segments
        if len(clean_code) >= 10:
            segment_length = len(clean_code) // 5
            segments = [clean_code[i:i+segment_length] for i in range(0, len(clean_code), segment_length)]
            if len(set(segments)) == 1:  # All segments are identical
                return True
        
        return False
    
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
    
    def _calculate_content_quality(self, text: str, potential_codes: List[Dict[str, Any]]) -> float:
        """Calculate overall content quality score."""
        if not text:
            return 0.0
        
        quality_score = 0.5  # Base score
        
        # Text length factor
        text_length = len(text.strip())
        if text_length > 100:
            quality_score += 0.1
        if text_length > 500:
            quality_score += 0.1
        
        # Code quality factor
        if potential_codes:
            avg_confidence = sum(code['confidence'] for code in potential_codes) / len(potential_codes)
            quality_score += avg_confidence * 0.3
        
        # Content relevance factor
        relevant_keywords = ['shift', 'code', 'borderlands', 'gearbox', 'key', 'reward']
        text_lower = text.lower()
        keyword_count = sum(1 for keyword in relevant_keywords if keyword in text_lower)
        quality_score += min(keyword_count * 0.05, 0.2)
        
        return min(1.0, quality_score)
    
    def _handle_parsing_error(self, error: Exception, url: str) -> RawContent:
        """Handle parsing errors gracefully."""
        self.logger.warning(f"Parsing error for {url}: {error}")
        
        # Return minimal content object with error information
        return RawContent(
            url=url,
            content="",
            content_type=ContentType.HTML,
            source_id=self.source_config.id,
            metadata={
                'parsing_error': str(error),
                'error_type': type(error).__name__,
                'content_quality_score': 0.0
            }
        )
    
    def _extract_meta_information(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Extract additional meta information from the page."""
        meta_info = {}
        
        # Extract Open Graph data
        og_tags = soup.find_all('meta', property=re.compile(r'^og:'))
        for tag in og_tags:
            property_name = tag.get('property', '').replace('og:', '')
            content = tag.get('content', '')
            if property_name and content:
                meta_info[f'og_{property_name}'] = content
        
        # Extract Twitter Card data
        twitter_tags = soup.find_all('meta', attrs={'name': re.compile(r'^twitter:')})
        for tag in twitter_tags:
            name = tag.get('name', '').replace('twitter:', '')
            content = tag.get('content', '')
            if name and content:
                meta_info[f'twitter_{name}'] = content
        
        # Extract canonical URL
        canonical = soup.find('link', rel='canonical')
        if canonical and canonical.get('href'):
            meta_info['canonical_url'] = canonical['href']
        
        # Extract language
        html_tag = soup.find('html')
        if html_tag and html_tag.get('lang'):
            meta_info['language'] = html_tag['lang']
        
        return meta_info