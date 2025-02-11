import os
import time
import tkinter as tk
import threading
import google.generativeai as genai
import pytesseract
import cv2
import numpy as np
import pyautogui

# -------------------------------
# 1. Load the API Key
# -------------------------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    try:
        from config import GEMINI_API_KEY
    except ImportError:
        raise ValueError("API key not found. Set GEMINI_API_KEY environment variable or create config.py with your API key.")
if not GEMINI_API_KEY:
    raise ValueError("API key not found. Set GEMINI_API_KEY environment variable or use config.py.")
print("DEBUG: Using GEMINI_API_KEY =", GEMINI_API_KEY)

# -------------------------------
# 2. Configure the Gemini API
# -------------------------------
genai.configure(api_key=GEMINI_API_KEY)
# Initialize the Gemini model using your chosen model ("gemini-pro")
model = genai.GenerativeModel("gemini-pro")
# -------------------------------
# 3. Functions for Screen Analysis and Gemini Integration
# -------------------------------

def capture_screen():
    """
    Capture the current screen excluding the overlay area.
    We assume the overlay window is 800px wide and positioned at the top-right.
    So we capture from x=0 to x=(screen_width - overlay_width - margin).
    """
    screen_width, screen_height = pyautogui.size()
    overlay_width = 800  # Must match the overlay width below
    margin = 10
    region_width = screen_width - overlay_width - margin
    screenshot = pyautogui.screenshot(region=(0, 0, region_width, screen_height))
    screenshot = np.array(screenshot)
    screenshot = cv2.cvtColor(screenshot, cv2.COLOR_RGB2BGR)
    return screenshot

def extract_text(image):
    """
    Convert the image to grayscale, apply thresholding, and extract text using pytesseract.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    text = pytesseract.image_to_string(thresh, lang="eng")
    return text.strip()

def analyze_text_with_gemini(text):
    """
    If the text contains a question, include instructions to answer it.
    Otherwise, simply analyze the content.
    """
    if not text:
        return "No meaningful text detected."
    if "?" in text:
        prompt = f"Analyze the following screen content and answer any questions within it:\n{text}"
    else:
        prompt = f"Analyze the following screen content:\n{text}"
    response = model.generate_content(prompt)
    return response.text

def process_cycle():
    """
    Execute one cycle: capture the screen, extract text, analyze via Gemini, and return the response.
    """
    print("[📸] Capturing screen...")
    screen_image = capture_screen()
    print("[🔍] Extracting text...")
    extracted_text = extract_text(screen_image)
    print("Extracted Text:\n", extracted_text)
    print("[🤖] Sending text to Gemini for analysis...")
    gemini_response = analyze_text_with_gemini(extracted_text)
    print("\n[🔎 Gemini Response]:\n", gemini_response)
    return gemini_response

# -------------------------------
# 4. Persistent, Draggable, and Minimizable Overlay Window Setup
# -------------------------------

# Create the persistent overlay window
overlay_root = tk.Tk()
overlay_root.title("Gemini Analysis")
overlay_root.overrideredirect(True)  # Remove default window decorations
overlay_root.attributes("-topmost", True)
overlay_root.lift()

# Set overlay dimensions and position
overlay_width = 800
overlay_height = 600
screen_width = overlay_root.winfo_screenwidth()
x_position = screen_width - overlay_width - 10
y_position = 10
overlay_root.geometry(f"{overlay_width}x{overlay_height}+{x_position}+{y_position}")

# Create a custom title bar for dragging and minimizing
title_bar = tk.Frame(overlay_root, bg="gray", relief="raised", bd=2)
title_bar.pack(fill="x")
title_label = tk.Label(title_bar, text="Gemini Analysis", bg="gray", fg="white")
title_label.pack(side="left", padx=5)
minimize_button = tk.Button(title_bar, text="_", command=overlay_root.iconify, bg="gray", fg="white", bd=0)
minimize_button.pack(side="right", padx=5)

# Functions to enable dragging of the window
def start_move(event):
    overlay_root._drag_start_x = event.x
    overlay_root._drag_start_y = event.y

def on_move(event):
    x = overlay_root.winfo_x() - overlay_root._drag_start_x + event.x
    y = overlay_root.winfo_y() - overlay_root._drag_start_y + event.y
    overlay_root.geometry(f"+{x}+{y}")

title_bar.bind("<ButtonPress-1>", start_move)
title_bar.bind("<B1-Motion>", on_move)

# Create a content frame for the scrollable text widget
content_frame = tk.Frame(overlay_root, bg="lightyellow")
content_frame.pack(expand=True, fill="both")
scrollbar = tk.Scrollbar(content_frame)
scrollbar.pack(side="right", fill="y")
text_widget = tk.Text(content_frame, wrap="word", font=("Arial", 12), bg="lightyellow", fg="black")
text_widget.pack(expand=True, fill="both", padx=10, pady=10)
text_widget.config(yscrollcommand=scrollbar.set)
scrollbar.config(command=text_widget.yview)

def update_text_widget(new_text):
    """
    Update the persistent text widget with new Gemini response.
    """
    text_widget.config(state="normal")
    text_widget.delete("1.0", tk.END)
    text_widget.insert(tk.END, new_text)
    text_widget.config(state="disabled")

# -------------------------------
# 5. Continuous Update Loop
# -------------------------------

def continuous_update():
    def worker():
        try:
            new_response = process_cycle()
        except Exception as e:
            new_response = f"Error: {e}"
        overlay_root.after(0, lambda: update_text_widget(new_response))
    threading.Thread(target=worker, daemon=True).start()
    overlay_root.after(5000, continuous_update)

# -------------------------------
# 6. Main Execution
# -------------------------------
if __name__ == "__main__":
    continuous_update()
    overlay_root.mainloop()