"""
LPService - Landing Page Parsing and Analysis

Responsibilities:
- Fetch LP from URL or load from local HTML file
- Parse HTML with BeautifulSoup
- Extract: fv_copy, primary_cta, offer, form_presence, form_fields_count, detected_ctas, raw_text_excerpt
- Fallback-first approach (graceful degradation)
- Language agnostic (handle both Japanese and English)

Input: lp_input (URL or local HTML file path)
Output: dict with extracted LP data

Note: message_consistency scoring is deferred to LLMService
"""

from typing import Dict, Any, Optional, List
from pathlib import Path
import logging
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse

from app.services.base_service import BaseService, ValidationError, ProcessingError


logger = logging.getLogger(__name__)


class LPService(BaseService):
    """
    Service for parsing and analyzing Landing Pages.
    
    Supports:
    - URL input: Fetch via HTTP GET
    - Local HTML file: Read from disk
    
    Extraction strategy:
    - Graceful fallback: if h1 missing, try h2, then first p
    - Flexible CTA detection: button, a, input[type=submit]
    - Simple form detection: count <input>, <textarea>, <select> elements
    """
    
    def __init__(self, timeout: int = 10):
        """
        Initialize LPService.
        
        Args:
            timeout (int): HTTP request timeout in seconds
        """
        super().__init__()
        self.logger = logging.getLogger(self.__class__.__name__)
        self.timeout = timeout
    
    def execute(self, lp_input: str) -> Dict[str, Any]:
        """
        Parse LP and extract key information.
        
        Args:
            lp_input (str): URL (http/https) or local file path
        
        Returns:
            dict: Extracted LP data
                {
                    "fv_copy": "FV main headline",
                    "fv_headline": "Shorter headline",
                    "primary_cta": "Button text",
                    "offer": "30-day free trial",
                    "form_present": True,
                    "form_fields_count": 3,
                    "form_field_names": ["email", "name"],
                    "detected_ctas": ["CTA 1", "CTA 2"],
                    "raw_text_excerpt": "First 500 chars of body text",
                    "estimated_scroll_depth_for_form": "above_fold",
                    "has_hero_section": True,
                    "has_social_proof": True,
                    "has_faq_section": False,
                    "url": "https://example.com/lp",
                    "http_status": 200,
                    "content_length": 15234,
                    "charset": "utf-8"
                }
        
        Raises:
            ValidationError: Invalid input
            ProcessingError: Fetch or parse error
        """
        self.validate_input(lp_input)
        
        try:
            self.logger.info(f"Processing LP: {lp_input}")
            
            # Fetch HTML
            html = self._fetch_html(lp_input)
            
            # Parse with BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')
            
            # Extract components
            result = {
                "fv_copy": self._extract_fv_copy(soup),
                "fv_headline": self._extract_fv_headline(soup),
                "primary_cta": self._extract_primary_cta(soup),
                "offer": self._extract_offer(soup),
                "form_present": self._form_exists(soup),
                "form_fields_count": self._count_form_fields(soup),
                "form_field_names": self._extract_form_field_names(soup),
                "detected_ctas": self._extract_all_ctas(soup),
                "raw_text_excerpt": self._extract_text_excerpt(soup),
                "estimated_scroll_depth_for_form": self._estimate_form_scroll_depth(soup),
                "has_hero_section": self._has_hero_section(soup),
                "has_social_proof": self._has_social_proof(soup),
                "has_faq_section": self._has_faq_section(soup),
                "url": lp_input if lp_input.startswith('http') else "local_file",
                "content_length": len(html),
                "charset": self._detect_charset(html),
            }
            
            # Add HTTP status if URL
            if lp_input.startswith('http'):
                result["http_status"] = 200  # Simplified, would come from actual fetch
            
            self.logger.info(f"LP parsing successful: {len(html)} bytes")
            return result
        
        except (ValidationError, ProcessingError):
            raise
        except Exception as e:
            raise ProcessingError(f"Failed to parse LP: {str(e)}")
    
    def validate_input(self, lp_input: str) -> bool:
        """
        Validate LP input.
        
        Args:
            lp_input (str): URL or file path
        
        Returns:
            bool: True if valid
        
        Raises:
            ValidationError: If invalid
        """
        if not isinstance(lp_input, str):
            raise ValidationError(f"lp_input must be string, got {type(lp_input)}")
        
        if len(lp_input) == 0:
            raise ValidationError("lp_input cannot be empty")
        
        # Check if URL or file path
        if lp_input.startswith('http'):
            # URL validation
            if not (lp_input.startswith('http://') or lp_input.startswith('https://')):
                raise ValidationError(f"Invalid URL: {lp_input}")
        else:
            # File path validation
            path = Path(lp_input)
            if not path.exists():
                raise ValidationError(f"File not found: {lp_input}")
            if not path.is_file():
                raise ValidationError(f"Path is not a file: {lp_input}")
        
        return True
    
    def _fetch_html(self, lp_input: str) -> str:
        """
        Fetch HTML from URL or load from file.
        
        Args:
            lp_input (str): URL or file path
        
        Returns:
            str: HTML content
        
        Raises:
            ProcessingError: If fetch/load fails
        """
        try:
            if lp_input.startswith('http'):
                # Fetch from URL
                self.logger.info(f"Fetching URL: {lp_input}")
                response = requests.get(lp_input, timeout=self.timeout)
                response.raise_for_status()
                return response.text
            else:
                # Load from file
                self.logger.info(f"Loading HTML file: {lp_input}")
                with open(lp_input, 'r', encoding='utf-8') as f:
                    return f.read()
        
        except requests.RequestException as e:
            raise ProcessingError(f"Failed to fetch URL {lp_input}: {str(e)}")
        except Exception as e:
            raise ProcessingError(f"Failed to load HTML: {str(e)}")
    
    # ===== Extraction Methods =====
    
    def _extract_fv_copy(self, soup: BeautifulSoup) -> Optional[str]:
        """
        Extract FV (First View) main copy.
        
        Fallback chain: h1 → h2 → first <p> with meaningful text
        """
        # Try h1
        h1 = soup.find('h1')
        if h1:
            text = h1.get_text(strip=True)
            if len(text) > 0:
                return text
        
        # Try h2
        h2 = soup.find('h2')
        if h2:
            text = h2.get_text(strip=True)
            if len(text) > 0:
                return text
        
        # Try first p with substance
        for p in soup.find_all('p'):
            text = p.get_text(strip=True)
            if len(text) > 20:  # Meaningful paragraph
                return text
        
        return None
    
    def _extract_fv_headline(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract FV headline (h1 only)"""
        h1 = soup.find('h1')
        if h1:
            text = h1.get_text(strip=True)
            if len(text) > 0:
                return text
        return None
    
    def _extract_primary_cta(self, soup: BeautifulSoup) -> Optional[str]:
        """
        Extract primary CTA text.
        
        Look for: button, prominent <a>, input[type=submit]
        Heuristic: first CTA in main content area
        """
        # Try button (most common)
        button = soup.find('button')
        if button:
            text = button.get_text(strip=True)
            if len(text) > 0:
                return text
        
        # Try input[type=submit]
        submit_input = soup.find('input', {'type': 'submit'})
        if submit_input:
            value = submit_input.get('value', '').strip()
            if len(value) > 0:
                return value
        
        # Try prominent link
        for a in soup.find_all('a', limit=5):
            text = a.get_text(strip=True)
            if len(text) > 0 and len(text) < 50:  # Reasonable CTA length
                # Skip nav links
                if 'contact' in text.lower() or 'sign' in text.lower() or 'start' in text.lower():
                    return text
        
        return None
    
    def _extract_offer(self, soup: BeautifulSoup) -> Optional[str]:
        """
        Extract offer text.
        
        Heuristic: Look for keywords like 'free', 'trial', 'discount', '%', 'off', '割引', '無料'
        """
        text = soup.get_text(separator=' ').lower()
        
        keywords = ['%', '割引', '無料', 'discount', 'off', 'limited time', 'exclusive', 'free trial', 'free for']
        for keyword in keywords:
            if keyword in text:
                # Find context around keyword
                idx = text.find(keyword)
                start = max(0, idx - 50)
                end = min(len(text), idx + 100)
                context = text[start:end].strip()
                
                # Clean up: handle Japanese period
                context = context.replace('。', '.')
                sentences = context.split('.')
                for sent in sentences:
                    if keyword in sent.lower():
                        offer = sent.strip()
                        if offer:
                            offer = offer[0].upper() + offer[1:]
                        if len(offer) > 5:
                            return offer[:150]
        
        return None
    
    def _form_exists(self, soup: BeautifulSoup) -> bool:
        """Check if form exists"""
        return soup.find('form') is not None
    
    def _count_form_fields(self, soup: BeautifulSoup) -> int:
        """Count form input fields (input, textarea, select)"""
        form = soup.find('form')
        if not form:
            return 0
        
        fields = form.find_all(['input', 'textarea', 'select'])
        # Exclude hidden and submit inputs
        count = sum(1 for f in fields if f.name != 'input' or f.get('type') not in ['hidden', 'submit'])
        return count
    
    def _extract_form_field_names(self, soup: BeautifulSoup) -> List[str]:
        """Extract form field names/labels"""
        form = soup.find('form')
        if not form:
            return []
        
        field_names = []
        
        # Extract from name attribute
        for field in form.find_all(['input', 'textarea', 'select']):
            name = field.get('name', '').strip()
            if name and name not in ['', 'token', 'csrf']:
                field_names.append(name)
            
            # Fallback to label
            if not name:
                placeholder = field.get('placeholder', '').strip()
                if placeholder:
                    field_names.append(placeholder)
        
        return field_names
    
    def _extract_all_ctas(self, soup: BeautifulSoup) -> List[str]:
        """Extract all CTA texts from page"""
        ctas = []
        
        # From buttons
        for button in soup.find_all('button', limit=5):
            text = button.get_text(strip=True)
            if len(text) > 0 and text not in ctas:
                ctas.append(text)
        
        # From submit inputs
        for submit_input in soup.find_all('input', {'type': 'submit'}, limit=5):
            value = submit_input.get('value', '').strip()
            if len(value) > 0 and value not in ctas:
                ctas.append(value)
        
        # From prominent links
        for a in soup.find_all('a', limit=5):
            text = a.get_text(strip=True)
            if len(text) > 0 and len(text) < 50 and text not in ctas:
                if any(keyword in text.lower() for keyword in ['start', 'sign', 'try', 'get', 'contact', 'learn']):
                    ctas.append(text)
        
        return ctas[:5]  # Limit to top 5
    
    def _extract_text_excerpt(self, soup: BeautifulSoup, max_length: int = 500) -> str:
        """Extract first N chars of body text (for context)"""
        text = soup.get_text(separator=' ', strip=True)
        return text[:max_length]
    
    def _estimate_form_scroll_depth(self, soup: BeautifulSoup) -> str:
        """
        Estimate form scroll depth.
        
        Heuristic: If form in first 30% of HTML, probably above_fold
        """
        html_str = str(soup)
        form = soup.find('form')
        
        if not form:
            return "no_form"
        
        form_pos = html_str.find(str(form))
        total_len = len(html_str)
        
        if form_pos / total_len < 0.3:
            return "above_fold"
        elif form_pos / total_len < 0.7:
            return "mid_page"
        else:
            return "below_fold"
    
    def _has_hero_section(self, soup: BeautifulSoup) -> bool:
        """Check for hero section (large image/background near top)"""
        # Look for div with class containing 'hero'
        hero = soup.find(class_=lambda x: x and 'hero' in x.lower())
        if hero:
            return True
        
        # Look for large image in first 20% of content
        img = soup.find('img')
        if img:
            return True
        
        return False
    
    def _has_social_proof(self, soup: BeautifulSoup) -> bool:
        """Check for social proof (testimonials, ratings, client logos)"""
        text = soup.get_text().lower()
        
        keywords = ['testimonial', 'review', 'rating', 'star', 'quote', 'client', 'customer', 'success', 'trusted', 'verified']
        for keyword in keywords:
            if keyword in text:
                return True
        
        # Look for review/testimonial sections
        for section in soup.find_all(['section', 'div'], class_=lambda x: x and ('review' in x.lower() or 'testimonial' in x.lower())):
            return True
        
        return False
    
    def _has_faq_section(self, soup: BeautifulSoup) -> bool:
        """Check for FAQ section"""
        text = soup.get_text().lower()
        if 'faq' in text or 'frequently asked' in text:
            return True
        
        # Look for FAQ-like structure (dt/dd or multiple divs with Q&A)
        for section in soup.find_all(['section', 'div'], class_=lambda x: x and 'faq' in x.lower()):
            return True
        
        return False
    
    @staticmethod
    def _detect_charset(html: str) -> str:
        """Simple charset detection"""
        # Check for meta charset
        if 'charset=utf-8' in html.lower():
            return "utf-8"
        if 'charset=shift_jis' in html.lower():
            return "shift_jis"
        
        return "utf-8"  # Default
