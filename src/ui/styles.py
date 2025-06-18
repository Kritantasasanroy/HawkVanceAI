from tkinter import ttk
import tkinter as tk
from config.settings import THEME

class HawkVanceStyle:
    @staticmethod
    def configure_styles():
        style = ttk.Style()

        # Set background and general text color
        THEME['background'] = '#2E003E'  # Dark purple (start of gradient)
        THEME['text'] = '#FFFFFF'        # White for general text (not buttons)

        style.configure('HawkVance.TFrame', background=THEME['background'])

        style.configure('HawkVance.TButton',
                        background=THEME['accent'],
                        foreground='Black',  # Keep button text black
                        padding=(10, 5),
                        font=('Segoe UI', 10, 'bold'))

        style.configure('Nav.TButton',
                        background=THEME['primary'],
                        foreground='Black',  # Keep nav button text black
                        padding=(5, 2),
                        font=('Segoe UI', 12, 'bold'))

        style.configure('TitleBar.TFrame',
                        background=THEME['primary'],
                        relief='raised')

        style.configure('Content.TFrame',
                        background=THEME['secondary'],
                        relief='flat')

        return {
            'title_bar': {
                'bg': THEME['primary'],
                'fg': '#FFFFFF',  # white title text
                'relief': 'raised',
                'bd': 0
            },
            'button': {
                'bg': THEME['accent'],
                'fg': 'Black',  # Keep it black
                'activebackground': THEME['primary'],
                'activeforeground': 'Black',  # Also black on active
                'relief': 'flat',
                'bd': 0,
                'padx': 10,
                'pady': 5,
                'font': ('Segoe UI', 10)
            },
            'text': {
                'bg': THEME['secondary'],
                'fg': '#FFFFFF',  # White text
                'font': ('Segoe UI', 11),
                'relief': 'flat',
                'bd': 0,
                'padx': 10,
                'pady': 5
            }
        }

    @staticmethod
    def create_gradient_background(root, color1="#2E003E", color2="#4B0082"):
        """Creates a vertical gradient from color1 to color2 on a Canvas."""
        width = root.winfo_screenwidth()
        height = root.winfo_screenheight()

        gradient_canvas = tk.Canvas(root, width=width, height=height, highlightthickness=0)
        gradient_canvas.pack(fill='both', expand=True)

        # Create gradient by drawing rectangles
        limit = 256  # number of steps in gradient
        r1, g1, b1 = root.winfo_rgb(color1)
        r2, g2, b2 = root.winfo_rgb(color2)

        r_ratio = (r2 - r1) / limit
        g_ratio = (g2 - g1) / limit
        b_ratio = (b2 - b1) / limit

        for i in range(limit):
            nr = int(r1 + (r_ratio * i)) >> 8
            ng = int(g1 + (g_ratio * i)) >> 8
            nb = int(b1 + (b_ratio * i)) >> 8
            color = f"#{nr:02x}{ng:02x}{nb:02x}"
            y = int(i * height / limit)
            gradient_canvas.create_rectangle(0, y, width, y + height / limit, outline="", fill=color)

        return gradient_canvas
