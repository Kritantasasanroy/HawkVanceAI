import sys
import os
from pathlib import Path

# Add the project root directory to Python path
project_root = Path(__file__).parent
sys.path.append(str(project_root))

from src.ui import MainWindow
from src.core import ScreenCapture, OCRProcessor, GeminiProcessor
from src.utils import TextProcessor, DocumentExporter
from config.settings import TESSERACT_PATH, GEMINI_API_KEY
import logging

def setup_logging():
    """Configure logging"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('hawkvance.log'),
            logging.StreamHandler(sys.stdout)
        ]
    )

def main():
    """Main application entry point"""
    try:
        # Setup logging
        setup_logging()
        logging.info("Starting HawkVance AI")

        # Initialize core components with enhanced features
        screen_capture = ScreenCapture(gemini_api_key=GEMINI_API_KEY)
        
        # Try to initialize OCR processor with better error handling
        try:
            ocr_processor = OCRProcessor(tesseract_path=TESSERACT_PATH)
        except RuntimeError as ocr_error:
            logging.error(f"OCR initialization failed: {str(ocr_error)}")
            print("\n" + "="*60)
            print("TESSERACT OCR NOT FOUND")
            print("="*60)
            print("\nHawkVance AI requires Tesseract OCR to function.")
            print("\nTo install Tesseract:")
            print("1. Download from: https://github.com/UB-Mannheim/tesseract/wiki")
            print("2. Install the Windows installer (.exe file)")
            print("3. Make sure to install to: C:\\Program Files\\Tesseract-OCR")
            print("4. Add Tesseract to your system PATH during installation")
            print("\nAfter installation, restart this application.")
            print("="*60)
            input("\nPress Enter to exit...")
            return
            
        gemini_processor = GeminiProcessor()
        text_processor = TextProcessor()
        document_exporter = DocumentExporter()

        # Create and run main window
        root = MainWindow()
        
        # Pass core components to main window
        root.initialize_components(
            screen_capture=screen_capture,
            ocr_processor=ocr_processor,
            gemini_processor=gemini_processor,
            text_processor=text_processor,
            document_exporter=document_exporter
        )
        
        # Start the application
        root.mainloop()

    except Exception as e:
        logging.error(f"Application error: {str(e)}", exc_info=True)
        print(f"\nApplication error: {str(e)}")
        input("\nPress Enter to exit...")
        sys.exit(1)

if __name__ == "__main__":
    main()