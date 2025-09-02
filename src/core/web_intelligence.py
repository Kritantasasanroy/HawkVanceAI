"""
Web Intelligence Module
Provides web content extraction and analysis for HawkVance AI
"""

import logging
from typing import Dict, Optional, List
import time

class WebContentIntelligence:
    """Web content extraction and intelligence system"""
    
    def __init__(self):
        self.selenium_available = False
        self.beautifulsoup_available = False
        
        # Check for selenium
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            self.selenium_available = True
            logging.info("Selenium webdriver available")
        except ImportError:
            logging.warning("Selenium not available - install for full web intelligence")
            
        # Check for beautifulsoup
        try:
            from bs4 import BeautifulSoup
            import requests
            self.beautifulsoup_available = True
            logging.info("BeautifulSoup available")
        except ImportError:
            logging.warning("BeautifulSoup not available - install for web parsing")
            
        logging.info("Web intelligence module initialized")
        
    def extract_webpage_content(self, url: str) -> Dict:
        """Extract full webpage content"""
        try:
            if self.beautifulsoup_available:
                import requests
                from bs4 import BeautifulSoup
                
                response = requests.get(url, timeout=10)
                soup = BeautifulSoup(response.content, 'html.parser')
                
                return {
                    'url': url,
                    'title': soup.title.string if soup.title else 'No title',
                    'text_content': soup.get_text()[:2000] + '...',  # Limit content
                    'links': [a.get('href') for a in soup.find_all('a', href=True)][:10],
                    'images': [img.get('src') for img in soup.find_all('img', src=True)][:5],
                    'timestamp': time.time(),
                    'success': True
                }
            else:
                return {
                    'url': url,
                    'error': 'BeautifulSoup not available',
                    'success': False
                }
                
        except Exception as e:
            logging.error(f"Web content extraction failed: {e}")
            return {
                'url': url,
                'error': str(e),
                'success': False
            }
            
    def extract_current_browser_content(self) -> Dict:
        """Extract content from currently active browser using OCR and smart detection"""
        try:
            import pyautogui
            import re
            
            # Take screenshot to analyze
            screenshot = pyautogui.screenshot()
            
            # Try to extract text using OCR if available
            try:
                from .ocr import OCRProcessor
                from config.settings import TESSERACT_PATH
                import numpy as np
                
                ocr = OCRProcessor(TESSERACT_PATH)
                # Convert PIL image to numpy array for OCR
                screenshot_np = np.array(screenshot)
                text_content = ocr.extract_text(screenshot_np)
            except:
                # Fallback without OCR
                text_content = "OCR not available for text extraction"
            
            # Detect URLs in the text
            url_pattern = r'https?://[^\s<>"\[\]{}|\\^`]+'
            urls = re.findall(url_pattern, text_content)
            
            # Detect if this looks like web content
            web_indicators = ['http', 'www', '.com', '.org', '.net', 'Search', 'Home', 'About', 'Contact']
            is_web_content = any(indicator.lower() in text_content.lower() for indicator in web_indicators)
            
            result = {
                'content_type': 'web_browser' if is_web_content else 'unknown',
                'text_content': text_content,
                'urls_found': urls,
                'word_count': len(text_content.split()) if text_content else 0,
                'is_web_content': is_web_content,
                'timestamp': time.time(),
                'success': True,
                'method': 'screen_ocr_analysis'
            }
            
            # If we found URLs, try to get more info about the first one
            if urls:
                try:
                    main_url = urls[0]
                    url_info = self.extract_webpage_content(main_url)
                    if url_info.get('success'):
                        result['webpage_info'] = url_info
                except:
                    pass
            
            return result
            
        except Exception as e:
            logging.error(f"Browser content extraction failed: {e}")
            return {
                'error': str(e),
                'success': False,
                'method': 'screen_ocr_analysis'
            }
            
    def analyze_web_content(self, content: Dict) -> Dict:
        """Analyze extracted web content with enhanced intelligence"""
        try:
            if not content.get('success', False):
                return {'analysis': 'No content to analyze', 'confidence': 0.0}
                
            text = content.get('text_content', '')
            word_count = len(text.split()) if text else 0
            urls = content.get('urls_found', [])
            
            # Enhanced analysis
            analysis = {
                'word_count': word_count,
                'content_type': content.get('content_type', 'unknown'),
                'has_urls': len(urls) > 0,
                'url_count': len(urls),
                'urls': urls[:5],  # First 5 URLs
                'is_web_content': content.get('is_web_content', False),
                'confidence': 0.0
            }
            
            # Detect content category
            content_categories = []
            if any(word in text.lower() for word in ['login', 'sign in', 'password', 'username']):
                content_categories.append('Authentication')
            if any(word in text.lower() for word in ['shop', 'buy', 'cart', 'price', 'product']):
                content_categories.append('E-commerce')
            if any(word in text.lower() for word in ['news', 'article', 'posted', 'published']):
                content_categories.append('News/Article')
            if any(word in text.lower() for word in ['search', 'results', 'found']):
                content_categories.append('Search Results')
            if any(word in text.lower() for word in ['video', 'play', 'watch', 'subscribe']):
                content_categories.append('Video Content')
                
            analysis['content_categories'] = content_categories
            
            # Calculate confidence based on various factors
            confidence = 0.2  # Base confidence
            if word_count > 0:
                confidence += 0.2
            if len(urls) > 0:
                confidence += 0.3
            if content.get('is_web_content'):
                confidence += 0.3
                
            analysis['confidence'] = min(confidence, 1.0)
            
            # Generate summary
            if content.get('is_web_content'):
                summary = f"Web content detected with {word_count} words"
                if urls:
                    summary += f" and {len(urls)} URLs"
                if content_categories:
                    summary += f". Categories: {', '.join(content_categories)}"
            else:
                summary = f"Non-web content with {word_count} words"
                
            analysis['summary'] = summary
            
            return analysis
            
        except Exception as e:
            logging.error(f"Web content analysis failed: {e}")
            return {'analysis': f'Analysis failed: {str(e)}', 'confidence': 0.0}
            
    def is_web_intelligence_available(self) -> bool:
        """Check if web intelligence features are available"""
        return self.selenium_available or self.beautifulsoup_available
        
    def get_available_features(self) -> List[str]:
        """Get list of available web intelligence features"""
        features = []
        if self.beautifulsoup_available:
            features.append('URL content extraction')
            features.append('HTML parsing')
        if self.selenium_available:
            features.append('Browser automation')
            features.append('JavaScript rendering')
        return features