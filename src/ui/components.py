import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional
from config.settings import THEME

class IconButton(ttk.Button):
    """Custom button with icon support"""
    def __init__(self, master, text: str, icon: str = None, command: Callable = None, **kwargs):
        super().__init__(master, text=text, command=command, **kwargs)
        if icon:
            self.icon = tk.PhotoImage(file=icon)
            self.configure(image=self.icon, compound='left')

class ScrolledText(tk.Frame):
    """Custom scrolled text widget with line numbers"""
    def __init__(self, master, **kwargs):
        super().__init__(master)
        
        # Create text widget with scrollbar
        self.text = tk.Text(self, wrap='word', **kwargs)
        self.scrollbar = ttk.Scrollbar(self, command=self.text.yview)
        self.text.configure(yscrollcommand=self.scrollbar.set)
        
        # Create line numbers
        self.linenumbers = tk.Text(self, width=4, padx=3, takefocus=0,
                                 border=0, background=THEME['secondary'],
                                 state='disabled')
                                 
        # Grid layout
        self.linenumbers.grid(row=0, column=0, sticky='nsew')
        self.text.grid(row=0, column=1, sticky='nsew')
        self.scrollbar.grid(row=0, column=2, sticky='ns')
        
        # Configure grid weights
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        
        # Bind events
        self.text.bind('<KeyPress>', self._on_key_press)
        self.text.bind('<KeyRelease>', self._update_line_numbers)

    def _on_key_press(self, event=None):
        """Handle key press events"""
        return

    def _update_line_numbers(self, event=None):
        """Update line numbers"""
        if event and event.keysym in ('Up', 'Down', 'Return'):
            lines = self.text.get('1.0', 'end-1c').split('\n')
            line_count = len(lines)
            
            self.linenumbers.configure(state='normal')
            self.linenumbers.delete('1.0', 'end')
            self.linenumbers.insert('1.0', '\n'.join(str(i) for i in range(1, line_count + 1)))
            self.linenumbers.configure(state='disabled')

class StatusBar(ttk.Frame):
    """Custom status bar with progress indicator"""
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        
        self.status_label = ttk.Label(self, text="Ready")
        self.status_label.pack(side='left', padx=5)
        
        self.progress = ttk.Progressbar(self, mode='indeterminate', length=100)
        self.progress.pack(side='right', padx=5)

    def set_status(self, text: str, show_progress: bool = False):
        """Update status text and progress indicator"""
        self.status_label.configure(text=text)
        if show_progress:
            self.progress.start(10)
        else:
            self.progress.stop()
            self.progress.pack_forget()