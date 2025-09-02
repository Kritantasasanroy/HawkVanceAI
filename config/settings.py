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
# Common Tesseract installation paths on Windows
TESSERACT_PATHS = [
    r'C:\Program Files\Tesseract-OCR\tesseract.exe',
    r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
    r'C:\Users\{}\AppData\Local\Programs\Tesseract-OCR\tesseract.exe'.format(os.getenv('USERNAME', 'user')),
    'tesseract'  # If it's in PATH
]

# Function to find Tesseract installation
def find_tesseract_path():
    """Find the correct Tesseract path on the system"""
    import shutil
    
    # Check if tesseract is in PATH
    tesseract_in_path = shutil.which('tesseract')
    if tesseract_in_path:
        return tesseract_in_path
    
    # Check common installation paths
    for path in TESSERACT_PATHS[:-1]:  # Exclude 'tesseract' from file checks
        if os.path.exists(path):
            return path
    
    return None

TESSERACT_PATH = find_tesseract_path()

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