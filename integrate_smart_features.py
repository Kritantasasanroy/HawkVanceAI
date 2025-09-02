#!/usr/bin/env python3
"""
🔧 HawkVance AI - Smart Features Integration

This script shows how to integrate the new smart scrolling feature
into your existing HawkVance AI application.
"""

import sys
import os
from pathlib import Path

# Add the project root directory to Python path
project_root = Path(__file__).parent
sys.path.append(str(project_root))

from src.core.smart_scrolling import SmartScrollingCapture
from src.core.ocr import OCRProcessor
from src.core.gemini_api import GeminiProcessor
from config.settings import TESSERACT_PATH, GEMINI_API_KEY

class EnhancedHawkVanceAI:
    """
    Enhanced version of HawkVance AI with smart scrolling capabilities
    """
    
    def __init__(self):
        # Initialize core components
        self.ocr_processor = OCRProcessor(tesseract_path=TESSERACT_PATH)
        self.gemini_processor = GeminiProcessor()
        self.smart_scroller = SmartScrollingCapture(self.ocr_processor)
        
        print("🚀 Enhanced HawkVance AI initialized with smart scrolling!")
    
    def analyze_page_comprehensive(self, question: str = None):
        """
        Comprehensive page analysis using smart scrolling
        """
        print("🧠 Starting comprehensive page analysis...")
        print("📜 Capturing all content (including scrolled areas)...")
        
        # Capture all content using smart scrolling
        captures = self.smart_scroller.capture_with_smart_scrolling(
            target_text=question if question else None,
            max_scrolls=15
        )
        
        # Extract all text
        all_text = self.smart_scroller.extract_all_text(captures)
        
        # Analyze content structure
        analysis = self.smart_scroller.analyze_content_structure(captures)
        
        print(f"✅ Captured {analysis['total_captures']} screens")
        print(f"📝 Extracted {len(all_text)} characters of text")
        
        # Send to Gemini for AI analysis
        if question:
            prompt = f"""
            Based on this comprehensive content from the entire page/document:
            
            {all_text[:8000]}  # Limit for API
            
            Question: {question}
            
            Please provide a detailed answer based on ALL the content, including information that might be below the visible screen area.
            """
        else:
            prompt = f"""
            Please analyze this comprehensive content from the entire page/document:
            
            {all_text[:8000]}
            
            Provide:
            1. A summary of the main topics
            2. Key insights or important information
            3. Any actionable recommendations
            4. Notable patterns or themes
            """
        
        print("🤖 Sending to Gemini AI for analysis...")
        result = self.gemini_processor.analyze_text(prompt)
        
        return {
            'captures': captures,
            'extracted_text': all_text,
            'structure_analysis': analysis,
            'ai_response': result
        }
    
    def smart_search(self, search_term: str):
        """
        Search for specific content by scrolling through the page
        """
        print(f"🔍 Smart searching for: '{search_term}'")
        
        captures = self.smart_scroller.capture_with_smart_scrolling(
            target_text=search_term,
            max_scrolls=20
        )
        
        all_text = self.smart_scroller.extract_all_text(captures)
        
        # Find occurrences of search term
        occurrences = []
        lines = all_text.split('\n')
        for i, line in enumerate(lines):
            if search_term.lower() in line.lower():
                occurrences.append({
                    'line_number': i,
                    'content': line.strip(),
                    'context': '\n'.join(lines[max(0, i-2):i+3])
                })
        
        print(f"✅ Found {len(occurrences)} occurrences of '{search_term}'")
        
        if occurrences:
            # Send to Gemini for contextual analysis
            context_info = '\n'.join([occ['context'] for occ in occurrences[:3]])
            prompt = f"""
            I searched for "{search_term}" and found these contexts:
            
            {context_info}
            
            Please provide:
            1. A summary of what this search term refers to in this content
            2. The key information related to this term
            3. Any relevant insights or connections
            """
            
            result = self.gemini_processor.analyze_text(prompt)
            
            return {
                'search_term': search_term,
                'occurrences': occurrences,
                'ai_analysis': result
            }
        else:
            return {
                'search_term': search_term,
                'occurrences': [],
                'ai_analysis': f"No occurrences of '{search_term}' found in the content."
            }

def demo_enhanced_features():
    """
    Demonstrate the enhanced features
    """
    print("🎯 Enhanced HawkVance AI Demo")
    print("=" * 50)
    print()
    
    try:
        # Initialize enhanced AI
        ai = EnhancedHawkVanceAI()
        print()
        
        print("🔥 Available Enhanced Features:")
        print("1. Comprehensive page analysis (sees ALL content)")
        print("2. Smart search (finds content anywhere on page)")
        print("3. AI-powered insights from complete content")
        print()
        
        while True:
            print("📋 Choose an option:")
            print("1. Comprehensive Analysis")
            print("2. Smart Search")
            print("3. Ask a Question")
            print("4. Exit")
            
            choice = input("Enter your choice (1-4): ").strip()
            print()
            
            if choice == "1":
                print("📊 Starting comprehensive analysis...")
                print("⏰ Make sure you have a long webpage or document open")
                input("Press Enter to continue...")
                
                result = ai.analyze_page_comprehensive()
                print("\\n🎉 Analysis Complete!")
                print(f"Summary: {result['ai_response'].summary}")
                
            elif choice == "2":
                search_term = input("🔍 Enter search term: ").strip()
                if search_term:
                    result = ai.smart_search(search_term)
                    print(f"\\n✅ Search complete! Found {len(result['occurrences'])} occurrences")
                    if result['ai_analysis']:
                        print(f"AI Analysis: {result['ai_analysis'].summary}")
                
            elif choice == "3":
                question = input("❓ Enter your question: ").strip()
                if question:
                    result = ai.analyze_page_comprehensive(question)
                    print(f"\\n🤖 AI Response: {result['ai_response'].summary}")
                
            elif choice == "4":
                print("👋 Goodbye!")
                break
            
            print("\\n" + "-" * 50 + "\\n")
            
    except KeyboardInterrupt:
        print("\\n⏹️  Demo interrupted")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    demo_enhanced_features()