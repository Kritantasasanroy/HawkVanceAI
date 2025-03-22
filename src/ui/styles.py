from tkinter import ttk
import tkinter as tk
from config.settings import THEME  # Importing theme colors

class HawkVanceStyle:
    @staticmethod
    def configure_styles():
        # Create and configure ttk styles
        style = ttk.Style()
        
        # Configure main background frame
        style.configure('HawkVance.TFrame', background=THEME['background'])

        # Configure buttons with uniform style
        style.configure('HawkVance.TButton',
            background=THEME['accent'],  # Button color
            foreground='black',  # Button text color
            padding=(8, 4),  # Reduced padding by 20%
            font=('Segoe UI', 9, 'bold'),  # Font settings
            width=12,  # Uniform width
            relief='flat',
            borderwidth=6  # Increased rounding by 15%
        )
        style.map('HawkVance.TButton', 
            background=[('active', THEME['primary'])]  # Change color when active
        )
        
        # Configure navigation button styles
        style.configure('Nav.TButton',
            background=THEME['primary'],  # Navigation button color
            foreground='black',
            padding=(5, 2),
            font=('Segoe UI', 10, 'bold')
        )
        
        # Configure title bar
        style.configure('TitleBar.TFrame',
            background=THEME['primary'],  # Title bar color
            relief='raised'
        )
        
        # Configure content frame
        style.configure('Content.TFrame',
            background=THEME['secondary'],
            relief='flat'
        )

        # **Ensuring MAIN TEXT & HEADINGS are WHITE**
        style.configure('Heading.TLabel',
            foreground='white',  # Set all headings to white
            font=('Segoe UI', 12, 'bold'),  # Bold headings
            background=THEME['secondary']
        )

        style.configure('Text.TLabel',
            foreground='white',  # Set all normal text to white
            font=('Segoe UI', 11),
            background=THEME['secondary']
        )

        return {
            'title_bar': {
                'bg': THEME['primary'],
                'fg': 'white',  # Ensure title bar text is white
                'relief': 'raised',
                'bd': 0
            },
            'button': {
                'bg': THEME['accent'],
                'fg': 'white',  # Button text white
                'activebackground': THEME['primary'],
                'activeforeground': 'white',
                'relief': 'flat',
                'bd': 0,
                'padx': 10,
                'pady': 5,
                'font': ('Segoe UI', 10)
            },
            'text': {
                'bg': THEME['secondary'],
                'fg': 'white',  # Ensure all normal text is white
                'font': ('Segoe UI', 11),
                'relief': 'flat',
                'bd': 0,
                'padx': 10,
                'pady': 5
            }
        }
