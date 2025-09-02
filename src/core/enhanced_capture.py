import pyautogui
import numpy as np
import cv2
import time
import logging
from dataclasses import dataclass
from typing import List, Optional, Dict, Tuple

@dataclass
class CaptureResult:
    """Result of a single capture operation"""
    image: np.ndarray
    timestamp: float
    text_content: str
    confidence: float
    metadata: Dict

class EnhancedScreenCapture:
    """Enhanced screen capture with advanced features"""
    
    def __init__(self):
        self.capture_history = []
        logging.info("Enhanced screen capture module initialized")
        
    def capture_scrollable_content(self, max_scrolls: int = 5) -> List[CaptureResult]:
        """Capture scrollable content using smart scrolling"""
        try:
            # Import smart scrolling if available
            from .smart_scrolling import SmartScrollingCapture
            
            smart_scroller = SmartScrollingCapture()
            captures = smart_scroller.capture_with_smart_scrolling(max_scrolls=max_scrolls)
            
            results = []
            for i, capture in enumerate(captures):
                result = CaptureResult(
                    image=capture.image,
                    timestamp=capture.timestamp,
                    text_content=f"Scroll position {capture.position}",
                    confidence=1.0 - capture.similarity_to_previous,
                    metadata={'position': capture.position, 'similarity': capture.similarity_to_previous}
                )
                results.append(result)
                
            return results
            
        except ImportError:
            logging.warning("Smart scrolling not available for enhanced capture")
            return []
        except Exception as e:
            logging.error(f"Enhanced scrollable capture failed: {e}")
            return []
            
    def capture_with_analysis(self, target_analysis: str = None) -> CaptureResult:
        """Capture with built-in analysis"""
        try:
            import pyautogui
            
            # Take screenshot
            screenshot = pyautogui.screenshot()
            image = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
            
            # Basic analysis placeholder
            text_content = "Enhanced capture completed"
            if target_analysis:
                text_content = f"Analysis target: {target_analysis}"
            
            result = CaptureResult(
                image=image,
                timestamp=time.time(),
                text_content=text_content,
                confidence=0.9,
                metadata={'analysis_target': target_analysis}
            )
            
            self.capture_history.append(result)
            return result
            
        except Exception as e:
            logging.error(f"Enhanced capture with analysis failed: {e}")
            return None
            
    def get_capture_history(self) -> List[CaptureResult]:
        """Get history of captures"""
        return self.capture_history.copy()
        
    def clear_history(self):
        """Clear capture history"""
        self.capture_history.clear()
        logging.info("Enhanced capture history cleared")
