import win32gui
import win32process
import win32api
import win32con
import psutil
import time
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import logging
import json
import sqlite3
from pathlib import Path
import threading
from collections import defaultdict
import pygetwindow as gw
import pyautogui
import cv2
import numpy as np

@dataclass
class ApplicationContext:
    process_name: str
    window_title: str
    window_handle: int
    pid: int
    executable_path: str
    working_directory: str
    command_line: str
    memory_usage: int
    cpu_percent: float
    window_rect: Tuple[int, int, int, int]
    is_focused: bool
    timestamp: float

@dataclass
class ContentContext:
    application: ApplicationContext
    visible_text: str
    hidden_text: str  # Text from scrolled areas, menus, etc.
    ui_elements: List[Dict]
    file_paths: List[str]
    urls: List[str]
    recent_actions: List[str]

class ContextAwarenessSystem:
    """Advanced system for understanding application context and extracting comprehensive content"""
    
    def __init__(self):
        self.db_path = Path("hawkvance_context.db")
        self.init_database()
        self.application_monitors = {}
        self.content_cache = {}
        
    def init_database(self):
        """Initialize SQLite database for context storage"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS application_context (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL,
                    process_name TEXT,
                    window_title TEXT,
                    content_summary TEXT,
                    full_content TEXT,
                    metadata TEXT
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_actions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL,
                    action_type TEXT,
                    application TEXT,
                    description TEXT,
                    metadata TEXT
                )
            """)
    
    def get_active_application_context(self) -> Optional[ApplicationContext]:
        """Get comprehensive context of the currently active application"""
        try:
            # Get foreground window
            hwnd = win32gui.GetForegroundWindow()
            if not hwnd:
                return None
            
            # Get window title
            window_title = win32gui.GetWindowText(hwnd)
            
            # Get process ID
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            
            # Get process information
            try:
                process = psutil.Process(pid)
                process_name = process.name()
                executable_path = process.exe()
                working_directory = process.cwd()
                command_line = ' '.join(process.cmdline())
                memory_usage = process.memory_info().rss
                cpu_percent = process.cpu_percent()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                return None
            
            # Get window rectangle
            window_rect = win32gui.GetWindowRect(hwnd)
            
            return ApplicationContext(
                process_name=process_name,
                window_title=window_title,
                window_handle=hwnd,
                pid=pid,
                executable_path=executable_path,
                working_directory=working_directory,
                command_line=command_line,
                memory_usage=memory_usage,
                cpu_percent=cpu_percent,
                window_rect=window_rect,
                is_focused=True,
                timestamp=time.time()
            )
            
        except Exception as e:
            logging.error(f"Error getting application context: {e}")
            return None
    
    def extract_comprehensive_content(self, app_context: ApplicationContext) -> ContentContext:
        """Extract all available content from the application"""
        
        visible_text = ""
        hidden_text = ""
        ui_elements = []
        file_paths = []
        urls = []
        recent_actions = []
        
        try:
            # Extract visible content using OCR
            visible_text = self._extract_visible_text(app_context.window_handle)
            
            # Extract hidden content based on application type
            if self._is_browser(app_context.process_name):
                hidden_text, urls = self._extract_browser_content(app_context)
            elif self._is_text_editor(app_context.process_name):
                hidden_text, file_paths = self._extract_editor_content(app_context)
            elif self._is_file_manager(app_context.process_name):
                hidden_text, file_paths = self._extract_file_manager_content(app_context)
            else:
                hidden_text = self._extract_generic_content(app_context)
            
            # Extract UI elements
            ui_elements = self._extract_ui_elements(app_context.window_handle)
            
            # Get recent actions for this application
            recent_actions = self._get_recent_actions(app_context.process_name)
            
        except Exception as e:
            logging.error(f"Error extracting comprehensive content: {e}")
        
        return ContentContext(
            application=app_context,
            visible_text=visible_text,
            hidden_text=hidden_text,
            ui_elements=ui_elements,
            file_paths=file_paths,
            urls=urls,
            recent_actions=recent_actions
        )
    
    def _extract_visible_text(self, window_handle: int) -> str:
        """Extract visible text from window using OCR"""
        try:
            rect = win32gui.GetWindowRect(window_handle)
            screenshot = pyautogui.screenshot(region=(rect[0], rect[1], 
                                                    rect[2] - rect[0], rect[3] - rect[1]))
            
            # Convert to OpenCV format for OCR
            image = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
            
            # This would integrate with your existing OCR processor
            # For now, return placeholder
            return "Visible text extracted via OCR"
            
        except Exception as e:
            logging.error(f"Error extracting visible text: {e}")
            return ""
    
    def _is_browser(self, process_name: str) -> bool:
        """Check if process is a web browser"""
        browsers = ['chrome.exe', 'firefox.exe', 'edge.exe', 'safari.exe', 'opera.exe']
        return any(browser in process_name.lower() for browser in browsers)
    
    def _is_text_editor(self, process_name: str) -> bool:
        """Check if process is a text editor"""
        editors = ['notepad.exe', 'code.exe', 'notepad++.exe', 'sublime_text.exe', 'atom.exe']
        return any(editor in process_name.lower() for editor in editors)
    
    def _is_file_manager(self, process_name: str) -> bool:
        """Check if process is a file manager"""
        managers = ['explorer.exe', 'totalcmd.exe']
        return any(manager in process_name.lower() for manager in managers)
    
    def _extract_browser_content(self, app_context: ApplicationContext) -> Tuple[str, List[str]]:
        """Extract content from web browser"""
        # This would integrate with the WebContentIntelligence system
        # For now, return placeholder
        return "Browser content would be extracted here", ["http://example.com"]
    
    def _extract_editor_content(self, app_context: ApplicationContext) -> Tuple[str, List[str]]:
        """Extract content from text editor"""
        # This could use automation to access the editor's content
        # For now, return placeholder
        return "Editor content would be extracted here", ["/path/to/file.txt"]
    
    def _extract_file_manager_content(self, app_context: ApplicationContext) -> Tuple[str, List[str]]:
        """Extract content from file manager"""
        # This could access the current directory listing
        try:
            current_dir = app_context.working_directory
            files = list(Path(current_dir).glob("*"))
            file_list = [str(f) for f in files[:20]]  # Limit to first 20 files
            content = f"Current directory: {current_dir}\nFiles: {', '.join([f.name for f in files[:10]])}"
            return content, file_list
        except Exception as e:
            logging.error(f"Error extracting file manager content: {e}")
            return "", []
    
    def _extract_generic_content(self, app_context: ApplicationContext) -> str:
        """Extract content from generic application"""
        # This could use accessibility APIs or other methods
        return f"Generic content from {app_context.process_name}"
    
    def _extract_ui_elements(self, window_handle: int) -> List[Dict]:
        """Extract UI elements from window"""
        # This would use UI Automation or similar APIs
        # For now, return placeholder
        return [{"type": "button", "text": "Example Button", "position": (100, 200)}]
    
    def _get_recent_actions(self, process_name: str) -> List[str]:
        """Get recent user actions for this application"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("""
                    SELECT description FROM user_actions 
                    WHERE application = ? 
                    ORDER BY timestamp DESC 
                    LIMIT 10
                """, (process_name,))
                return [row[0] for row in cursor.fetchall()]
        except Exception as e:
            logging.error(f"Error getting recent actions: {e}")
            return []
    
    def log_user_action(self, action_type: str, application: str, description: str, metadata: Dict = None):
        """Log user action for context building"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO user_actions (timestamp, action_type, application, description, metadata)
                    VALUES (?, ?, ?, ?, ?)
                """, (time.time(), action_type, application, description, json.dumps(metadata or {})))
        except Exception as e:
            logging.error(f"Error logging user action: {e}")
    
    def store_context(self, content_context: ContentContext):
        """Store context in database for learning and analysis"""
        try:
            app = content_context.application
            full_content = f"""
            Visible Text: {content_context.visible_text}
            Hidden Text: {content_context.hidden_text}
            UI Elements: {json.dumps(content_context.ui_elements)}
            File Paths: {', '.join(content_context.file_paths)}
            URLs: {', '.join(content_context.urls)}
            Recent Actions: {', '.join(content_context.recent_actions)}
            """
            
            metadata = {
                'window_rect': app.window_rect,
                'memory_usage': app.memory_usage,
                'cpu_percent': app.cpu_percent,
                'executable_path': app.executable_path
            }
            
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO application_context 
                    (timestamp, process_name, window_title, content_summary, full_content, metadata)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    app.timestamp,
                    app.process_name,
                    app.window_title,
                    content_context.visible_text[:500],  # Summary
                    full_content,
                    json.dumps(metadata)
                ))
                
        except Exception as e:
            logging.error(f"Error storing context: {e}")
    
    def get_context_history(self, hours: int = 24) -> List[Dict]:
        """Get context history for analysis"""
        try:
            cutoff_time = time.time() - (hours * 3600)
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("""
                    SELECT * FROM application_context 
                    WHERE timestamp > ? 
                    ORDER BY timestamp DESC
                """, (cutoff_time,))
                
                columns = [description[0] for description in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]
                
        except Exception as e:
            logging.error(f"Error getting context history: {e}")
            return []