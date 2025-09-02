import pyautogui
import cv2
import numpy as np
import time
import logging
from typing import List, Tuple, Optional
from dataclasses import dataclass

@dataclass
class ScrollCapture:
    """Single scroll capture result"""
    image: np.ndarray
    position: int
    timestamp: float
    similarity_to_previous: float

class SmartScrollingCapture:
    """
    Smart scrolling system that captures content beyond visible areas
    This is a working implementation that you can use immediately!
    """
    
    def __init__(self, ocr_processor=None):
        self.ocr_processor = ocr_processor
        self.scroll_delay = 0.5  # Delay between scrolls
        self.similarity_threshold = 0.95  # Threshold to detect end of content
        self.max_scrolls = 20  # Maximum number of scrolls to prevent infinite loops
        
    def capture_with_smart_scrolling(self, 
                                   target_text: Optional[str] = None, 
                                   max_scrolls: Optional[int] = None) -> List[ScrollCapture]:
        """
        Perform smart scrolling capture to get content beyond visible area
        
        Args:
            target_text: If provided, will stop scrolling when this text is found
            max_scrolls: Maximum number of scrolls (overrides default)
            
        Returns:
            List of ScrollCapture objects containing all captured content
        """
        if max_scrolls is None:
            max_scrolls = self.max_scrolls
            
        captures = []
        previous_image = None
        scroll_position = 0
        
        logging.info(f"Starting smart scrolling capture (max_scrolls: {max_scrolls})")
        
        try:
            while scroll_position < max_scrolls:
                # Capture current screen
                screenshot = pyautogui.screenshot()
                current_image = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
                
                # Calculate similarity to previous image
                similarity = 0.0
                if previous_image is not None:
                    similarity = self._calculate_similarity(previous_image, current_image)
                
                # Create capture record
                capture = ScrollCapture(
                    image=current_image,
                    position=scroll_position,
                    timestamp=time.time(),
                    similarity_to_previous=similarity
                )
                captures.append(capture)
                
                # Check if we've reached the end (high similarity)
                if similarity > self.similarity_threshold and scroll_position > 0:
                    logging.info(f"Reached end of content at scroll position {scroll_position}")
                    break
                
                # Check for target text if provided and OCR is available
                if target_text and self.ocr_processor:
                    try:
                        text = self.ocr_processor.extract_text(current_image)
                        if target_text.lower() in text.lower():
                            logging.info(f"Found target text '{target_text}' at scroll position {scroll_position}")
                            break
                    except Exception as e:
                        logging.warning(f"OCR failed during scrolling: {e}")
                
                # Scroll down for next capture
                if scroll_position < max_scrolls - 1:  # Don't scroll on last iteration
                    pyautogui.scroll(-3)  # Scroll down
                    time.sleep(self.scroll_delay)  # Wait for content to load
                
                previous_image = current_image
                scroll_position += 1
                
                # Progress logging
                if scroll_position % 5 == 0:
                    logging.info(f"Scroll progress: {scroll_position}/{max_scrolls}")
            
            # Scroll back to top
            self._scroll_to_top(scroll_position)
            
            logging.info(f"Smart scrolling completed. Captured {len(captures)} screens")
            return captures
            
        except Exception as e:
            logging.error(f"Error during smart scrolling: {e}")
            # Try to scroll back to top even if there was an error
            try:
                self._scroll_to_top(scroll_position)
            except:
                pass
            return captures
    
    def extract_all_text(self, captures: List[ScrollCapture]) -> str:
        """
        Extract text from all captures and combine intelligently
        """
        if not self.ocr_processor:
            return "OCR processor not available"
        
        all_text = []
        seen_text_segments = set()
        
        for i, capture in enumerate(captures):
            try:
                text = self.ocr_processor.extract_text(capture.image)
                
                if text.strip():
                    # Split into segments to avoid duplicates
                    segments = text.split('\n')
                    unique_segments = []
                    
                    for segment in segments:
                        segment = segment.strip()
                        if segment and segment not in seen_text_segments:
                            seen_text_segments.add(segment)
                            unique_segments.append(segment)
                    
                    if unique_segments:
                        all_text.extend(unique_segments)
                        logging.debug(f"Extracted {len(unique_segments)} unique text segments from capture {i}")
                        
            except Exception as e:
                logging.warning(f"Failed to extract text from capture {i}: {e}")
        
        combined_text = '\n'.join(all_text)
        logging.info(f"Combined text extraction complete. Total length: {len(combined_text)} characters")
        
        return combined_text
    
    def analyze_content_structure(self, captures: List[ScrollCapture]) -> dict:
        """
        Analyze the structure of captured content
        """
        analysis = {
            'total_captures': len(captures),
            'content_changes': 0,
            'duplicate_content': 0,
            'scroll_efficiency': 0.0,
            'content_regions': []
        }
        
        for i, capture in enumerate(captures):
            if i > 0:
                if capture.similarity_to_previous < 0.8:
                    analysis['content_changes'] += 1
                elif capture.similarity_to_previous > 0.95:
                    analysis['duplicate_content'] += 1
        
        if len(captures) > 1:
            analysis['scroll_efficiency'] = analysis['content_changes'] / (len(captures) - 1)
        
        logging.info(f"Content structure analysis: {analysis}")
        return analysis
    
    def _calculate_similarity(self, img1: np.ndarray, img2: np.ndarray) -> float:
        """
        Calculate similarity between two images
        """
        try:
            # Resize images to same size if different
            if img1.shape != img2.shape:
                h, w = min(img1.shape[0], img2.shape[0]), min(img1.shape[1], img2.shape[1])
                img1 = cv2.resize(img1, (w, h))
                img2 = cv2.resize(img2, (w, h))
            
            # Convert to grayscale
            gray1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
            gray2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)
            
            # Calculate correlation coefficient
            correlation = cv2.matchTemplate(gray1, gray2, cv2.TM_CCOEFF_NORMED)
            return float(correlation[0][0])
            
        except Exception as e:
            logging.warning(f"Failed to calculate image similarity: {e}")
            return 0.0
    
    def _scroll_to_top(self, scroll_count: int):
        """
        Scroll back to the top of the page
        """
        logging.info(f"Scrolling back to top ({scroll_count} scrolls)")
        
        # Multiple methods to get back to top
        # Method 1: Use Home key
        try:
            pyautogui.press('home')
            time.sleep(0.5)
        except:
            pass
        
        # Method 2: Ctrl+Home for some applications
        try:
            pyautogui.hotkey('ctrl', 'home')
            time.sleep(0.5)
        except:
            pass
        
        # Method 3: Scroll up the same amount we scrolled down
        try:
            for _ in range(scroll_count + 5):  # Add a few extra scrolls to ensure we're at top
                pyautogui.scroll(3)  # Scroll up
                time.sleep(0.05)  # Quick scrolls back up
        except:
            pass
        
        logging.info("Returned to top of page")

# Quick demo function
def demo_smart_scrolling(ocr_processor=None):
    """
    Quick demonstration of smart scrolling capabilities
    """
    print("🚀 Smart Scrolling Demo Starting...")
    print("⏰ You have 5 seconds to open a long webpage or document...")
    
    # Give user time to open content
    for i in range(5, 0, -1):
        print(f"⏰ {i}...")
        time.sleep(1)
    
    print("📸 Starting smart scrolling capture...")
    
    # Create smart scrolling instance
    smart_scroller = SmartScrollingCapture(ocr_processor)
    
    # Perform capture
    captures = smart_scroller.capture_with_smart_scrolling(max_scrolls=10)
    
    # Analyze results
    analysis = smart_scroller.analyze_content_structure(captures)
    
    print(f"\n✅ Smart Scrolling Complete!")
    print(f"📊 Results:")
    print(f"   - Total captures: {analysis['total_captures']}")
    print(f"   - Content changes: {analysis['content_changes']}")
    print(f"   - Scroll efficiency: {analysis['scroll_efficiency']:.2%}")
    
    if ocr_processor:
        print("📝 Extracting all text...")
        all_text = smart_scroller.extract_all_text(captures)
        print(f"   - Total text length: {len(all_text)} characters")
        print(f"   - First 200 characters: {all_text[:200]}...")
    
    return captures, analysis