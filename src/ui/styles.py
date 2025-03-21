from tkinter import ttk
import tkinter as tk
from config.settings import THEME

class HawkVanceStyle:
    @staticmethod
    def configure_styles():
        # Create and configure ttk styles
        style = ttk.Style()
        
        # Configure main theme
        style.configure('HawkVance.TFrame', background=THEME['background'])
        
        # Configure uniform button styles (20% smaller & 15% more rounded)
        style.configure('HawkVance.TButton',
            background=THEME['accent'],
            foreground='Black',
            padding=(8, 4),  # Reduced padding by 20%
            font=('Segoe UI', 9, 'bold'),
            width=12,  # Uniform width
            relief='flat',
            borderwidth=6  # Increased rounding by 15%
        )
        style.map('HawkVance.TButton', 
            background=[('active', THEME['primary'])]  # Highlight effect
        )
        
        # Configure navigation button styles
        style.configure('Nav.TButton',
            background=THEME['primary'],
            foreground='Black',
            padding=(5, 2),
            font=('Segoe UI', 10, 'bold')
        )
        
        # Configure title bar style
        style.configure('TitleBar.TFrame',
            background=THEME['primary'],
            relief='raised'
        )
        
        # Configure text widget style
        style.configure('Content.TFrame',
            background=THEME['secondary'],
            relief='flat'
        )

        return {
            'title_bar': {
                'bg': THEME['primary'],
                'fg': 'white',  # Changed from THEME['text_light'] to 'white'
                'relief': 'raised',
                'bd': 0
            },
            'button': {
                'bg': THEME['accent'],
                'fg': 'white',  # Changed from THEME['text_light'] to 'white'
                'activebackground': THEME['primary'],
                'activeforeground': 'white',  # Changed from THEME['text_light'] to 'white'
                'relief': 'flat',
                'bd': 0,
                'padx': 10,
                'pady': 5,
                'font': ('Segoe UI', 10)
            },
            'text': {
                'bg': THEME['secondary'],
                'fg': 'white',  # Changed from THEME['text_light'] to 'white'
                'font': ('Segoe UI', 11),
                'relief': 'flat',
                'bd': 0,
                'padx': 10,
                'pady': 5
            }
        }
