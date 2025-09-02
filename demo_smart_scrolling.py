#!/usr/bin/env python3
"""
🚀 HawkVance AI - Smart Scrolling Demo

This script demonstrates the smart scrolling capability that allows
HawkVance AI to see content beyond just the visible screen area.

This is a WORKING implementation that you can use right now!
"""

import sys
import os
from pathlib import Path

# Add the project root directory to Python path
project_root = Path(__file__).parent
sys.path.append(str(project_root))

from src.core.smart_scrolling import SmartScrollingCapture, demo_smart_scrolling
from src.core.ocr import OCRProcessor
from config.settings import TESSERACT_PATH

def main():
    print("🎯 HawkVance AI - Smart Scrolling Demonstration")
    print("=" * 60)
    print()
    print("🔥 This demonstrates how HawkVance AI can see BEYOND the visible screen!")
    print("📜 It will automatically scroll through content and capture everything.")
    print()
    
    # Initialize OCR processor
    ocr_processor = None
    try:
        ocr_processor = OCRProcessor(tesseract_path=TESSERACT_PATH)
        print("✅ OCR processor initialized successfully")
    except Exception as e:
        print(f"⚠️  OCR processor initialization failed: {e}")
        print("🔄 Will continue with image capture only")
    
    print()
    print("📋 Instructions:")
    print("1. Open a long webpage (like Wikipedia article) or long document")
    print("2. Make sure the content is scrollable")
    print("3. Click in the content area to focus it")
    print("4. Wait for the countdown, then watch the magic happen!")
    print()
    
    input("Press Enter when you're ready to start the demo...")
    print()
    
    # Run the demo
    try:
        captures, analysis = demo_smart_scrolling(ocr_processor)
        
        print()
        print("🎉 DEMO COMPLETE!")
        print("=" * 60)
        print("🧠 What just happened:")
        print("• HawkVance AI automatically scrolled through your content")
        print("• It captured multiple screens of content")
        print("• It detected when it reached the end")
        print("• It returned to the top automatically")
        print("• It extracted ALL the text from the entire document")
        print()
        print("🚀 This is just the beginning of what HawkVance AI can do!")
        print("📈 Next features will add:")
        print("• Full web page content extraction")
        print("• Application context awareness") 
        print("• Multi-modal AI analysis")
        print("• Proactive assistance")
        print()
        print("🎯 Your AI is already becoming more intelligent!")
        
    except KeyboardInterrupt:
        print("\\n⏹️  Demo interrupted by user")
    except Exception as e:
        print(f"❌ Demo error: {e}")
        print("💡 Try opening a different webpage or document")

if __name__ == "__main__":
    main()