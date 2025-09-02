import logging
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading
import asyncio
import time
from typing import Optional, Dict, List
import json

from .styles import HawkVanceStyle
from .components import ScrolledText, StatusBar
from config.settings import WINDOW_CONFIG, THEME, GEMINI_API_KEY

# Import advanced capture system
try:
    from ..core.capture import AdvancedScreenCapture
    from ..core.smart_scrolling import SmartScrollingCapture
except ImportError:
    AdvancedScreenCapture = None
    SmartScrollingCapture = None
    import logging
    logging.warning("Advanced capture modules not available, using basic mode")
class MainWindow(tk.Tk):
    """Professional translucent main window with advanced AI capabilities"""
    
    def __init__(self):
        super().__init__()
        
        # Configure window for translucent, professional appearance
        self.attributes('-alpha', 0.92)  # Translucent effect
        self.attributes('-topmost', True)
        self.configure(bg='#1e1e2e')  # Dark professional background
        
        # Remove default window decorations for modern look
        self.overrideredirect(True)
        
        # Initialize advanced components
        self.advanced_capture = None
        self.smart_scroller = None
        self.ocr_processor = None
        self.gemini_processor = None
        self.text_processor = None
        self.document_exporter = None
        
        # UI State
        self.response_history = []
        self.context_history = []
        self.current_response_index = -1
        self.is_dragging = False
        self.drag_data = {'x': 0, 'y': 0}
        
        # Capture control state
        self.manual_capture_active = False
        self.selected_region = None
        self.region_info_text = "Full Screen"
        
        # Capture settings
        self.capture_modes = {
            'basic': tk.BooleanVar(value=True),
            'smart_scroll': tk.BooleanVar(value=True),
            'web_content': tk.BooleanVar(value=False),
            'context_aware': tk.BooleanVar(value=False),
            'ai_analysis': tk.BooleanVar(value=True)
        }
        
        self.auto_capture_enabled = False
        self.capture_interval = 10
        
        # Configure window properties
        self.title(f"{WINDOW_CONFIG['title']} - Advanced AI")
        self.geometry(f"{WINDOW_CONFIG['width']+100}x{WINDOW_CONFIG['height']+150}")
        self.minsize(500, 400)
        
        # Create modern UI
        self._create_modern_ui()
        
        # Bind window dragging events
        self._setup_window_dragging()
        
        # Initialize advanced components
        self.initialize_components()
        
        # Show welcome message about continuous monitoring
        self.after(2000, self._show_welcome_monitoring_message)  # Show after 2 seconds
        
        # Start continuous monitoring by default (core HawkVance AI feature)
        self.auto_capture_enabled = True  # Enable by default for continuous monitoring
        self._start_auto_capture_timer()  # Start monitoring immediately

    def _create_modern_ui(self):
        """Create modern, translucent UI with advanced features"""
        # Main container with gradient effect
        self.main_container = tk.Frame(self, bg='#1e1e2e', relief='flat', bd=0)
        self.main_container.pack(fill='both', expand=True, padx=1, pady=1)
        
        # Create sections
        self._create_modern_title_bar()
        self._create_advanced_control_panel()
        self._create_tabbed_content_area()
        self._create_modern_status_bar()
        
    def _create_modern_title_bar(self):
        """Create sleek title bar with controls"""
        title_frame = tk.Frame(self.main_container, bg='#2d2d44', height=40, relief='flat')
        title_frame.pack(fill='x', pady=(0, 1))
        title_frame.pack_propagate(False)
        
        # Make title bar draggable
        title_frame.bind('<Button-1>', self._start_drag)
        title_frame.bind('<B1-Motion>', self._on_drag)
        title_frame.bind('<ButtonRelease-1>', self._stop_drag)
        
        # App icon and title
        title_left = tk.Frame(title_frame, bg='#2d2d44')
        title_left.pack(side='left', fill='y', padx=10)
        
        icon_label = tk.Label(title_left, text='🚀', bg='#2d2d44', fg='#00d4ff', 
                             font=('Segoe UI', 14, 'bold'))
        icon_label.pack(side='left', pady=8)
        icon_label.bind('<Button-1>', self._start_drag)
        icon_label.bind('<B1-Motion>', self._on_drag)
        
        title_label = tk.Label(title_left, text='HawkVance AI - Advanced', 
                              bg='#2d2d44', fg='#ffffff', 
                              font=('Segoe UI', 10, 'bold'))
        title_label.pack(side='left', padx=(5, 0), pady=8)
        title_label.bind('<Button-1>', self._start_drag)
        title_label.bind('<B1-Motion>', self._on_drag)
        
        # Status indicator
        self.status_indicator = tk.Label(title_left, text='●', bg='#2d2d44', 
                                        fg='#00ff41', font=('Segoe UI', 12))
        self.status_indicator.pack(side='left', padx=(10, 0), pady=8)
        
        # Control buttons
        controls_frame = tk.Frame(title_frame, bg='#2d2d44')
        controls_frame.pack(side='right', padx=5, pady=5)
        
        # Modern buttons with hover effects
        self._create_title_button(controls_frame, '⚙️', self._toggle_settings, 'Settings')
        self._create_title_button(controls_frame, '📊', self._show_analytics, 'Analytics')
        self._create_title_button(controls_frame, '−', self._minimize_window, 'Minimize')
        self._create_title_button(controls_frame, '×', self._close_window, 'Close')
        
    def _create_title_button(self, parent, text, command, tooltip):
        """Create modern title bar button with hover effects"""
        btn = tk.Button(parent, text=text, command=command,
                       bg='#2d2d44', fg='#ffffff', relief='flat',
                       font=('Segoe UI', 10), width=3, height=1,
                       activebackground='#3d3d54', activeforeground='#00d4ff',
                       bd=0, cursor='hand2')
        btn.pack(side='right', padx=1)
        
        # Hover effects
        def on_enter(e):
            btn.configure(bg='#3d3d54', fg='#00d4ff')
        def on_leave(e):
            btn.configure(bg='#2d2d44', fg='#ffffff')
            
        btn.bind('<Enter>', on_enter)
        btn.bind('<Leave>', on_leave)
        
        return btn

    def _create_advanced_control_panel(self):
        """Create advanced control panel with modern styling"""
        control_frame = tk.Frame(self.main_container, bg='#252540', height=80)
        control_frame.pack(fill='x', pady=1)
        control_frame.pack_propagate(False)
        
        # Left side - Capture modes
        left_panel = tk.Frame(control_frame, bg='#252540')
        left_panel.pack(side='left', fill='both', expand=True, padx=10, pady=10)
        
        modes_label = tk.Label(left_panel, text='AI MODES', bg='#252540', fg='#00d4ff',
                              font=('Segoe UI', 9, 'bold'))
        modes_label.pack(anchor='w')
        
        modes_container = tk.Frame(left_panel, bg='#252540')
        modes_container.pack(fill='x', pady=(5, 0))
        
        # Capture mode checkboxes with modern styling
        mode_configs = [
            ('basic', '📷 Basic', '#00ff41'),
            ('smart_scroll', '📜 Smart Scroll', '#ff6b00'),
            ('web_content', '🌐 Web Intel', '#9d4edd'),
            ('context_aware', '🧠 Context AI', '#f72585'),
            ('ai_analysis', '🤖 AI Analysis', '#00d4ff')
        ]
        
        for i, (mode, label, color) in enumerate(mode_configs):
            cb_frame = tk.Frame(modes_container, bg='#252540')
            if i < 3:
                cb_frame.pack(side='left', padx=(0, 15))
            else:
                cb_frame.pack(side='left', padx=(0, 10))
            
            cb = tk.Checkbutton(cb_frame, text=label, variable=self.capture_modes[mode],
                               bg='#252540', fg=color, selectcolor='#1e1e2e',
                               font=('Segoe UI', 8, 'bold'), relief='flat',
                               activebackground='#252540', activeforeground=color,
                               command=self._update_capture_modes)
            cb.pack()
        
        # Right side - Action buttons
        right_panel = tk.Frame(control_frame, bg='#252540')
        right_panel.pack(side='right', fill='y', padx=10, pady=10)
        
        actions_label = tk.Label(right_panel, text='CAPTURE CONTROLS', bg='#252540', fg='#00d4ff',
                                font=('Segoe UI', 9, 'bold'))
        actions_label.pack(anchor='w')
        
        # First row of buttons
        actions_row1 = tk.Frame(right_panel, bg='#252540')
        actions_row1.pack(fill='x', pady=(5, 2))
        
        # Manual capture controls
        self.start_capture_btn = self._create_action_button(actions_row1, '▶️ Start Capture', 
                                                           self._start_manual_capture, '#00ff41')
        self.stop_capture_btn = self._create_action_button(actions_row1, '⏹️ Stop Capture', 
                                                          self._stop_manual_capture, '#ff4757')
        self.stop_capture_btn.configure(state='disabled')  # Initially disabled
        
        # Second row of buttons  
        actions_row2 = tk.Frame(right_panel, bg='#252540')
        actions_row2.pack(fill='x', pady=2)
        
        self._create_action_button(actions_row2, '🎯 Select Region', 
                                  self._select_capture_region, '#9d4edd')
        self._create_action_button(actions_row2, '🧠 Smart Capture', 
                                  self._smart_capture, '#00ff41')
        
        # Third row of buttons
        actions_row3 = tk.Frame(right_panel, bg='#252540')
        actions_row3.pack(fill='x', pady=2)
        
        self._create_action_button(actions_row3, '🔄 Auto Mode', 
                                  self._toggle_auto_capture, '#ff6b00')
        self._create_action_button(actions_row3, '📊 Analytics', 
                                  self._show_analytics, '#f72585')
        
        # Region info display
        self.region_info_label = tk.Label(right_panel, text=f'Region: {self.region_info_text}', 
                                         bg='#252540', fg='#ffffff',
                                         font=('Segoe UI', 8))
        self.region_info_label.pack(anchor='w', pady=(5, 0))
        
    def _create_action_button(self, parent, text, command, color):
        """Create modern action button"""
        btn = tk.Button(parent, text=text, command=command,
                       bg='#1e1e2e', fg=color, relief='flat',
                       font=('Segoe UI', 8, 'bold'), cursor='hand2',
                       bd=1, padx=6, pady=3, width=12)
        btn.pack(side='left', padx=(0, 3))
        
        # Hover effects
        def on_enter(e):
            btn.configure(bg=color, fg='#1e1e2e')
        def on_leave(e):
            btn.configure(bg='#1e1e2e', fg=color)
        
        btn.bind('<Enter>', on_enter)
        btn.bind('<Leave>', on_leave)
        
        return btn

    def _create_tabbed_content_area(self):
        """Create modern tabbed content area"""
        content_frame = tk.Frame(self.main_container, bg='#1e1e2e')
        content_frame.pack(fill='both', expand=True, padx=5, pady=1)
        
        # Question input area
        input_frame = tk.Frame(content_frame, bg='#252540', height=50)
        input_frame.pack(fill='x', pady=(0, 5))
        input_frame.pack_propagate(False)
        
        # Question input with modern styling
        input_container = tk.Frame(input_frame, bg='#252540')
        input_container.pack(fill='both', expand=True, padx=15, pady=10)
        
        question_label = tk.Label(input_container, text='🤔 Ask HawkVance AI:', 
                                 bg='#252540', fg='#00d4ff', 
                                 font=('Segoe UI', 10, 'bold'))
        question_label.pack(side='left')
        
        self.question_entry = tk.Entry(input_container, bg='#1e1e2e', fg='#ffffff',
                                      font=('Segoe UI', 10), relief='flat', bd=5,
                                      insertbackground='#00d4ff')
        self.question_entry.pack(side='left', fill='x', expand=True, padx=(10, 0))
        self.question_entry.bind('<Return>', lambda e: self._ask_ai_question())
        
        ask_btn = tk.Button(input_container, text='🚀 Ask', command=self._ask_ai_question,
                           bg='#00d4ff', fg='#1e1e2e', relief='flat',
                           font=('Segoe UI', 9, 'bold'), cursor='hand2',
                           padx=15, pady=5)
        ask_btn.pack(side='right', padx=(10, 0))
        
        # Notebook for tabbed content
        self.notebook = ttk.Notebook(content_frame)
        self.notebook.pack(fill='both', expand=True)
        
        # Configure notebook styling with better visibility
        style = ttk.Style()
        style.configure('TNotebook', background='#1e1e2e', borderwidth=0)
        
        # Unselected tabs - darker and more visible
        style.configure('TNotebook.Tab', 
                       background='#2d2d44',  # Darker background
                       foreground='#888888',  # Dimmed text
                       padding=[20, 8], 
                       font=('Segoe UI', 9, 'bold'),
                       borderwidth=1,
                       relief='flat')
        
        # Selected tab - bright and prominent
        style.map('TNotebook.Tab', 
                 background=[('selected', '#00d4ff')],  # Bright blue when selected
                 foreground=[('selected', '#1e1e2e')],  # Dark text for contrast
                 borderwidth=[('selected', 2)],
                 relief=[('selected', 'raised')])
        
        # Create tabs - AI Response, Insights, and Analytics
        self._create_ai_response_tab()
        self._create_insights_tab()
        self._create_analytics_tab()
        
    def _create_ai_response_tab(self):
        """AI Response tab with modern text display"""
        self.ai_tab = tk.Frame(self.notebook, bg='#1e1e2e')
        self.notebook.add(self.ai_tab, text='🤖 AI Response')
        
        # Response display area
        response_container = tk.Frame(self.ai_tab, bg='#1e1e2e')
        response_container.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Response text with scrollbar
        self.response_text = scrolledtext.ScrolledText(
            response_container, bg='#252540', fg='#ffffff',
            font=('Segoe UI', 10), relief='flat', bd=5,
            insertbackground='#00d4ff', selectbackground='#00d4ff',
            selectforeground='#1e1e2e', wrap='word'
        )
        self.response_text.pack(fill='both', expand=True)
        
        # Navigation controls
        nav_frame = tk.Frame(self.ai_tab, bg='#1e1e2e')
        nav_frame.pack(fill='x', padx=10, pady=(0, 10))
        
        self._create_nav_button(nav_frame, '◀ Previous', self._show_previous, 'left')
        
        self.response_counter = tk.Label(nav_frame, text='0 / 0', bg='#1e1e2e', fg='#00d4ff',
                                        font=('Segoe UI', 10, 'bold'))
        self.response_counter.pack(side='left', expand=True)
        
        self._create_nav_button(nav_frame, 'Next ▶', self._show_next, 'right')
        self._create_nav_button(nav_frame, '💾 Export', self._export_results, 'right')
        

        
    def _create_insights_tab(self):
        """AI Insights tab - for continuous monitoring and summaries only"""
        self.insights_tab = tk.Frame(self.notebook, bg='#1e1e2e')
        self.notebook.add(self.insights_tab, text='💡 Insights')
        
        self.insights_text = scrolledtext.ScrolledText(
            self.insights_tab, bg='#252540', fg='#ff6b00',
            font=('Segoe UI', 9), relief='flat', bd=5,
            insertbackground='#ff6b00', wrap='word'
        )
        self.insights_text.pack(fill='both', expand=True, padx=10, pady=10)
        
    def _create_analytics_tab(self):
        """Analytics tab - for all capture results and operational data"""
        self.analytics_tab = tk.Frame(self.notebook, bg='#1e1e2e')
        self.notebook.add(self.analytics_tab, text='📊 Analytics')
        
        self.analytics_text = scrolledtext.ScrolledText(
            self.analytics_tab, bg='#252540', fg='#00ff41',
            font=('Segoe UI', 9), relief='flat', bd=5,
            insertbackground='#00ff41', wrap='word'
        )
        self.analytics_text.pack(fill='both', expand=True, padx=10, pady=10)
        

        
    def _create_nav_button(self, parent, text, command, side):
        """Create navigation button"""
        btn = tk.Button(parent, text=text, command=command,
                       bg='#252540', fg='#ffffff', relief='flat',
                       font=('Segoe UI', 9), cursor='hand2',
                       padx=10, pady=5)
        btn.pack(side=side, padx=5)
        
        # Hover effects
        def on_enter(e):
            btn.configure(bg='#00d4ff', fg='#1e1e2e')
        def on_leave(e):
            btn.configure(bg='#252540', fg='#ffffff')
        
        btn.bind('<Enter>', on_enter)
        btn.bind('<Leave>', on_leave)
        
        return btn

    def _create_modern_status_bar(self):
        """Create modern status bar with translucent styling"""
        status_frame = tk.Frame(self.main_container, bg='#2d2d44', height=30)
        status_frame.pack(fill='x', pady=(1, 0))
        status_frame.pack_propagate(False)
        
        # Status text
        self.status_label = tk.Label(status_frame, text='🚀 HawkVance AI Ready - Advanced Mode Active', 
                                    bg='#2d2d44', fg='#00d4ff',
                                    font=('Segoe UI', 9))
        self.status_label.pack(side='left', padx=10, pady=5)
        
        # Progress indicator
        self.progress_label = tk.Label(status_frame, text='●', bg='#2d2d44', fg='#00ff41',
                                      font=('Segoe UI', 12))
        self.progress_label.pack(side='right', padx=10, pady=5)
        
        # CPU/Memory indicator
        self.system_label = tk.Label(status_frame, text='CPU: 0% | RAM: 0MB', 
                                    bg='#2d2d44', fg='#ffffff',
                                    font=('Segoe UI', 8))
        self.system_label.pack(side='right', padx=5, pady=5)
        
        # Start system monitoring
        self._update_system_info()

    def _setup_window_dragging(self):
        """Setup window dragging functionality"""
        pass  # Dragging is handled in title bar creation
        
    def _start_drag(self, event):
        """Start window dragging"""
        self.is_dragging = True
        self.drag_data['x'] = event.x
        self.drag_data['y'] = event.y
        
    def _on_drag(self, event):
        """Handle window dragging"""
        if self.is_dragging:
            x = self.winfo_x() + (event.x - self.drag_data['x'])
            y = self.winfo_y() + (event.y - self.drag_data['y'])
            self.geometry(f'+{x}+{y}')
            
    def _stop_drag(self, event):
        """Stop window dragging"""
        self.is_dragging = False
        
    def _minimize_window(self):
        """Minimize window - hide instead of iconify due to overrideredirect"""
        self.withdraw()  # Hide the window instead of iconify
        
    def _close_window(self):
        """Close application"""
        self.quit()
        
    def _toggle_settings(self):
        """Toggle settings panel"""
        messagebox.showinfo("Settings", "Settings panel coming soon!")
        
    def _update_capture_modes(self):
        """Update capture modes based on checkboxes"""
        active_modes = [mode for mode, var in self.capture_modes.items() if var.get()]
        self._update_status(f"Active modes: {', '.join(active_modes)}")
        
    def _smart_capture(self):
        """Perform smart capture with all enabled modes"""
        if not any(var.get() for var in self.capture_modes.values()):
            messagebox.showwarning("Warning", "Please enable at least one capture mode")
            return
            
        self._update_status("🧠 Performing smart capture...")
        threading.Thread(target=self._perform_smart_capture, daemon=True).start()
        
    def _toggle_auto_capture(self):
        """Toggle auto capture mode with real continuous monitoring"""
        self.auto_capture_enabled = not self.auto_capture_enabled
        if self.auto_capture_enabled:
            self._update_status("🔄 Auto capture enabled - Continuous monitoring started")
            self.capture_interval = 15  # Capture every 15 seconds for real monitoring
            self._start_auto_capture_timer()
        else:
            self._update_status("⏹️ Auto capture disabled - Continuous monitoring stopped")
            
    def _start_manual_capture(self):
        """Start manual capture mode with checkbox validation"""
        # Check if any capture modes are enabled
        enabled_modes = [mode for mode, var in self.capture_modes.items() if var.get()]
        if not enabled_modes:
            messagebox.showwarning("No Capture Modes Selected", 
                                 "Please enable at least one capture mode before starting capture.")
            return
        
        self.manual_capture_active = True
        self.start_capture_btn.configure(state='disabled')
        self.stop_capture_btn.configure(state='normal')
        
        if self.selected_region and self.advanced_capture:
            self.advanced_capture.set_region(*self.selected_region)
            
        # Start capture with enabled modes
        mode_list = ', '.join([mode.replace('_', ' ').title() for mode in enabled_modes])
        self._update_status(f"▶️ Manual capture started - Active: {mode_list}")
        
        # Perform initial capture immediately to show results
        threading.Thread(target=self._perform_initial_capture, daemon=True).start()
        
        # Start the timer for continuous capture
        self._start_manual_capture_timer()
    
    def _perform_initial_capture(self):
        """Perform immediate initial capture to show results"""
        try:
            enabled_modes = [mode for mode, var in self.capture_modes.items() if var.get()]
            self._perform_capture_with_modes(enabled_modes, is_initial=True)
        except Exception as e:
            logging.error(f"Initial capture error: {e}")
            self.after(0, lambda: self._update_status(f"❌ Initial capture failed: {str(e)}"))
    
    def _perform_capture_with_modes(self, enabled_modes: list, is_initial: bool = False):
        """Perform capture with specified modes and display results"""
        try:
            results = []
            captured_text = ""
            
            # Basic capture with OCR
            if 'basic' in enabled_modes:
                self.after(0, lambda: self._update_status("📷 Performing basic screen capture..."))
                try:
                    if self.advanced_capture:
                        import asyncio
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        capture_result = loop.run_until_complete(
                            self.advanced_capture.capture_with_analysis()
                        )
                        loop.close()
                        
                        if 'text_content' in capture_result and capture_result['text_content']:
                            captured_text = capture_result['text_content']
                            text_length = len(captured_text)
                            results.append(f"Basic capture: Extracted {text_length} characters of text")
                            
                            # Display in Insights tab instead of AI Response
                            if is_initial:
                                timestamp = time.strftime('%H:%M:%S')
                                region_info = f" [{self.region_info_text}]" if self.selected_region else " [Full Screen]"
                                response_text = f"📷 Basic Capture Results ({timestamp}){region_info}:\n\n"
                                response_text += f"Text Length: {text_length} characters\n\n"
                                response_text += f"Extracted Content:\n{captured_text[:500]}..."
                                
                                # Send to Analytics tab
                                self.after(0, lambda text=response_text: self._display_analytics(text))
                        else:
                            results.append("Basic capture completed (no text extracted)")
                            if is_initial:
                                self.after(0, lambda: self._display_analytics("📷 Basic capture completed but no text was extracted from the screen."))
                    else:
                        results.append("Basic capture: Advanced capture not available")
                        if is_initial:
                            self.after(0, lambda: self._display_analytics("⚠️ Advanced capture system not available"))
                except Exception as e:
                    results.append(f"Basic capture failed: {str(e)}")
                    if is_initial:
                        self.after(0, lambda err=str(e): self._display_analytics(f"❌ Basic capture failed: {err}"))
                        
            # Smart scrolling capture  
            if 'smart_scroll' in enabled_modes:
                self.after(0, lambda: self._update_status("📜 Performing smart scrolling capture..."))
                try:
                    if self.smart_scroller:
                        captures = self.smart_scroller.capture_with_smart_scrolling(max_scrolls=5)
                        if captures:
                            results.append(f"Smart scrolling: Captured {len(captures)} screens")
                            
                            # Extract text from all captures if OCR is available
                            if self.ocr_processor:
                                all_text = self.smart_scroller.extract_all_text(captures)
                                if all_text:
                                    captured_text += "\n\n=== SMART SCROLLING RESULTS ===\n" + all_text
                                    results.append(f"Smart scrolling: Extracted {len(all_text)} total characters")
                                    
                                    if is_initial:
                                        scroll_response = f"📜 Smart Scrolling Results ({time.strftime('%H:%M:%S')}):\n\n"
                                        scroll_response += f"Captured {len(captures)} screens\n"
                                        scroll_response += f"Total text length: {len(all_text)} characters\n\n"
                                        scroll_response += f"Content Preview:\n{all_text[:400]}..."
                                        # Send to Analytics tab
                                        self.after(0, lambda text=scroll_response: self._display_analytics(text))
                        else:
                            results.append("Smart scrolling: No content captured")
                            if is_initial:
                                self.after(0, lambda: self._display_analytics("📜 Smart scrolling completed but no new content was found"))
                    else:
                        results.append("Smart scrolling: Module not available")
                        if is_initial:
                            self.after(0, lambda: self._display_analytics("⚠️ Smart scrolling module not available"))
                except Exception as e:
                    results.append(f"Smart scrolling failed: {str(e)}")
                    if is_initial:
                        self.after(0, lambda err=str(e): self._display_analytics(f"❌ Smart scrolling failed: {err}"))
                        
            # Web content capture
            if 'web_content' in enabled_modes:
                self.after(0, lambda: self._update_status("🌐 Extracting web content..."))
                try:
                    # Use the enhanced web intelligence module
                    from ..core.web_intelligence import WebContentIntelligence
                    web_intel = WebContentIntelligence()
                    
                    # Extract content from current screen/browser
                    web_result = web_intel.extract_current_browser_content()
                    
                    if web_result.get('success', False):
                        # Analyze the content
                        analysis = web_intel.analyze_web_content(web_result)
                        
                        results.append(f"Web content extraction: Found {analysis.get('word_count', 0)} words")
                        if web_result.get('urls_found'):
                            results.append(f"Web content: Detected {len(web_result['urls_found'])} URLs")
                        
                        if is_initial:
                            web_response = f"🌐 Web Intelligence Results ({time.strftime('%H:%M:%S')}):\n\n"
                            web_response += f"Content Type: {analysis.get('content_type', 'Unknown')}\n"
                            web_response += f"Word Count: {analysis.get('word_count', 0)}\n"
                            web_response += f"URLs Found: {analysis.get('url_count', 0)}\n"
                            
                            if analysis.get('content_categories'):
                                web_response += f"Categories: {', '.join(analysis['content_categories'])}\n"
                            
                            if web_result.get('urls_found'):
                                web_response += f"\nURLs Detected:\n"
                                for url in web_result['urls_found'][:3]:  # Show first 3 URLs
                                    web_response += f"• {url}\n"
                            
                            web_response += f"\nSummary: {analysis.get('summary', 'No summary available')}"
                            web_response += f"\nConfidence: {analysis.get('confidence', 0):.0%}"
                            
                            # Send to Analytics tab
                            self.after(0, lambda text=web_response: self._display_analytics(text))
                    else:
                        error_msg = web_result.get('error', 'Unknown error')
                        results.append(f"Web content extraction failed: {error_msg}")
                        if is_initial:
                            self.after(0, lambda: self._display_analytics(f"🌐 Web intelligence: {error_msg}"))
                            
                except Exception as e:
                    results.append(f"Web content extraction failed: {str(e)}")
                    if is_initial:
                        self.after(0, lambda err=str(e): self._display_analytics(f"❌ Web content extraction failed: {err}"))
                        
            # Context-aware capture
            if 'context_aware' in enabled_modes:
                self.after(0, lambda: self._update_status("🧠 Analyzing context..."))
                try:
                    # Basic context analysis based on captured text
                    if captured_text:
                        context_analysis = self._analyze_context(captured_text)
                        results.append(f"Context analysis: {context_analysis}")
                        if is_initial:
                            context_response = f"🧠 Context Analysis ({time.strftime('%H:%M:%S')}):\n\n{context_analysis}"
                            # Send to Analytics tab
                            self.after(0, lambda text=context_response: self._display_analytics(text))
                    else:
                        results.append("Context analysis: No text available for analysis")
                        if is_initial:
                            self.after(0, lambda: self._display_analytics("🧠 Context analysis requires text content to analyze"))
                except Exception as e:
                    results.append(f"Context analysis failed: {str(e)}")
                    if is_initial:
                        self.after(0, lambda err=str(e): self._display_analytics(f"❌ Context analysis failed: {err}"))
                        
            # AI analysis
            if 'ai_analysis' in enabled_modes:
                self.after(0, lambda: self._update_status("🤖 Performing AI analysis..."))
                try:
                    if self.gemini_processor and captured_text:
                        # Analyze the captured content with AI
                        ai_prompt = f"Analyze this screen content and provide insights: {captured_text[:1000]}"
                        ai_result = self.gemini_processor.analyze_text(ai_prompt)
                        
                        if hasattr(ai_result, 'summary'):
                            ai_analysis = ai_result.summary
                        else:
                            ai_analysis = str(ai_result)
                            
                        results.append("AI analysis: Completed successfully")
                        if is_initial:
                            ai_response = f"🤖 AI Analysis ({time.strftime('%H:%M:%S')}):\n\n{ai_analysis}"
                            # Send to Analytics tab
                            self.after(0, lambda text=ai_response: self._display_analytics(text))
                    else:
                        if not self.gemini_processor:
                            results.append("AI analysis: Gemini processor not available")
                            if is_initial:
                                self.after(0, lambda: self._display_analytics("⚠️ AI analysis requires Gemini API configuration"))
                        else:
                            results.append("AI analysis: No content to analyze")
                            if is_initial:
                                self.after(0, lambda: self._display_analytics("🤖 AI analysis requires captured content to analyze"))
                except Exception as e:
                    results.append(f"AI analysis failed: {str(e)}")
                    if is_initial:
                        self.after(0, lambda err=str(e): self._display_analytics(f"❌ AI analysis failed: {err}"))
            
            # Update context tab with results summary
            if not is_initial:
                self.after(0, lambda: self._display_capture_results(results))
                
        except Exception as e:
            logging.error(f"Capture with modes error: {e}")
            self.after(0, lambda: self._update_status(f"❌ Capture error: {str(e)}"))
    
    def _analyze_context(self, text: str) -> str:
        """Enhanced context analysis from captured text with real application detection"""
        try:
            import psutil
            import win32gui
            import win32process
            
            word_count = len(text.split())
            char_count = len(text)
            
            # Get current active window information
            try:
                hwnd = win32gui.GetForegroundWindow()
                window_title = win32gui.GetWindowText(hwnd)
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                process = psutil.Process(pid)
                app_name = process.name()
                
                context_info = f"Active Application: {app_name}\n"
                context_info += f"Window Title: {window_title}\n"
            except:
                context_info = "Application detection: Not available\n"
                app_name = "unknown"
                window_title = ""
            
            # Enhanced content type detection
            content_type = "Unknown"
            activity_type = "General"
            
            # Application-based detection
            if "chrome" in app_name.lower() or "firefox" in app_name.lower() or "edge" in app_name.lower():
                content_type = "Web Browser"
                if any(word in text.lower() for word in ["search", "google", "results"]):
                    activity_type = "Web Search"
                elif any(word in text.lower() for word in ["email", "gmail", "inbox"]):
                    activity_type = "Email"
                elif any(word in text.lower() for word in ["youtube", "video", "play"]):
                    activity_type = "Video Streaming"
                else:
                    activity_type = "Web Browsing"
            elif "code" in app_name.lower() or "visual" in app_name.lower() or "studio" in app_name.lower():
                content_type = "Development Environment"
                activity_type = "Programming"
            elif "word" in app_name.lower() or "notepad" in app_name.lower():
                content_type = "Document Editor"
                activity_type = "Document Editing"
            elif "excel" in app_name.lower() or "calc" in app_name.lower():
                content_type = "Spreadsheet"
                activity_type = "Data Analysis"
            elif "outlook" in app_name.lower() or "mail" in app_name.lower():
                content_type = "Email Client"
                activity_type = "Email Management"
            
            # Text-based content detection (fallback/enhancement)
            if "http" in text.lower() or "www" in text.lower():
                if content_type == "Unknown":
                    content_type = "Web Content"
            elif any(word in text.lower() for word in ["function", "class", "import", "def", "var", "const"]):
                if content_type == "Unknown":
                    content_type = "Source Code"
                    activity_type = "Programming"
            elif any(word in text.lower() for word in ["document", "paragraph", "chapter", "section"]):
                if content_type == "Unknown":
                    content_type = "Document"
                    activity_type = "Reading/Writing"
            
            # Productivity analysis
            productivity_score = 0
            if activity_type in ["Programming", "Document Editing", "Data Analysis"]:
                productivity_score = 8
            elif activity_type in ["Email Management", "Web Search"]:
                productivity_score = 6
            elif activity_type in ["Reading/Writing", "Web Browsing"]:
                productivity_score = 5
            elif activity_type in ["Video Streaming"]:
                productivity_score = 2
            else:
                productivity_score = 4
            
            # Time-based analysis
            import datetime
            current_time = datetime.datetime.now()
            time_period = "Morning" if current_time.hour < 12 else "Afternoon" if current_time.hour < 18 else "Evening"
            
            analysis = context_info
            analysis += f"Content Type: {content_type}\n"
            analysis += f"Activity Type: {activity_type}\n"
            analysis += f"Time Period: {time_period}\n"
            analysis += f"Text Statistics:\n"
            analysis += f"  - Word Count: {word_count}\n"
            analysis += f"  - Character Count: {char_count}\n"
            analysis += f"  - Estimated Reading Time: {max(1, word_count // 200)} minutes\n"
            analysis += f"Productivity Score: {productivity_score}/10\n"
            
            # Context-aware suggestions
            suggestions = []
            if productivity_score < 5:
                suggestions.append("Consider focusing on more productive tasks")
            if word_count > 500:
                suggestions.append("Large amount of text detected - consider using AI analysis")
            if "error" in text.lower() or "exception" in text.lower():
                suggestions.append("Error detected - consider debugging assistance")
            if len(suggestions) > 0:
                analysis += f"\nSuggestions:\n"
                for suggestion in suggestions:
                    analysis += f"  • {suggestion}\n"
            
            return analysis  # Return the complete analysis
            
        except Exception as e:
            return f"Context analysis error: {str(e)}"
    
    def _display_immediate_response(self, response: str):
        """Display immediate response in AI Response tab"""
        self.response_history.append(response)
        self.current_response_index = len(self.response_history) - 1
        
        self.response_text.config(state='normal')
        self.response_text.insert(tk.END, response + "\n\n" + "="*50 + "\n\n")
        self.response_text.config(state='disabled')
        self.response_text.see(tk.END)
        
        self._update_response_counter()
    
    def _display_insights(self, insight_text: str):
        """Display insights in the Insights tab - ONLY for continuous monitoring and summaries"""
        self.insights_text.config(state='normal')
        self.insights_text.insert(tk.END, insight_text + "\n\n" + "="*50 + "\n\n")
        self.insights_text.config(state='disabled')
        self.insights_text.see(tk.END)
        
    def _display_analytics(self, analytics_text: str):
        """Display analytics data in the Analytics tab - for ALL capture results and operational data"""
        self.analytics_text.config(state='normal')
        self.analytics_text.insert(tk.END, analytics_text + "\n\n" + "="*50 + "\n\n")
        self.analytics_text.config(state='disabled')
        self.analytics_text.see(tk.END)
            
    def _stop_manual_capture(self):
        """Stop manual capture mode and all active capturing"""
        self.manual_capture_active = False
        self.auto_capture_enabled = False  # Also stop auto capture if active
        
        self.start_capture_btn.configure(state='normal')
        self.stop_capture_btn.configure(state='disabled')
        
        if self.advanced_capture:
            self.advanced_capture.stop_capture()  # Stop advanced capture
            self.advanced_capture.clear_region()  # Clear region but keep selection
            
        # Clear any ongoing processes
        self.after_cancel  # Cancel any pending after calls
        
        self._update_status("⏹️ All capture modes stopped")
        
        # Display final summary in Analytics tab
        final_response = f"⏹️ Capture Session Ended ({time.strftime('%H:%M:%S')})\n\n"
        final_response += "All active capture modes have been stopped.\n"
        final_response += f"Total responses captured: {len(self.response_history)}\n"
        final_response += "You can review previous captures using the navigation buttons."
        
        self.after(0, lambda: self._display_analytics(final_response))
            
    def _select_capture_region(self):
        """Open region selection dialog with enhanced functionality"""
        try:
            self._update_status("🎯 Preparing region selection - Click and drag to select area...")
            
            # Hide main window temporarily
            self.withdraw()
            
            # Small delay to ensure window is hidden
            time.sleep(0.2)
            
            if self.advanced_capture:
                region = self.advanced_capture.select_region()
                if region and region[2] > 0 and region[3] > 0:
                    self.selected_region = region
                    x, y, w, h = region
                    self.region_info_text = f"{w}x{h} at ({x},{y})"
                    self.region_info_label.config(text=f'Region: {self.region_info_text}')
                    
                    # Show immediate feedback with capture
                    self._update_status(f"✅ Region selected: {w}x{h} - Performing test capture...")
                    
                    # Perform immediate test capture to show what was selected
                    threading.Thread(target=self._test_region_capture, daemon=True).start()
                else:
                    self._update_status("❌ Region selection cancelled")
            else:
                self._update_status("❌ Advanced capture not available")
        except Exception as e:
            self._update_status(f"❌ Region selection failed: {str(e)}")
        finally:
            # Always restore main window
            self.after(100, self.deiconify)  # Small delay before showing window
    
    def _test_region_capture(self):
        """Perform a test capture of the selected region"""
        try:
            if self.selected_region and self.advanced_capture:
                # Set the region temporarily
                self.advanced_capture.set_region(*self.selected_region)
                
                # Perform a quick capture
                import asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                capture_result = loop.run_until_complete(
                    self.advanced_capture.capture_with_analysis()
                )
                loop.close()
                
                x, y, w, h = self.selected_region
                if 'text_content' in capture_result and capture_result['text_content']:
                    preview_text = capture_result['text_content'][:100] + "..." if len(capture_result['text_content']) > 100 else capture_result['text_content']
                    
                    test_response = f"🎯 Region Test Capture ({time.strftime('%H:%M:%S')}):\n\n"
                    test_response += f"Selected Area: {w}x{h} pixels at position ({x},{y})\n"
                    test_response += f"Text found: {len(capture_result['text_content'])} characters\n\n"
                    test_response += f"Content Preview:\n{preview_text}"
                    
                    # Clear the region setting after test
                    self.advanced_capture.clear_region()
                    
                    self.after(0, lambda text=test_response: self._display_analytics(text))
                    self.after(0, lambda: self._update_status(f"✅ Region ready - {w}x{h} area selected and tested"))
                else:
                    # Clear the region setting after test
                    self.advanced_capture.clear_region()
                    
                    test_response = f"🎯 Region Selected ({time.strftime('%H:%M:%S')}):\n\n"
                    test_response += f"Selected Area: {w}x{h} pixels at position ({x},{y})\n"
                    test_response += "No text detected in this region.\n\n"
                    test_response += "Region is ready for capture. Start capture to monitor this area."
                    
                    self.after(0, lambda text=test_response: self._display_analytics(text))
                    self.after(0, lambda: self._update_status(f"✅ Region ready - {w}x{h} area selected (no text detected)"))
                    
        except Exception as e:
            logging.error(f"Test region capture error: {e}")
            self.after(0, lambda: self._update_status(f"⚠️ Region test failed: {str(e)}"))
            
    def _start_manual_capture_timer(self):
        """Start manual capture timer"""
        if self.manual_capture_active:
            threading.Thread(target=self._perform_manual_capture, daemon=True).start()
            self.after(3000, self._start_manual_capture_timer)  # Every 3 seconds
            
    def _perform_manual_capture(self):
        """Perform manual capture using enabled modes only"""
        try:
            if not self.manual_capture_active:
                return
                
            # Get currently enabled modes
            enabled_modes = [mode for mode, var in self.capture_modes.items() if var.get()]
            if not enabled_modes:
                return
                
            # Perform capture with enabled modes
            self._perform_capture_with_modes(enabled_modes, is_initial=False)
                
        except Exception as e:
            logging.error(f"Manual capture error: {e}")
            
    def _update_manual_context(self, timestamp: str, summary: str):
        """Update Analytics tab with manual capture operational data"""
        region_info = f" [{self.region_info_text}]" if self.selected_region else " [Full Screen]"
        response_text = f"🔴 Manual Capture ({timestamp}){region_info}: {summary}"
        # Send to Analytics tab for operational data
        self._display_analytics(response_text)
            
    def _start_auto_capture_timer(self):
        """Start continuous auto capture timer with real monitoring"""
        if self.auto_capture_enabled:
            # Perform a smart capture in background
            threading.Thread(target=self._perform_background_capture, daemon=True).start()
            # Schedule next capture
            self.after(self.capture_interval * 1000, self._start_auto_capture_timer)
            
    def _perform_initial_background_capture(self):
        """Perform immediate first capture to show monitoring is active"""
        try:
            if not self.auto_capture_enabled:
                return
            
            self._update_status("🔍 HawkVance AI analyzing your current work...")
            self._perform_background_capture()
            
        except Exception as e:
            logging.error(f"Initial background capture error: {e}")
            
    def _perform_background_capture(self):
        """Enhanced background capture with real-time work understanding"""
        try:
            if not self.auto_capture_enabled:
                return
                
            # Capture current screen and analyze
            if self.advanced_capture:
                import asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                capture_result = loop.run_until_complete(
                    self.advanced_capture.capture_with_analysis()
                )
                loop.close()
                
                if 'text_content' in capture_result and capture_result['text_content']:
                    # Store in context history with enhanced analysis
                    timestamp = time.strftime('%H:%M:%S')
                    content_text = capture_result['text_content']
                    
                    # Enhanced context analysis
                    context_analysis = self._analyze_context(content_text)
                    
                    # Create comprehensive summary
                    content_summary = content_text[:150] + "..." if len(content_text) > 150 else content_text
                    
                    self.context_history.append({
                        'timestamp': timestamp,
                        'content': content_text,
                        'summary': content_summary,
                        'context_analysis': context_analysis,
                        'activity_detected': True
                    })
                    
                    # Update Insights tab with continuous monitoring (REAL-TIME INSIGHTS)
                    self.after(0, lambda: self._update_continuous_context(timestamp, content_summary, context_analysis))
                    
                    # Generate AI insights more frequently and contextually
                    if self.gemini_processor:
                        # Generate insights based on current activity type and user needs
                        self._generate_contextual_insights(content_text, context_analysis)
                        
                    # Keep only recent history to maintain performance
                    if len(self.context_history) > 20:
                        self.context_history = self.context_history[-15:]
                        
                else:
                    # Even with no text, track that monitoring is active
                    timestamp = time.strftime('%H:%M:%S')
                    self.after(0, lambda: self._display_insights(f"🕰️ HawkVance AI monitoring active ({timestamp}) - No text content detected"))
                    
        except Exception as e:
            logging.error(f"Background capture error: {e}")
            # Show error in Insights to indicate monitoring status
            self.after(0, lambda: self._display_insights(f"⚠️ Monitoring error at {time.strftime('%H:%M:%S')}: {str(e)}"))
            
    def _update_continuous_context(self, timestamp: str, summary: str, context_analysis: str = ""):
        """Update Insights tab with enhanced continuous monitoring summaries"""
        response_text = f"🕰️ Live Work Analysis ({timestamp}):\n\n"
        response_text += f"📝 Content: {summary}\n\n"
        
        if context_analysis:
            # Extract key information from context analysis
            lines = context_analysis.split('\n')
            for line in lines:
                if 'Active Application:' in line or 'Activity Type:' in line or 'Productivity Score:' in line:
                    response_text += f"{line}\n"
        
        # Send to Insights tab for continuous monitoring summaries
        self._display_insights(response_text)
        
    def _generate_contextual_insights(self, content_text: str, context_analysis: str):
        """Generate AI insights based on current context and activity"""
        try:
            # Extract activity type from context analysis for targeted insights
            activity_type = "General"
            for line in context_analysis.split('\n'):
                if 'Activity Type:' in line:
                    activity_type = line.split(':', 1)[1].strip()
                    break
            
            # Create targeted prompts based on activity
            if activity_type == "Programming":
                insight_prompt = f"You're coding. Based on this code/development content, provide a helpful programming insight or suggestion: {content_text[:300]}"
            elif activity_type == "Web Search" or activity_type == "Web Browsing":
                insight_prompt = f"You're browsing/researching. Based on this web content, provide research insights or suggest related topics: {content_text[:300]}"
            elif activity_type == "Document Editing" or activity_type == "Reading/Writing":
                insight_prompt = f"You're writing/reading documents. Based on this content, provide writing insights or suggestions: {content_text[:300]}"
            elif activity_type == "Email Management":
                insight_prompt = f"You're managing emails. Based on this content, provide productivity tips for email management: {content_text[:200]}"
            else:
                insight_prompt = f"Based on your current work activity, provide a helpful productivity insight: {content_text[:300]}"
            
            # Generate insights in background
            def generate_insight():
                try:
                    ai_result = self.gemini_processor.analyze_text(insight_prompt)
                    insight = ai_result.summary if hasattr(ai_result, 'summary') else str(ai_result)
                    
                    # Only show insights if they're meaningful
                    if insight and len(insight) > 20 and "error" not in insight.lower():
                        self.after(0, lambda i=insight, act=activity_type: self._display_contextual_insight(i, act))
                except Exception as e:
                    logging.warning(f"Contextual insight generation failed: {e}")
            
            # Generate insights every 2nd capture to avoid spam
            if len(self.context_history) % 2 == 0:
                threading.Thread(target=generate_insight, daemon=True).start()
                
        except Exception as e:
            logging.error(f"Contextual insight error: {e}")
            
    def _display_contextual_insight(self, insight: str, activity_type: str):
        """Display contextual AI insight in Insights tab"""
        insight_text = f"🎨 HawkVance AI Insight ({time.strftime('%H:%M:%S')}) - {activity_type}:\n"
        insight_text += "-" * 50 + "\n"
        insight_text += insight
        insight_text += "\n" + "-" * 50 + "\n"
        
        # Display in Insights tab
        self._display_insights(insight_text)
        
    def _show_monitoring_summary(self):
        """Show summary of the monitoring session"""
        if not self.context_history:
            summary = "📈 HawkVance AI Monitoring Session Ended\n\n"
            summary += "No activity was captured during this session.\n"
            summary += "Try enabling more capture modes or ensure screen content is visible."
        else:
            summary = f"📈 HawkVance AI Monitoring Session Summary\n\n"
            summary += f"🕰️ Duration: {len(self.context_history)} captures\n"
            summary += f"📄 Total content analyzed: {sum(len(item.get('content', '')) for item in self.context_history)} characters\n\n"
            
            # Show activity breakdown
            activities = {}
            for item in self.context_history:
                analysis = item.get('context_analysis', '')
                for line in analysis.split('\n'):
                    if 'Activity Type:' in line:
                        activity = line.split(':', 1)[1].strip()
                        activities[activity] = activities.get(activity, 0) + 1
                        break
            
            if activities:
                summary += "🎨 Activities Detected:\n"
                for activity, count in activities.items():
                    summary += f"  • {activity}: {count} times\n"
            
            summary += "\n🚀 HawkVance AI will resume monitoring when you restart Live Mode."
        
        self._display_insights(summary)
        
    def _show_welcome_monitoring_message(self):
        """Show welcome message about HawkVance AI continuous monitoring"""
        welcome_msg = f"🎆 Welcome to HawkVance AI - Intelligent Work Assistant\n\n"
        welcome_msg += f"🔍 LIVE MONITORING ACTIVE: HawkVance AI is now continuously analyzing your work\n"
        welcome_msg += f"🧠 Real-time insights will appear here as you work\n"
        welcome_msg += f"🚀 AI assistance is tailored to your current activity\n\n"
        welcome_msg += f"Monitoring started at {time.strftime('%H:%M:%S')}\n"
        welcome_msg += f"Capture interval: Every {self.capture_interval} seconds\n\n"
        welcome_msg += f"📊 Watch this space for productivity insights, suggestions, and contextual help!"
        
        self._display_insights(welcome_msg)
        
    def _display_productivity_insight(self, insight: str):
        """Display AI-generated productivity insight in Insights tab"""
        insight_text = f"💡 Productivity Insight ({time.strftime('%H:%M:%S')}):\n"
        insight_text += "-" * 40 + "\n"
        insight_text += insight
        insight_text += "\n" + "-" * 40 + "\n"
        
        # Keep in Insights tab for productivity insights
        self._display_insights(insight_text)
            
    def _show_analytics(self):
        """Show analytics window"""
        analytics_text = self._generate_analytics_report()
        
        # Create analytics window
        analytics_window = tk.Toplevel(self)
        analytics_window.title("HawkVance AI - Analytics")
        analytics_window.geometry("600x400")
        analytics_window.configure(bg='#1e1e2e')
        analytics_window.attributes('-alpha', 0.95)
        
        text_widget = scrolledtext.ScrolledText(
            analytics_window, bg='#252540', fg='#00d4ff',
            font=('Consolas', 9), relief='flat', bd=5
        )
        text_widget.pack(fill='both', expand=True, padx=10, pady=10)
        text_widget.insert('1.0', analytics_text)
        text_widget.config(state='disabled')
        
    def _ask_ai_question(self):
        """Process AI question"""
        question = self.question_entry.get().strip()
        if not question:
            return
            
        self.question_entry.delete(0, tk.END)
        self._update_status(f"🤖 Processing: {question[:30]}...")
        
        # Add to response area
        self.response_text.config(state='normal')
        self.response_text.insert(tk.END, f"\n🤔 Question: {question}\n")
        self.response_text.insert(tk.END, "🤖 HawkVance AI: Processing your question...\n\n")
        self.response_text.config(state='disabled')
        self.response_text.see(tk.END)
        
        # Process in background
        threading.Thread(target=self._process_ai_question, args=(question,), daemon=True).start()
        
    def _show_previous(self):
        """Show previous response"""
        if self.response_history and self.current_response_index > 0:
            self.current_response_index -= 1
            self._display_current_response()
            
    def _show_next(self):
        """Show next response"""
        if self.response_history and self.current_response_index < len(self.response_history) - 1:
            self.current_response_index += 1
            self._display_current_response()
            
    def _export_results(self):
        """Export current results"""
        if not self.response_history:
            messagebox.showinfo("Info", "No responses to export")
            return
            
        # Simple export to text file for now
        try:
            import os
            from datetime import datetime
            
            filename = f"hawkvance_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            filepath = os.path.join(os.path.expanduser('~'), 'Documents', filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write("HawkVance AI - Export Report\n")
                f.write("=" * 50 + "\n\n")
                
                for i, response in enumerate(self.response_history, 1):
                    f.write(f"Response {i}:\n")
                    f.write("-" * 20 + "\n")
                    f.write(response + "\n\n")
                    
            messagebox.showinfo("Export Complete", f"Results exported to:\n{filepath}")
            self._update_status(f"✅ Exported to {filename}")
            
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to export: {str(e)}")
            
    def initialize_components(self, screen_capture=None, ocr_processor=None, 
                            gemini_processor=None, text_processor=None, 
                            document_exporter=None):
        """Initialize advanced AI components"""
        try:
            # Store the components
            self.ocr_processor = ocr_processor
            self.gemini_processor = gemini_processor
            self.text_processor = text_processor
            self.document_exporter = document_exporter
            
            # Initialize advanced capture system
            if AdvancedScreenCapture:
                self.advanced_capture = AdvancedScreenCapture(gemini_api_key=GEMINI_API_KEY)
                self._update_status("✅ Advanced capture system initialized")
            
            # Initialize smart scrolling with OCR processor
            if SmartScrollingCapture:
                self.smart_scroller = SmartScrollingCapture(ocr_processor=self.ocr_processor)
                self._update_status("✅ Smart scrolling system initialized with OCR")
                
            # Initialize other components as needed
            self._update_status("🚀 All advanced systems ready")
            
        except Exception as e:
            import logging
            logging.error(f"Failed to initialize advanced components: {e}")
            self._update_status("⚠️ Running in basic mode")
            
    def _perform_smart_capture(self):
        """Perform smart capture with enabled modes using real functionality"""
        try:
            results = []
            
            # Basic capture with OCR
            if self.capture_modes['basic'].get():
                self._update_status("📷 Performing basic screen capture...")
                try:
                    if self.advanced_capture:
                        import asyncio
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        capture_result = loop.run_until_complete(
                            self.advanced_capture.capture_with_analysis()
                        )
                        loop.close()
                        
                        if 'text_content' in capture_result:
                            text_length = len(capture_result['text_content']) if capture_result['text_content'] else 0
                            results.append(f"Basic capture: Extracted {text_length} characters of text")
                            
                            # Store the text for display
                            if capture_result['text_content']:
                                self.after(0, lambda text=capture_result['text_content']: 
                                          self._display_screen_text(text))
                        else:
                            results.append("Basic capture completed (no text extracted)")
                    else:
                        results.append("Basic capture: Advanced capture not available")
                except Exception as e:
                    results.append(f"Basic capture failed: {str(e)}")
                    
            # Smart scrolling capture
            if self.capture_modes['smart_scroll'].get():
                self._update_status("📜 Performing smart scrolling capture...")
                try:
                    if self.smart_scroller:
                        captures = self.smart_scroller.capture_with_smart_scrolling(max_scrolls=5)
                        if captures:
                            results.append(f"Smart scrolling: Captured {len(captures)} screens")
                            
                            # Extract text from all captures
                            if self.ocr_processor:
                                all_text = self.smart_scroller.extract_all_text(captures)
                                if all_text:
                                    self.after(0, lambda text=all_text: 
                                              self._display_scrolled_text(text))
                                    results.append(f"Smart scrolling: Extracted {len(all_text)} total characters")
                        else:
                            results.append("Smart scrolling: No content captured")
                    else:
                        results.append("Smart scrolling: Module not available")
                except Exception as e:
                    results.append(f"Smart scrolling failed: {str(e)}")
                    
            # Web content capture
            if self.capture_modes['web_content'].get():
                self._update_status("🌐 Extracting web content...")
                results.append("Web content extraction: Module under development")
                
            # Context-aware capture
            if self.capture_modes['context_aware'].get():
                self._update_status("🧠 Analyzing context...")
                results.append("Context analysis: Module under development")
                
            # AI analysis
            if self.capture_modes['ai_analysis'].get():
                self._update_status("🤖 Performing AI analysis...")
                try:
                    if self.gemini_processor and results:
                        # Analyze the capture results
                        analysis_text = "\n".join(results)
                        ai_result = self.gemini_processor.analyze_text(
                            f"Analyze this screen capture session: {analysis_text}"
                        )
                        if hasattr(ai_result, 'summary'):
                            ai_analysis = ai_result.summary
                        else:
                            ai_analysis = str(ai_result)
                            
                        self.after(0, lambda analysis=ai_analysis: 
                                  self._display_ai_analysis(analysis))
                        results.append("AI analysis: Completed successfully")
                    else:
                        results.append("AI analysis: Processor not available")
                except Exception as e:
                    results.append(f"AI analysis failed: {str(e)}")
                
            # Update UI with results
            self.after(0, lambda: self._display_capture_results(results))
            
        except Exception as e:
            logging.error(f"Smart capture error: {e}")
            self.after(0, lambda: self._update_status(f"❌ Capture error: {str(e)}"))
            
    def _process_ai_question(self, question: str):
        """Process AI question in background using real Gemini AI"""
        try:
            # First, try to capture current screen content for context
            if self.advanced_capture:
                import asyncio
                try:
                    # Run async capture in thread
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    capture_result = loop.run_until_complete(
                        self.advanced_capture.capture_with_analysis(question)
                    )
                    loop.close()
                    
                    if 'text_content' in capture_result and capture_result['text_content']:
                        # Combine screen content with question
                        context = f"Screen content: {capture_result['text_content'][:1000]}..."
                        full_question = f"Question: {question}\n\nCurrent screen context: {context}"
                    else:
                        full_question = question
                        
                except Exception as e:
                    logging.warning(f"Screen capture failed, using question only: {e}")
                    full_question = question
            else:
                full_question = question
            
            # Use real Gemini AI if available
            response = None
            if self.gemini_processor:
                try:
                    logging.info(f"Processing question with Gemini: {question[:50]}...")
                    ai_result = self.gemini_processor.analyze_text(full_question)
                    logging.info(f"Gemini result type: {type(ai_result)}")
                    
                    if hasattr(ai_result, 'summary') and ai_result.summary:
                        response = ai_result.summary
                        logging.info("Using ai_result.summary")
                    elif hasattr(ai_result, 'content') and ai_result.content:
                        response = ai_result.content
                        logging.info("Using ai_result.content")
                    else:
                        response = str(ai_result)
                        logging.info("Using str(ai_result)")
                        
                    logging.info(f"Final response length: {len(response) if response else 0}")
                    
                except Exception as e:
                    logging.error(f"Gemini AI processing failed: {e}")
                    response = f"❌ AI Processing Error: {str(e)}\n\nQuestion: '{question}'\nPlease try again or check your Gemini API configuration."
            else:
                logging.error("Gemini processor is None!")
                response = "❌ Gemini AI processor is not initialized. Please check your API configuration."
            
            # Ensure we have a valid response before falling back
            if not response or response.strip() == "":
                logging.warning("Empty response from Gemini, using fallback")
                response = f"⚠️ No response generated\n\nQuestion: '{question}'\n\nThe AI system processed your question but didn't generate a response. Please try rephrasing your question."
            
            # Update UI
            self.after(0, lambda: self._display_ai_response(response))
            
        except Exception as e:
            logging.error(f"AI question processing error: {e}")
            error_response = f"Error processing question: {str(e)}\n\nPlease try again or check your AI configuration."
            self.after(0, lambda: self._display_ai_response(error_response))
            
    def _generate_ai_response(self, question: str) -> str:
        """Generate fallback response when Gemini AI is not available - should rarely be used"""
        return f"⚠️ Gemini AI Unavailable\n\nYour question: '{question}'\n\nThe AI processor is currently unavailable. Please check your internet connection and API configuration. This is a fallback response and not powered by AI."
        
    def _display_ai_response(self, response: str):
        """Display AI response in UI"""
        self.response_history.append(response)
        self.current_response_index = len(self.response_history) - 1
        
        self.response_text.config(state='normal')
        self.response_text.insert(tk.END, response + "\n\n")
        self.response_text.config(state='disabled')
        self.response_text.see(tk.END)
        
        self._update_response_counter()
        self._update_status("✅ AI response generated")
        
    def _display_current_response(self):
        """Display current response from history"""
        if self.response_history and 0 <= self.current_response_index < len(self.response_history):
            response = self.response_history[self.current_response_index]
            
            self.response_text.config(state='normal')
            self.response_text.delete('1.0', tk.END)
            self.response_text.insert('1.0', response)
            self.response_text.config(state='disabled')
            
            self._update_response_counter()
            
    def _update_response_counter(self):
        """Update response counter display"""
        if self.response_history:
            current = self.current_response_index + 1
            total = len(self.response_history)
            self.response_counter.config(text=f"{current} / {total}")
        else:
            self.response_counter.config(text="0 / 0")
            
    def _display_capture_results(self, results: List[str]):
        """Display capture results in Analytics tab"""
        results_text = f"🕒 Capture Results ({time.strftime('%H:%M:%S')}):\n\n"
        for result in results:
            results_text += f"✅ {result}\n"
        
        # Send to Analytics tab instead of Insights
        self._display_analytics(results_text)
        self._update_status("✅ Smart capture completed")
        
    def _display_screen_text(self, text: str):
        """Display extracted screen text in Analytics tab"""
        response_text = f"🕒 Screen Text Extracted ({time.strftime('%H:%M:%S')}):\n\n"
        response_text += f"Length: {len(text)} characters\n"
        response_text += f"Preview: {text[:200]}..."
        
        # Send to Analytics tab
        self._display_analytics(response_text)
        
    def _display_scrolled_text(self, text: str):
        """Display smart scrolling extracted text in Analytics tab"""
        self.analytics_text.config(state='normal')
        self.analytics_text.insert(tk.END, f"\n📜 Smart Scrolling Results ({time.strftime('%H:%M:%S')}):\n")
        self.analytics_text.insert(tk.END, f"Total content length: {len(text)} characters\n")
        self.analytics_text.insert(tk.END, "\n--- Full Content ---\n")
        self.analytics_text.insert(tk.END, text)
        self.analytics_text.insert(tk.END, "\n--- End Content ---\n\n")
        self.analytics_text.config(state='disabled')
        self.analytics_text.see(tk.END)
        
    def _display_ai_analysis(self, analysis: str):
        """Display AI analysis in Analytics tab"""
        self.analytics_text.config(state='normal')
        self.analytics_text.insert(tk.END, f"\n🤖 AI Analysis ({time.strftime('%H:%M:%S')}):\n")
        self.analytics_text.insert(tk.END, "=" * 50 + "\n")
        self.analytics_text.insert(tk.END, analysis)
        self.analytics_text.insert(tk.END, "\n" + "=" * 50 + "\n\n")
        self.analytics_text.config(state='disabled')
        self.analytics_text.see(tk.END)
        
    def _start_auto_capture_timer(self):
        """Start auto capture timer"""
        if self.auto_capture_enabled:
            self._smart_capture()
            self.after(self.capture_interval * 1000, self._start_auto_capture_timer)
            
    def _update_status(self, message: str):
        """Update status bar"""
        self.status_label.config(text=message)
        
    def _update_system_info(self):
        """Update system information"""
        try:
            import psutil
            cpu_percent = psutil.cpu_percent()
            memory_info = psutil.virtual_memory()
            memory_mb = int(memory_info.used / 1024 / 1024)
            
            self.system_label.config(text=f"CPU: {cpu_percent:.1f}% | RAM: {memory_mb}MB")
        except ImportError:
            self.system_label.config(text="System info unavailable")
        except Exception as e:
            self.system_label.config(text="System monitoring error")
            
        # Update every 5 seconds
        self.after(5000, self._update_system_info)
        
    def _generate_analytics_report(self) -> str:
        """Generate analytics report"""
        report = "🔍 HawkVance AI - Analytics Report\n"
        report += "=" * 50 + "\n\n"
        
        report += f"📊 Session Statistics:\n"
        report += f"• Total AI Responses: {len(self.response_history)}\n"
        report += f"• Active Capture Modes: {sum(1 for var in self.capture_modes.values() if var.get())}\n"
        report += f"• Auto Capture: {'Enabled' if self.auto_capture_enabled else 'Disabled'}\n\n"
        
        report += "🎯 Active Features:\n"
        for mode, var in self.capture_modes.items():
            status = "✅" if var.get() else "❌"
            report += f"{status} {mode.replace('_', ' ').title()}\n"
            
        report += "\n💡 Advanced Capabilities:\n"
        report += "✅ Translucent Professional UI\n"
        report += "✅ Smart Scrolling Capture\n"
        report += "✅ Multi-Modal AI Analysis\n"
        report += "✅ Context Awareness\n"
        report += "✅ Web Content Intelligence\n"
        report += "✅ Real-time System Monitoring\n"
        
        return report

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
        """Handle question submission - redirect to main ask method"""
        if hasattr(self, 'input_entry'):
            question = self.input_entry.get().strip()
            if question:
                self.input_entry.delete(0, tk.END)
                # Use the main ask AI question method
                self._process_question_for_display(question)
                threading.Thread(target=self._process_ai_question, args=(question,), daemon=True).start()
        
    def _process_question_for_display(self, question: str):
        """Display question in AI Response tab immediately"""
        self._update_status(f"🤖 Processing: {question[:30]}...")
        
        # Add to AI Response tab
        self.response_text.config(state='normal')
        self.response_text.insert(tk.END, f"\n🤔 Question: {question}\n")
        self.response_text.insert(tk.END, "🤖 HawkVance AI: Processing your question...\n\n")
        self.response_text.config(state='disabled')
        self.response_text.see(tk.END)

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