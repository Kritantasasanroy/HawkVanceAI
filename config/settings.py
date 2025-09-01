import os
import logging
from .environment import EnvironmentConfig

# Load environment variables on module import
EnvironmentConfig.load_environment()

def validate_configuration():
    """
    Validate that all required configuration is present and valid.
    
    Raises:
        ValueError: If required configuration is missing or invalid
    """
    missing_vars = []
    
    # Check for required environment variables
    if not os.getenv("GEMINI_API_KEY"):
        missing_vars.append("GEMINI_API_KEY")
    
    if not os.getenv("TESSERACT_PATH"):
        missing_vars.append("TESSERACT_PATH")
    
    if missing_vars:
        error_msg = f"Missing required environment variables: {', '.join(missing_vars)}"
        logging.error(error_msg)
        logging.error("Please create a .env file with the required variables or set them in your system environment.")
        logging.error("See .env.example for the required format.")
        raise ValueError(error_msg)
    
    # Validate Tesseract path exists
    tesseract_path = os.getenv("TESSERACT_PATH")
    if tesseract_path and not os.path.exists(tesseract_path):
        error_msg = f"TESSERACT_PATH points to non-existent file: {tesseract_path}"
        logging.error(error_msg)
        logging.error("Please verify the Tesseract installation path in your .env file.")
        raise ValueError(error_msg)
    
    logging.info("Configuration validation successful")

# Note: Configuration validation is now handled in main.py during startup
# This allows for better error handling and graceful shutdown

# API Configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# UI Configuration
THEME = {
    'primary': '#2C3E50',    # Dark blue-gray
    'secondary': '#ECF0F1',  # Light gray
    'accent': '#3498DB',     # Bright blue
    'text': '#2C3E50',       # Dark blue-gray
    'text_light': '#ECF0F1', # Light gray
    'success': '#2ECC71',    # Green
    'warning': '#F1C40F',    # Yellow
    'error': '#E74C3C',      # Red
    'background': '#FFFFFF', # White
}

# Window Configuration
WINDOW_CONFIG = {
    'width': 800,
    'height': 600,
    'min_width': 400,
    'min_height': 300,
    'title': 'HawkVance AI',
}

# OCR Configuration
TESSERACT_PATH = os.getenv("TESSERACT_PATH")
# Capture Configuration
CAPTURE_CONFIG = {
    'overlay_width': 800,
    'margin': 10,
    'update_interval': 6000,  # milliseconds
}

# Export Configuration
EXPORT_CONFIG = {
    'max_responses': 5,
    'default_dir': os.path.expanduser('~/Documents/HawkVanceAI'),
}