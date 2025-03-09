import os

# API Configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AIzaSyASYcIjY3TIuo0n_i49Un7G5Shf_rESZHY")

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
TESSERACT_PATH = r'C:\Users\kunda\AppData\Local\Programs\Tesseract-OCR\tesseract.exe'

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