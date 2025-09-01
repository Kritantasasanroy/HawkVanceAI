# HawkVanceAI

HawkVanceAI is a real-time screen analysis and text processing application that leverages Google’s Gemini API (using the `gemini-pro` model) to analyze the content of your screen. It continuously captures your screen, extracts text using OCR (via Tesseract), sends the text to the Gemini API for analysis (including answering questions found in the text), and displays the response in a persistent, draggable, and minimizable overlay window. The overlay updates at a configurable interval (currently every 15 seconds) without capturing itself in subsequent screenshots.

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Project Structure](#project-structure)
- [Requirements](#requirements)
- [Installation](#installation)
- [Environment Variables](#environment-variables)
- [Usage](#usage)
- [Customization](#customization)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [License](#license)

## Overview

HawkVanceAI is designed to provide real-time insights and analysis of what’s currently on your screen. It combines:
- **Screen Capture:** Automatically captures a portion of your screen excluding the overlay area.
- **OCR (Optical Character Recognition):** Extracts text from the captured screen image.
- **AI Analysis:** Uses Google’s Gemini API (via the `gemini-pro` model) to analyze the text, including answering questions if they are present.
- **Persistent Overlay:** Displays the analysis results in a customizable overlay window that remains on top of all other windows, is draggable, minimizable, and features a scrollable text widget.

## Features

- **Continuous Screen Capture:** Captures the screen at regular intervals (default is every 15 seconds).
- **Real-Time OCR:** Uses Tesseract to extract text from screenshots.
- **AI-Powered Analysis:** Sends extracted text to the Gemini API for analysis and question answering.
- **Persistent Overlay Window:** Displays the response in a window that is always on top, draggable, minimizable, and scrollable.
- **Excludes Overlay in Captures:** Ensures that the overlay is not captured in subsequent screenshots by excluding its region.

## Project Structure

HawkVanceAI/ ├── config.py # Stores the API key (fallback method) ├── main.py # Main application code └── requirements.txt # Python dependencies

markdown
Copy
Edit

## Requirements

- **Python 3.6+** (Tested with Python 3.12)
- **Tesseract OCR**  
  Install Tesseract OCR on your system and add its executable to your system PATH.  
  - [Tesseract OCR Installation](https://github.com/tesseract-ocr/tesseract)
- **Google Gemini API Key**
  - Get your API key from [Google AI Studio](https://makersuite.google.com/app/apikey)
- **Python Packages:** Listed in `requirements.txt`
  - `google-generativeai`
  - `pytesseract`
  - `opencv-python`
  - `numpy`
  - `pyautogui`
  - `python-dotenv`
  - (Tkinter is included with Python on most platforms)

## Installation

1. **Clone the Repository:**

   ```bash
   git clone https://github.com/Kritantasasanroy/HawkVanceAI.git
   cd HawkVanceAI
   ```

2. **Install Python Dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

3. **Install Tesseract OCR:**
   Follow the Tesseract installation instructions for your operating system:
   - **Windows:** Download from [GitHub releases](https://github.com/UB-Mannheim/tesseract/wiki)
   - **Linux:** `sudo apt-get install tesseract-ocr` (Ubuntu/Debian) or equivalent
   - **macOS:** `brew install tesseract`

4. **Set Up Environment Configuration:**

   a. **Copy the environment template:**
   ```bash
   cp .env.example .env
   ```

   b. **Edit the .env file** with your actual configuration:
   ```bash
   # Open .env in your preferred text editor
   notepad .env  # Windows
   nano .env     # Linux/macOS
   ```

   c. **Configure required variables** (see [Environment Variables](#environment-variables) section below)

## Environment Variables

HawkVanceAI uses environment variables to securely manage sensitive configuration. All required variables must be set in a `.env` file in the project root directory.

### Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `GEMINI_API_KEY` | Your Google Gemini API key for AI analysis | `AIzaSyC...` |
| `TESSERACT_PATH` | Full path to your Tesseract OCR executable | See platform examples below |

### Platform-Specific Tesseract Paths

**Windows:**
```
TESSERACT_PATH=C:\Users\username\AppData\Local\Programs\Tesseract-OCR\tesseract.exe
```

**Linux:**
```
TESSERACT_PATH=/usr/bin/tesseract
```

**macOS:**
```
TESSERACT_PATH=/usr/local/bin/tesseract
```

### Getting Your Gemini API Key

1. Visit [Google AI Studio](https://makersuite.google.com/app/apikey)
2. Sign in with your Google account
3. Click "Create API Key"
4. Copy the generated key to your `.env` file

### Security Notes

- **Never commit your `.env` file to version control** - it contains sensitive credentials
- The `.env` file is already included in `.gitignore` to prevent accidental commits
- Keep your API key secure and don't share it publicly

## Usage

### Prerequisites
Before running the application, ensure you have:
1. Completed all installation steps
2. Created and configured your `.env` file with valid credentials
3. Verified Tesseract OCR is properly installed

### Running the Application
To run the project, simply execute:

```bash
python main.py
```

### Application Startup
The application will:
1. **Load environment configuration** from your `.env` file
2. **Validate required environment variables** (API key and Tesseract path)
3. **Initialize components** with the loaded configuration
4. **Start the main application loop**

If any required environment variables are missing, the application will display an error message and exit gracefully.

### Application Functionality
Once running, the application will:
- Capture your screen (excluding the overlay area)
- Extract text from the captured image using Tesseract OCR
- Send the text to the Gemini API for analysis
- Update the overlay window with the analysis response every 15 seconds (configurable)
- Allow you to drag or minimize the overlay window without interfering with the screen capture

## Customization

### Update Interval
Change the update frequency by modifying the delay in the `overlay_root.after(15000, continuous_update)` call in `main.py` (e.g., to 5000 for 5 seconds).

### Overlay Window Size
Adjust `overlay_width` and `overlay_height` in `main.py` to change the size of the overlay window.

### Model Selection
The current model is set to "gemini-pro". You can change this to another model if desired, but ensure that the model is supported by your API key and project.

## Troubleshooting

### Configuration Issues

#### Missing .env File
**Error:** `FileNotFoundError: .env file not found`
**Solution:**
1. Copy the template: `cp .env.example .env`
2. Edit the `.env` file with your actual configuration values

#### Missing Environment Variables
**Error:** `EnvironmentError: Missing required environment variable: GEMINI_API_KEY`
**Solution:**
1. Open your `.env` file
2. Ensure all required variables are present and have valid values
3. Check for typos in variable names
4. Verify there are no extra spaces around the `=` sign

#### Invalid Gemini API Key
**Error:** `google.api_core.exceptions.Unauthenticated: 401 API key not valid`
**Solution:**
1. Verify your API key is correct in the `.env` file
2. Generate a new API key at [Google AI Studio](https://makersuite.google.com/app/apikey)
3. Ensure the API key has proper permissions
4. Check that you haven't exceeded your API quota

#### Tesseract Path Issues
**Error:** `TesseractNotFoundError: tesseract is not installed or it's not in your PATH`
**Solution:**
1. **Verify Tesseract installation:**
   - Windows: Check if Tesseract is installed in Program Files
   - Linux/macOS: Run `which tesseract` to find the path
2. **Update TESSERACT_PATH in .env:**
   - Use the full absolute path to the tesseract executable
   - Ensure the path uses forward slashes or properly escaped backslashes
3. **Common paths:**
   - Windows: `C:\Users\username\AppData\Local\Programs\Tesseract-OCR\tesseract.exe`
   - Linux: `/usr/bin/tesseract`
   - macOS: `/usr/local/bin/tesseract` or `/opt/homebrew/bin/tesseract`

### Application Issues

#### No Text Detected
**Symptoms:** OCR returns empty results
**Solutions:**
1. Ensure there is visible text on your screen when the capture occurs
2. Verify Tesseract OCR is properly installed and configured
3. Check that the screen capture area contains readable text
4. Try adjusting the screen capture region

#### API Connection Errors
**Symptoms:** Network or connection errors when calling Gemini API
**Solutions:**
1. Check your internet connection
2. Verify your API key is valid and active
3. Ensure the Gemini API service is available
4. Check if you've exceeded API rate limits

#### Overlay Not Updating
**Symptoms:** The overlay window doesn't refresh with new content
**Solutions:**
1. Check the console for error messages
2. Verify the update loop is running without exceptions
3. Ensure the application has proper screen capture permissions
4. Try restarting the application

### Getting Help

If you continue to experience issues:
1. **Check the console output** for detailed error messages
2. **Verify your environment setup** by running through the installation steps again
3. **Test individual components:**
   - Test Tesseract: `tesseract --version`
   - Test your API key using a simple API call
4. **Create an issue** on the GitHub repository with:
   - Your operating system and Python version
   - The complete error message
   - Your `.env.example` configuration (without sensitive values)

## Contributing

Contributions, suggestions, and improvements are welcome!
Feel free to fork the repository and submit a pull request with your changes.

## License

This project is open source and available under the MIT License.

---

Happy coding and good luck with scaling your project into a billion-dollar idea!
