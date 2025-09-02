import cv2
import pytesseract
import numpy as np
from typing import Optional
from pathlib import Path
import logging
import os

class OCRProcessor:
    def __init__(self, tesseract_path: Optional[str] = None):
        # Try to set Tesseract path if provided
        if tesseract_path:
            if tesseract_path != 'tesseract' and not os.path.exists(tesseract_path):
                logging.warning(f"Tesseract not found at specified path: {tesseract_path}")
                tesseract_path = None
            else:
                pytesseract.pytesseract.tesseract_cmd = tesseract_path
        
        # If no valid path provided, try to find Tesseract automatically
        if not tesseract_path:
            tesseract_path = self._find_tesseract()
            if tesseract_path:
                pytesseract.pytesseract.tesseract_cmd = tesseract_path
            
        # Verify Tesseract installation
        try:
            version = pytesseract.get_tesseract_version()
            logging.info(f"Tesseract OCR initialized successfully (version: {version})")
        except Exception as e:
            logging.error(f"Error initializing Tesseract OCR: {str(e)}")
            raise RuntimeError(
                "Tesseract OCR not found. Please:\n"
                "1. Download from: https://github.com/UB-Mannheim/tesseract/wiki\n"
                "2. Install to: C:\\Program Files\\Tesseract-OCR\n"
                "3. Add installation path to system PATH\n"
                "4. Or update TESSERACT_PATH in config/settings.py"
            )
    
    def _find_tesseract(self) -> Optional[str]:
        """Try to find Tesseract installation automatically"""
        import shutil
        
        # Check if tesseract is in PATH
        tesseract_in_path = shutil.which('tesseract')
        if tesseract_in_path:
            logging.info(f"Found Tesseract in PATH: {tesseract_in_path}")
            return tesseract_in_path
        
        # Check common installation paths
        common_paths = [
            r'C:\Program Files\Tesseract-OCR\tesseract.exe',
            r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
        ]
        
        for path in common_paths:
            if os.path.exists(path):
                logging.info(f"Found Tesseract at: {path}")
                return path
        
        logging.warning("Could not find Tesseract installation automatically")
        return None
            
    def preprocess_image(self, image: np.ndarray) -> np.ndarray:
        """Preprocess image for better OCR results"""
        # Convert to grayscale
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        # Apply thresholding
        thresh = cv2.threshold(
            gray, 0, 255, 
            cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )[1]
        
        # Optional: Apply noise reduction
        denoised = cv2.fastNlMeansDenoising(thresh)
        
        return denoised
        
    def extract_text(self, image: np.ndarray) -> str:
        """Extract text from image using OCR"""
        try:
            # Preprocess the image
            processed_image = self.preprocess_image(image)
            
            # Extract text using Tesseract
            text = pytesseract.image_to_string(
                processed_image,
                lang="eng",
                config='--psm 6'  # Assume uniform block of text
            )
            
            return text.strip()
            
        except Exception as e:
            logging.error(f"Error in text extraction: {str(e)}")
            return f"Error extracting text: {str(e)}"
            
    def get_text_regions(self, image: np.ndarray):
        """Get bounding boxes for text regions in image"""
        try:
            data = pytesseract.image_to_data(
                image, 
                output_type=pytesseract.Output.DICT
            )
            return data
            
        except Exception as e:
            logging.error(f"Error getting text regions: {str(e)}")
            return None