import sys
import os
from pathlib import Path

# Add the project root directory to Python path
project_root = Path(__file__).parent
sys.path.append(str(project_root))

from src.ui import MainWindow
from src.core import ScreenCapture, OCRProcessor, GeminiProcessor
from src.utils import TextProcessor, DocumentExporter
from config.settings import TESSERACT_PATH
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

        # Initialize core components
        screen_capture = ScreenCapture()
        ocr_processor = OCRProcessor(tesseract_path=TESSERACT_PATH)
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
        sys.exit(1)

if __name__ == "__main__":
    main()