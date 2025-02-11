# HawkVanceAI

HawkVanceAI is a real-time screen analysis and text processing application that leverages Google’s Gemini API (using the `gemini-pro` model) to analyze the content of your screen. It continuously captures your screen, extracts text using OCR (via Tesseract), sends the text to the Gemini API for analysis (including answering questions found in the text), and displays the response in a persistent, draggable, and minimizable overlay window. The overlay updates at a configurable interval (currently every 15 seconds) without capturing itself in subsequent screenshots.

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Project Structure](#project-structure)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
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
- **Python Packages:** Listed in `requirements.txt`
  - `google-generativeai`
  - `pytesseract`
  - `opencv-python`
  - `numpy`
  - `pyautogui`
  - (Tkinter is included with Python on most platforms)

## Installation

1. **Clone the Repository:**

   ```bash
   git clone https://github.com/Kritantasasanroy/HawkVanceAI.git
   cd HawkVanceAI
Install Python Dependencies:

bash
Copy
Edit
pip install -r requirements.txt
Install Tesseract OCR:
Follow the Tesseract installation instructions for your operating system

Usage
To run the project, simply execute:

bash
Copy
Edit
python main.py
The application will:

Capture your screen (excluding the overlay area).
Extract text from the captured image using Tesseract OCR.
Send the text to the Gemini API for analysis.
Update the overlay window with the analysis response every 15 seconds (configurable).
Allow you to drag or minimize the overlay window without interfering with the screen capture.
Customization
Update Interval:
Change the update frequency by modifying the delay in the overlay_root.after(15000, continuous_update) call in main.py (e.g., to 5000 for 5 seconds).

Overlay Window Size:
Adjust overlay_width and overlay_height in main.py to change the size of the overlay window.

Model Selection:
The current model is set to "gemini-pro". You can change this to another model if desired, but ensure that the model is supported by your API key and project.

Troubleshooting
No Text Detected:
Ensure there is visible text on your screen when the capture occurs and that Tesseract OCR is properly installed.

API Errors:
If you encounter API errors, verify that your API key is valid, the Gemini API is enabled in your Google Cloud project, and your key has the necessary permissions.

Overlay Not Updating:
Make sure the update loop is running and that there are no errors in the console.

Contributing
Contributions, suggestions, and improvements are welcome!
Feel free to fork the repository and submit a pull request with your changes.

License
This project is open source and available under the MIT License.

Happy coding and good luck with scaling your project into a billion-dollar idea!

yaml
Copy
Edit

---

Feel free to adjust any sections as needed to better reflect your project's specifics. Enjoy pushing your project to GitHub, and best of luck with all your future improvements!
