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
from config.environment import EnvironmentConfig
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

        # Load environment variables from .env file
        logging.info("Loading environment configuration...")
        try:
            EnvironmentConfig.load_environment()
        except PermissionError as e:
            logging.error("=" * 60)
            logging.error("PERMISSION ERROR: Cannot access .env file")
            logging.error("=" * 60)
            logging.error(f"Error details: {str(e)}")
            logging.error("")
            logging.error("This error occurs when the application cannot read the .env file")
            logging.error("due to insufficient permissions.")
            logging.error("")
            logging.error("RESOLUTION:")
            logging.error("1. Check that the .env file exists in the HawkVanceAI directory")
            logging.error("2. Verify file permissions allow read access")
            logging.error("3. On Windows: Right-click .env → Properties → Security")
            logging.error("4. On Linux/Mac: chmod 644 .env")
            logging.error("=" * 60)
            logging.info("Shutting down due to file permission error.")
            sys.exit(1)
        except Exception as e:
            logging.error("=" * 60)
            logging.error("ENVIRONMENT LOADING ERROR")
            logging.error("=" * 60)
            logging.error(f"Failed to load environment configuration: {str(e)}")
            logging.error("")
            logging.error("This may be caused by:")
            logging.error("- Malformed .env file (check syntax)")
            logging.error("- File encoding issues (ensure UTF-8)")
            logging.error("- Corrupted .env file")
            logging.error("")
            logging.error("RESOLUTION:")
            logging.error("1. Check your .env file format and syntax")
            logging.error("2. Ensure each line follows: VARIABLE_NAME=value")
            logging.error("3. Remove any special characters or formatting")
            logging.error("4. Try recreating the .env file from .env.example")
            logging.error("=" * 60)
            logging.info("Shutting down due to environment loading error.")
            sys.exit(1)
        
        # Validate required environment variables
        logging.info("Validating environment configuration...")
        if not EnvironmentConfig.validate_required_vars():
            missing_vars = EnvironmentConfig.get_missing_vars()
            
            # Run detailed diagnostics to help with troubleshooting
            logging.info("")
            EnvironmentConfig.diagnose_configuration_issues()
            
            logging.error("")
            logging.error("=" * 60)
            logging.error("APPLICATION STARTUP FAILED")
            logging.error("=" * 60)
            logging.error("The application cannot start due to missing or invalid configuration.")
            logging.error(f"Specifically, these variables need attention: {', '.join(missing_vars)}")
            logging.error("")
            logging.error("NEXT STEPS:")
            logging.error("1. Review the detailed error messages and diagnostics above")
            logging.error("2. Create or update your .env file with the required variables")
            logging.error("3. Restart the application after fixing the configuration")
            logging.error("")
            logging.error("If you continue to have issues, check the documentation or")
            logging.error("verify that all dependencies are properly installed.")
            logging.error("=" * 60)
            logging.info("Shutting down gracefully due to configuration errors.")
            
            # Graceful exit with appropriate error code
            sys.exit(1)
        
        # Log configuration status for debugging
        EnvironmentConfig.log_configuration_status()
        logging.info("Environment configuration validated successfully.")
        
        # Validate settings configuration (paths, etc.)
        logging.info("Validating application settings...")
        try:
            from config.settings import validate_configuration
            validate_configuration()
            logging.info("✓ Application settings validated successfully.")
        except ValueError as e:
            logging.error("=" * 60)
            logging.error("SETTINGS VALIDATION FAILED")
            logging.error("=" * 60)
            logging.error(f"Configuration error: {str(e)}")
            logging.error("")
            logging.error("This indicates that while environment variables are set,")
            logging.error("some values are invalid or point to missing resources.")
            logging.error("")
            logging.error("Please check the error details above and verify:")
            logging.error("- File paths exist and are accessible")
            logging.error("- API keys are valid and properly formatted")
            logging.error("- All required dependencies are installed")
            logging.error("=" * 60)
            logging.info("Shutting down due to settings validation failure.")
            sys.exit(1)

        # Initialize core components
        logging.info("Initializing core components...")
        screen_capture = ScreenCapture()
        ocr_processor = OCRProcessor(tesseract_path=TESSERACT_PATH)
        gemini_processor = GeminiProcessor()
        text_processor = TextProcessor()
        document_exporter = DocumentExporter()

        # Create and run main window
        logging.info("Creating main application window...")
        root = MainWindow()
        
        # Pass core components to main window
        root.initialize_components(
            screen_capture=screen_capture,
            ocr_processor=ocr_processor,
            gemini_processor=gemini_processor,
            text_processor=text_processor,
            document_exporter=document_exporter
        )
        
        logging.info("Application initialized successfully. Starting main loop...")
        # Start the application
        root.mainloop()

    except SystemExit:
        # Re-raise SystemExit to preserve exit codes
        raise
    except Exception as e:
        logging.error("=" * 60)
        logging.error("FATAL ERROR: Unexpected application failure")
        logging.error("=" * 60)
        logging.error(f"Error details: {str(e)}")
        logging.error(f"Error type: {type(e).__name__}")
        logging.error("")
        logging.error("This unexpected error may be caused by:")
        logging.error("- Missing or invalid environment configuration")
        logging.error("- Missing system dependencies (Tesseract, Python packages)")
        logging.error("- File permission or access issues")
        logging.error("- Corrupted installation or configuration files")
        logging.error("- System resource limitations")
        logging.error("")
        logging.error("TROUBLESHOOTING STEPS:")
        logging.error("1. Check that all required environment variables are set")
        logging.error("2. Verify Tesseract OCR is properly installed")
        logging.error("3. Ensure all Python dependencies are installed (pip install -r requirements.txt)")
        logging.error("4. Check file permissions for the application directory")
        logging.error("5. Review the full error traceback in the log file")
        logging.error("")
        logging.error("If the problem persists, please report this error with the")
        logging.error("full log output for further assistance.")
        logging.error("=" * 60)
        logging.debug("Full error traceback:", exc_info=True)
        logging.info("Application terminated due to fatal error.")
        sys.exit(1)

if __name__ == "__main__":
    main()