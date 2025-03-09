import logging
import tkinter as tk
from tkinter import ttk
from .styles import HawkVanceStyle
from .components import ScrolledText, StatusBar
from config.settings import WINDOW_CONFIG, THEME
from tkinter import ttk, messagebox
import threading
class MainWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        
        # Make window stay on top
        self.attributes('-topmost', True)
        
        # Initialize component references
        self.screen_capture = None
        self.ocr_processor = None
        self.gemini_processor = None
        self.text_processor = None
        self.document_exporter = None
        
        # Add these lines
        self.response_history = []
        self.current_response_index = -1
        
        # Configure window
        self.title(WINDOW_CONFIG['title'])
        self.geometry(f"{WINDOW_CONFIG['width']}x{WINDOW_CONFIG['height']}")
        self.minsize(WINDOW_CONFIG['min_width'], WINDOW_CONFIG['min_height'])
        
        # Apply styles
        self.style = HawkVanceStyle.configure_styles()
        
        # Configure grid
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        
        # Create components
        self._create_title_bar()
        self._create_main_content()
        self._create_status_bar()

    def initialize_components(self, **components):
        """Initialize core components"""
        self.screen_capture = components.get('screen_capture')
        self.ocr_processor = components.get('ocr_processor')
        self.gemini_processor = components.get('gemini_processor')
        self.text_processor = components.get('text_processor')
        self.document_exporter = components.get('document_exporter')
        
        # Enable functionality now that components are initialized
        self._setup_event_handlers()

    def _setup_event_handlers(self):
        """Set up event handlers for buttons"""
        if hasattr(self, 'capture_button'):
            self.capture_button.configure(command=self._toggle_capture)
            
        if hasattr(self, 'region_button'):
            self.region_button.configure(command=self._set_region)
            
        if hasattr(self, 'export_button'):
            self.export_button.configure(command=self._export_results)

    def _create_title_bar(self):
        title_bar = ttk.Frame(self, style='TitleBar.TFrame')
        title_bar.grid(row=0, column=0, sticky='ew')
        
        # Title
        title = ttk.Label(title_bar, 
                         text=WINDOW_CONFIG['title'],
                         foreground=THEME['text_light'],
                         background=THEME['primary'],
                         font=('Segoe UI', 12, 'bold'))
        title.pack(side='left', padx=10)
        
        # Control buttons
        controls = ttk.Frame(title_bar, style='TitleBar.TFrame')
        controls.pack(side='right', padx=5)
        
        # Navigation and Export buttons only
        self.prev_button = ttk.Button(controls, text='←', style='Nav.TButton',
                                     command=self._show_previous)
        self.prev_button.pack(side='left', padx=2)
        
        self.next_button = ttk.Button(controls, text='→', style='Nav.TButton',
                                     command=self._show_next)
        self.next_button.pack(side='left', padx=2)
        
        self.export_button = ttk.Button(controls, text='Export', style='HawkVance.TButton',
                                       command=self._export_results)
        self.export_button.pack(side='left', padx=5)

    def _create_main_content(self):
        """Creates the main content area"""
        content = ttk.Frame(self, style='Content.TFrame')
        content.grid(row=1, column=0, sticky='nsew', padx=10, pady=5)
        content.grid_columnconfigure(0, weight=1)
        content.grid_rowconfigure(1, weight=1)

        # Control buttons
        buttons_frame = ttk.Frame(content, style='HawkVance.TFrame')
        buttons_frame.grid(row=0, column=0, sticky='ew', pady=(0, 5))
        
        self.capture_button = ttk.Button(
            buttons_frame, 
            text='Start Capture',
            style='HawkVance.TButton'
        )
        self.capture_button.pack(side='left', padx=5)
        
        self.region_button = ttk.Button(
            buttons_frame,
            text='Select Region',
            style='HawkVance.TButton'
        )
        self.region_button.pack(side='left', padx=5)

        # Add full screen capture button
        self.full_capture_button = ttk.Button(
            buttons_frame,
            text='Full Screen Capture',
            style='HawkVance.TButton',
            command=self._capture_full_screen
        )
        self.full_capture_button.pack(side='left', padx=5)

        # Output area with improved styling
        self.output_text = ScrolledText(
            content,
            height=15,
            width=50,
            font=('Segoe UI', 11),  # Changed to Segoe UI for better readability
            bg=THEME['background'],
            fg=THEME['text']
        )
        self.output_text.grid(row=1, column=0, sticky='nsew', pady=5)
        
        # Configure text tags with improved styling
        self.output_text.text.tag_configure('title', 
            font=('Segoe UI', 13, 'bold'),
            foreground=THEME['primary'],
            spacing3=10
        )
        
        self.output_text.text.tag_configure('section', 
            font=('Segoe UI', 12, 'bold'),
            foreground=THEME['accent'],
            spacing3=5
        )
        
        self.output_text.text.tag_configure('bullet', 
            font=('Segoe UI', 11),
            lmargin1=20,
            lmargin2=40
        )
        
        self.output_text.text.tag_configure('stat', 
            font=('Segoe UI', 11, 'bold'),
            foreground=THEME['success']
        )
        
        self.output_text.text.tag_configure('normal',
            font=('Segoe UI', 11)
        )
        
        self.output_text.text.tag_configure('bold',
            font=('Segoe UI', 11, 'bold')
        )

        # Input area
        input_frame = ttk.Frame(content, style='HawkVance.TFrame')
        input_frame.grid(row=2, column=0, sticky='ew', pady=(5, 0))
        input_frame.grid_columnconfigure(0, weight=1)

        self.input_entry = ttk.Entry(
            input_frame,
            font=('Segoe UI', 10)
        )
        self.input_entry.grid(row=0, column=0, sticky='ew', padx=(0, 5))

        self.ask_button = ttk.Button(
            input_frame,
            text='Ask',
            style='HawkVance.TButton',
            command=self._on_ask
        )
        self.ask_button.grid(row=0, column=1)

    def _create_status_bar(self):
        """Creates the status bar"""
        self.status_bar = StatusBar(self)
        self.status_bar.grid(row=2, column=0, sticky='ew')

    def update_status(self, message: str, show_progress: bool = False):
        """Update status bar message"""
        self.status_bar.set_status(message, show_progress)

    def _toggle_capture(self):
        """Toggle screen capture on/off"""
        if not self.screen_capture:
            return
            
        if self.screen_capture._is_capturing:
            self.screen_capture._is_capturing = False
            self.capture_button.configure(text='Start Capture')
            self.update_status("Capture stopped")
        else:
            self.screen_capture._is_capturing = True
            self.capture_button.configure(text='Stop Capture')
            self.update_status("Capturing...", show_progress=True)
            self._capture_loop()

    def _capture_loop(self):
        """Continuous capture loop"""
        if self.screen_capture and self.screen_capture._is_capturing:
            try:
                image = self.screen_capture.capture()
                if image is not None:
                    text = self.ocr_processor.extract_text(image)
                    if text:
                        # Clean the text first
                        cleaned_text = self.text_processor._clean_text(text)
                        if cleaned_text:
                            result = self.gemini_processor.analyze_text(cleaned_text)
                            if result.summary:
                                self.response_history.append(result.summary)
                                self.current_response_index = len(self.response_history) - 1
                                self._show_response(result.summary)
                                self.update_status("Analysis complete")
            except Exception as e:
                self.update_status(f"Capture error: {str(e)}")
                self.screen_capture._is_capturing = False
                self.capture_button.configure(text='Start Capture')
                return
                
            self.after(8500, self._capture_loop)  # Changed to 8 seconds

    def _set_region(self):
        """Open region selection dialog"""
        if self.screen_capture:
            self.withdraw()  # Hide main window
            try:
                # Get region coordinates
                x, y, w, h = self.screen_capture.select_region()
                if w > 0 and h > 0:
                    self.screen_capture.set_region(x, y, w, h)
                    self.update_status(f"Region set: {w}x{h}")
                    
                    # Immediate capture and analysis
                    self._capture_and_analyze()
                    
            except Exception as e:
                self.update_status(f"Error setting region: {str(e)}")
            finally:
                self.deiconify()

    def _capture_and_analyze(self):
        """Capture and analyze screen content"""
        try:
            image = self.screen_capture.capture()
            if image is not None:
                # Extract text
                text = self.ocr_processor.extract_text(image)
                if text:
                    # Clean the text
                    cleaned_text = self.text_processor._clean_text(text)
                    if cleaned_text:
                        # Analyze with Gemini
                        result = self.gemini_processor.analyze_text(cleaned_text)
                        if result.summary:
                            self.response_history.append(result.summary)
                            self.current_response_index = len(self.response_history) - 1
                            self._show_response(result.summary)
                            self.update_status("Analysis complete")
                        else:
                            self.update_status("No meaningful content to analyze")
                    else:
                        self.update_status("No text found after cleaning")
                else:
                    self.update_status("No text detected in image")
        except Exception as e:
            self.update_status(f"Error in capture and analysis: {str(e)}")

    def _export_results(self):
        """Export current results to PDF"""
        if not self.document_exporter:
            self.update_status("Error: Document exporter not initialized")
            return
            
        try:
            self.update_status("Exporting to PDF...", show_progress=True)
            
            # Prepare export data
            export_data = {
                'response_history': [],
                'summary': ''
            }
            
            # Add all responses from history
            if self.response_history:
                export_data['response_history'] = self.response_history
            else:
                # If no history, use current output
                current_text = self.output_text.text.get('1.0', tk.END).strip()
                if current_text:
                    export_data['summary'] = current_text
                else:
                    self.update_status("No content to export")
                    return
            
            # Export to PDF
            output_path = self.document_exporter.export_to_pdf(export_data)
            self.update_status(f"Exported successfully to: {output_path}")
            
        except Exception as e:
            self.update_status(f"Export failed: {str(e)}")
            logging.error(f"Export error: {str(e)}", exc_info=True)

    def _on_ask(self):
        """Handle question submission"""
        if not self.gemini_processor:
            self.update_status("Error: Gemini processor not initialized")
            return
            
        question = self.input_entry.get().strip()
        if not question:
            return
            
        try:
            self.update_status("Processing question...", show_progress=True)
            result = self.gemini_processor.analyze_text(question)
            
            if result.error:
                self.update_status(f"Error: {result.error}")
            else:
                # Add to history
                self.response_history.append(result.summary)
                self.current_response_index = len(self.response_history) - 1
                
                # Show response
                self.output_text.text.config(state='normal')
                self.output_text.text.delete('1.0', tk.END)
                self.output_text.text.insert('1.0', result.summary)
                self.output_text.text.config(state='disabled')
                
                # Clear input
                self.input_entry.delete(0, tk.END)
                self.update_status("Response generated successfully")
                
        except Exception as e:
            self.update_status(f"Error processing question: {str(e)}")

    def _on_settings(self):
        """Open settings dialog"""
        # This will be implemented when core functionality is ready
        pass

    def _show_previous(self):
        if self.response_history and self.current_response_index > 0:
            self.current_response_index -= 1
            self._show_response(self.response_history[self.current_response_index])

    def _show_next(self):
        if self.response_history and self.current_response_index < len(self.response_history) - 1:
            self.current_response_index += 1
            self._show_response(self.response_history[self.current_response_index])

    def _show_response(self, response):
        """Display formatted response in output text widget"""
        self.output_text.text.config(state='normal')
        self.output_text.text.delete('1.0', tk.END)
        
        lines = response.split('\n')
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            
            if '=' * 20 in line:  # Section separator
                # Skip separator line
                i += 1
                if i < len(lines):
                    # Get the title (removing ** markers)
                    title = lines[i].strip().replace('**', '')
                    self.output_text.text.insert(tk.END, f"{title}\n", 'title')
                i += 1  # Skip next separator
            
            elif line.startswith('**') and line.endswith('**'):  # Section headers
                # Remove ** markers and insert with section styling
                text = line.strip('*').strip()
                self.output_text.text.insert(tk.END, f"{text}\n", 'section')
            
            elif line.startswith('•'):  # Bullet points
                self.output_text.text.insert(tk.END, f"{line}\n", 'bullet')
            
            elif line.startswith('📊'):  # Statistics
                self.output_text.text.insert(tk.END, f"{line}\n", 'stat')
            
            elif line.startswith('Q:'):  # Questions
                self.output_text.text.insert(tk.END, f"{line}\n", 'bold')
                if i + 1 < len(lines) and lines[i + 1].startswith('A:'):
                    self.output_text.text.insert(tk.END, f"{lines[i + 1]}\n\n", 'normal')
                    i += 1
            
            else:
                # Check for bold text within line
                parts = line.split('**')
                if len(parts) > 1:
                    for j, part in enumerate(parts):
                        if j % 2 == 0:  # Regular text
                            self.output_text.text.insert(tk.END, part, 'normal')
                        else:  # Bold text
                            self.output_text.text.insert(tk.END, part, 'bold')
                    self.output_text.text.insert(tk.END, '\n')
                else:
                    self.output_text.text.insert(tk.END, f"{line}\n", 'normal')
            
            i += 1
        
        self.output_text.text.config(state='disabled')

    def _capture_full_screen(self):
        """Capture full screen once"""
        try:
            self.screen_capture.clear_region()  # Clear any existing region
            image = self.screen_capture.capture()
            if image is not None:
                text = self.ocr_processor.extract_text(image)
                if text:
                    result = self.gemini_processor.analyze_text(text)
                    self.response_history.append(result.summary)
                    self.current_response_index = len(self.response_history) - 1
                    self._show_response(result.summary)
        except Exception as e:
            self.update_status(f"Capture error: {str(e)}")