import cv2
import pytesseract
import numpy as np
from typing import Optional
from pathlib import Path
import logging
import os

class OCRProcessor:
    def __init__(self, tesseract_path: Optional[str] = None):
        if tesseract_path:
            if not os.path.exists(tesseract_path):
                raise RuntimeError(f"Tesseract not found at: {tesseract_path}")
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