import pyautogui
import numpy as np
import cv2
import pyautogui
from dataclasses import dataclass
from typing import Optional, Tuple, List, Dict
from tkinter import Toplevel, Canvas
import tkinter as tk
import time
import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor
import threading
from pathlib import Path

@dataclass
class CaptureRegion:
    x: int
    y: int
    width: int
    height: int

class ScreenCapture:
    """Basic screen capture functionality that main.py expects"""
    
    def __init__(self, gemini_api_key: str = None):
        self._region: Optional[CaptureRegion] = None
        self._is_capturing = False
        self.start_x = None
        self.start_y = None
        self.current_rect = None
        self.gemini_api_key = gemini_api_key
        
        logging.info("Basic ScreenCapture initialized")
        
    @property
    def is_capturing(self) -> bool:
        return self._is_capturing
        
    def select_region(self) -> Tuple[int, int, int, int]:
        """Open a fullscreen window to select capture region"""
        root = tk.Tk()
        root.withdraw()  # Hide the main window
        
        # Create selection window
        self.selection_window = Toplevel(root)
        self.selection_window.attributes('-fullscreen', True, '-alpha', 0.3)
        self.selection_window.configure(background='grey')
        
        # Create canvas for drawing selection
        self.canvas = Canvas(self.selection_window, cursor="cross")
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        # Bind mouse events
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        
        self.selection_window.wait_window()
        return self._region if self._region else (0, 0, 0, 0)

    def _on_press(self, event):
        self.start_x = event.x
        self.start_y = event.y

    def _on_drag(self, event):
        if self.current_rect:
            self.canvas.delete(self.current_rect)
        self.current_rect = self.canvas.create_rectangle(
            self.start_x, self.start_y, event.x, event.y, outline='red'
        )

    def _on_release(self, event):
        x1, y1 = min(self.start_x, event.x), min(self.start_y, event.y)
        x2, y2 = max(self.start_x, event.x), max(self.start_y, event.y)
        self._region = (x1, y1, x2-x1, y2-y1)
        self.selection_window.destroy()
        
    def set_region(self, x: int, y: int, width: int, height: int) -> None:
        """Set the region for capture"""
        self._region = CaptureRegion(x, y, width, height)
        
    def clear_region(self) -> None:
        """Clear the capture region"""
        self._region = None
        
    def start_capture(self) -> None:
        """Start screen capture"""
        self._is_capturing = True
        
    def stop_capture(self) -> None:
        """Stop screen capture"""
        self._is_capturing = False
        
    def capture(self) -> np.ndarray:
        """Capture the screen or selected region"""
        try:
            if self._region:
                screenshot = pyautogui.screenshot(region=(
                    self._region.x,
                    self._region.y,
                    self._region.width,
                    self._region.height
                ))
            else:
                screenshot = pyautogui.screenshot()
                
            # Convert to CV2 format
            frame = np.array(screenshot)
            return cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        except Exception as e:
            logging.error(f"Screenshot capture failed: {e}")
            return None

# Advanced Screen Capture for modern UI compatibility
class AdvancedScreenCapture(ScreenCapture):
    """Advanced screen capture with AI integration and smart features"""
    
    def __init__(self, gemini_api_key: str = None):
        super().__init__(gemini_api_key)
        self.smart_scroller = None
        
        # Initialize smart scrolling if available
        try:
            from .smart_scrolling import SmartScrollingCapture
            self.smart_scroller = SmartScrollingCapture()
            logging.info("Smart scrolling initialized")
        except ImportError:
            logging.warning("Smart scrolling not available")
            
        # Initialize AI processor if available
        self.ai_processor = None
        if gemini_api_key:
            try:
                from ..core.gemini_processor import GeminiProcessor
                self.ai_processor = GeminiProcessor()
                logging.info("AI processor initialized")
            except ImportError:
                logging.warning("AI processor not available")
                
        self.capture_modes = {
            'basic': True,
            'smart_scroll': bool(self.smart_scroller),
            'ai_analysis': bool(self.ai_processor)
        }
        
    async def capture_with_analysis(self, question: str = None) -> Dict:
        """Capture screen and perform AI analysis"""
        try:
            # Basic capture
            image = self.capture()
            if image is None:
                return {'error': 'Failed to capture screen'}
            
            result = {
                'timestamp': time.time(),
                'image': image,
                'analysis': None,
                'text_content': None
            }
            
            # OCR extraction if available
            try:
                from .ocr import OCRProcessor
                from config.settings import TESSERACT_PATH
                ocr = OCRProcessor(TESSERACT_PATH)
                text = ocr.extract_text(image)
                result['text_content'] = text
                
                # AI analysis if available and question provided
                if self.ai_processor and (question or text):
                    analysis_text = question or text
                    ai_result = self.ai_processor.analyze_text(analysis_text)
                    result['analysis'] = ai_result.summary if hasattr(ai_result, 'summary') else str(ai_result)
                    
            except Exception as e:
                logging.warning(f"OCR/AI analysis failed: {e}")
                result['text_content'] = "OCR not available"
                
            return result
            
        except Exception as e:
            logging.error(f"Capture with analysis failed: {e}")
            return {'error': str(e)}
            
    def capture_smart_scrolling(self, max_scrolls: int = 5) -> List:
        """Perform smart scrolling capture"""
        if not self.smart_scroller:
            return [{'error': 'Smart scrolling not available'}]
            
        try:
            captures = self.smart_scroller.capture_with_smart_scrolling(max_scrolls=max_scrolls)
            return captures
        except Exception as e:
            logging.error(f"Smart scrolling failed: {e}")
            return [{'error': str(e)}]

# Backward compatibility alias
ScreenCapture = AdvancedScreenCapture