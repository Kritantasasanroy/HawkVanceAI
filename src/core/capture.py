import pyautogui
import numpy as np
import cv2
from dataclasses import dataclass
from typing import Optional, Tuple
from tkinter import Toplevel, Canvas
import tkinter as tk

@dataclass
class CaptureRegion:
    x: int
    y: int
    width: int
    height: int

class ScreenCapture:
    def __init__(self):
        self._region: Optional[CaptureRegion] = None
        self._is_capturing = False
        self.start_x = None
        self.start_y = None
        self.current_rect = None
        
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