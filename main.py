import os
import time
import tkinter as tk
import threading
import google.generativeai as genai
import pytesseract
import cv2
import numpy as np
import pyautogui

# Global variables for question cooldown and response history
last_question_time = 0    # Timestamp of the last question asked
question_cooldown = 5       # Cooldown period in seconds (5 sec)
response_history = []       # List to store generated responses
current_response_index = -1 # Pointer for navigating the history

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
# Initialize the Gemini model using "gemini-pro"
model = genai.GenerativeModel("gemini-pro")

# -------------------------------
# 3. Functions for Screen Analysis and Gemini Integration
# -------------------------------

def capture_screen():
    """
    Capture the current screen excluding the overlay region.
    We assume the overlay is 800px wide and positioned at the top-right.
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

import re

def clean_text(text):
    """
    Clean the input text by:
    - Splitting into lines.
    - Removing lines that are too short or contain no alphanumeric characters.
    - Returning the filtered text.
    """
    lines = text.splitlines()
    filtered_lines = []
    for line in lines:
        stripped = line.strip()
        # Skip if the line is too short (e.g., less than 5 characters) or contains no letters/digits.
        if len(stripped) < 5:
            continue
        if not re.search(r'[A-Za-z0-9]', stripped):
            continue
        filtered_lines.append(stripped)
    return "\n".join(filtered_lines)

def analyze_text_with_gemini(text):
    """
    Analyze the given text using the Gemini API.
    - First, the text is cleaned to remove noise.
    - If the cleaned text contains any question marks, the prompt instructs the model
      to both provide a detailed summary of the useful content and to list & answer every question.
    - Otherwise, it simply provides a summary.
    """
    cleaned_text = clean_text(text)
    if not cleaned_text:
        return "No meaningful text detected."

    # Construct a robust prompt based on whether questions are detected
    if "?" in cleaned_text:
        prompt = (
            "You are a highly capable assistant. Your task is to analyze the following screen content. "
            "First, provide a detailed, concise summary of the useful and relevant information, filtering out any noise or irrelevant details. "
            "Then, identify every clear question in the content and provide a comprehensive answer to each question individually. "
            "If a question is ambiguous, clarify it in your answer. Use bullet points if necessary.\n\n"
            "Screen Content:\n"
            f"{cleaned_text}"
        )
    else:
        prompt = (
            "You are a highly capable assistant. Your task is to analyze the following screen content and provide a detailed, concise summary of "
            "the useful and relevant information, filtering out any noise or irrelevant details.\n\n"
            "Screen Content:\n"
            f"{cleaned_text}"
        )

    response = model.generate_content(prompt)
    return response.text


def process_cycle():
    """
    Execute one cycle: capture screen, extract text, and get Gemini analysis.
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
# 4. Persistent, Draggable, Minimizable Overlay with Input & Navigation
# -------------------------------
overlay_root = tk.Tk()
overlay_root.title("HawkVance AI")
overlay_root.overrideredirect(True)
overlay_root.attributes("-topmost", True)
overlay_root.lift()

overlay_width = 800
overlay_height = 600
screen_width = overlay_root.winfo_screenwidth()
x_position = screen_width - overlay_width - 10
y_position = 10
overlay_root.geometry(f"{overlay_width}x{overlay_height}+{x_position}+{y_position}")

# Custom title bar
title_bar = tk.Frame(overlay_root, bg="gray", relief="raised", bd=2)
title_bar.pack(fill="x")
title_label = tk.Label(title_bar, text="HawkVance AI", bg="gray", fg="white")
title_label.pack(side="left", padx=5)
minimize_button = tk.Button(title_bar, text="_", command=overlay_root.iconify, bg="gray", fg="white", bd=0)
minimize_button.pack(side="right", padx=5)
paused = False
def toggle_pause():
    global paused
    paused = not paused
    if paused:
        pause_button.config(text="Resume")
        print("Updates paused.")
    else:
        pause_button.config(text="Pause")
        print("Updates resumed.")
pause_button = tk.Button(title_bar, text="Pause", command=toggle_pause, bg="gray", fg="white", bd=0)
pause_button.pack(side="right", padx=5)

def start_move(event):
    overlay_root._drag_start_x = event.x
    overlay_root._drag_start_y = event.y

def on_move(event):
    x = overlay_root.winfo_x() - overlay_root._drag_start_x + event.x
    y = overlay_root.winfo_y() - overlay_root._drag_start_y + event.y
    overlay_root.geometry(f"+{x}+{y}")

title_bar.bind("<ButtonPress-1>", start_move)
title_bar.bind("<B1-Motion>", on_move)

# Container for content and input using grid
main_container = tk.Frame(overlay_root, bg="lightyellow")
main_container.pack(expand=True, fill="both")
main_container.rowconfigure(0, weight=1)
main_container.rowconfigure(1, weight=0)
main_container.columnconfigure(0, weight=1)

# Content frame (scrollable text widget)
content_frame = tk.Frame(main_container, bg="lightyellow")
content_frame.grid(row=0, column=0, sticky="nsew")
scrollbar = tk.Scrollbar(content_frame)
scrollbar.pack(side="right", fill="y")
text_widget = tk.Text(content_frame, wrap="word", font=("Arial", 12), bg="lightyellow", fg="black")
text_widget.pack(expand=True, fill="both", padx=10, pady=10)
text_widget.config(yscrollcommand=scrollbar.set)
scrollbar.config(command=text_widget.yview)
def update_text_widget(new_text):
    text_widget.config(state="normal")
    text_widget.delete("1.0", tk.END)
    text_widget.insert(tk.END, new_text)
    text_widget.config(state="disabled")

# Input frame for manual questions
input_frame = tk.Frame(main_container, bg="lightyellow")
input_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=5)
input_frame.columnconfigure(0, weight=1)
question_entry = tk.Entry(input_frame, font=("Arial", 12))
question_entry.grid(row=0, column=0, sticky="ew", padx=(0,5))
def ask_question():
    global last_question_time, current_response_index
    current_time = time.time()
    if current_time - last_question_time < question_cooldown:
        remaining = int(question_cooldown - (current_time - last_question_time))
        update_text_widget(f"Please wait {remaining} seconds before asking another question.")
        return
    user_question = question_entry.get().strip()
    if user_question:
        prompt = f"Answer the following question:\n{user_question}"
        try:
            response = model.generate_content(prompt)
            answer = response.text
        except Exception as e:
            if "429" in str(e):
                answer = "Error: 429 Resource exhausted. Please wait and try again."
            else:
                answer = f"Error: {e}"
        response_history.append(answer)
        current_response_index = len(response_history) - 1
        update_text_widget(answer)
        question_entry.delete(0, tk.END)
        last_question_time = current_time
ask_button = tk.Button(input_frame, text="Ask", command=ask_question, font=("Arial", 12))
ask_button.grid(row=0, column=1, padx=5)

# Navigation buttons for response history
def show_previous_response():
    global current_response_index
    if response_history and current_response_index > 0:
        current_response_index -= 1
        update_text_widget(response_history[current_response_index])
def show_next_response():
    global current_response_index
    if response_history and current_response_index < len(response_history) - 1:
        current_response_index += 1
        update_text_widget(response_history[current_response_index])
prev_button = tk.Button(title_bar, text="←", command=show_previous_response, bg="gray", fg="white", bd=0)
prev_button.pack(side="right", padx=5)
next_button = tk.Button(title_bar, text="→", command=show_next_response, bg="gray", fg="white", bd=0)
next_button.pack(side="right", padx=5)

# -------------------------------
# 5. Continuous Update Loop with Pause Support
# -------------------------------
def continuous_update():
    def worker():
        try:
            new_response = process_cycle()
        except Exception as e:
            new_response = f"Error: {e}"
        response_history.append(new_response)
        global current_response_index
        current_response_index = len(response_history) - 1
        overlay_root.after(0, lambda: update_text_widget(new_response))
    if not paused:
        threading.Thread(target=worker, daemon=True).start()
    overlay_root.after(5000, continuous_update)
    
# -------------------------------
# 6. Main Execution
# -------------------------------
if __name__ == "__main__":
    continuous_update()
    overlay_root.mainloop()
