import os

# API Configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AIzaSyASYcIjY3TIuo0n_i49Un7G5Shf_rESZHY")

# UI Configuration
THEME = {
    'dark_blackish_purple': '#2D1B4F',  # Royal background color
    'background': '#2D1B4F',
    'primary': '#4A307D',
    'accent': '#7157A3',
    'secondary': '#3A235A',
    'text': 'white',
    'text_light': 'white',
    'success': '#4CAF50'  # Green for success messages (change if needed)
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
TESSERACT_PATH = r'C:\Users\mithu\AppData\Local\Programs\Tesseract-OCR\tesseract.exe'

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