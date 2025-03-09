import re
from typing import List, Optional
from dataclasses import dataclass

@dataclass
class ProcessedText:
    original: str
    cleaned: str
    sentences: List[str]
    word_count: int
    has_questions: bool

class TextProcessor:
    def __init__(self):
        self.question_pattern = re.compile(r'\b(who|what|when|where|why|how)\b|[?]', re.IGNORECASE)
        
    def process_text(self, text: str) -> ProcessedText:
        """Process and analyze the input text"""
        if not text:
            return ProcessedText("", "", [], 0, False)
            
        # Clean the text
        cleaned = self._clean_text(text)
        
        # Split into sentences
        sentences = self._split_sentences(cleaned)
        
        # Count words
        word_count = self._count_words(cleaned)
        
        # Check for questions
        has_questions = bool(self.question_pattern.search(cleaned))
        
        return ProcessedText(
            original=text,
            cleaned=cleaned,
            sentences=sentences,
            word_count=word_count,
            has_questions=has_questions
        )
        
    def _clean_text(self, text: str) -> str:
        """Clean and normalize the input text"""
        # Remove common web/system elements
        patterns_to_remove = [
            r'https?://\S+',                    # URLs
            r'www\.\S+',                        # Web addresses
            r'^\s*\d+\s*$',                     # Standalone numbers
            r'©.*$',                            # Copyright lines
            r'Page \d+ of \d+',                 # Page numbers
            r'Search\s*$',                      # Search text
            r'Menu\s*$',                        # Menu text
            r'Home\s*$',                        # Navigation items
            r'filepath:.*$',                    # File paths
            r'PS C:\\.*>',                      # PowerShell prompts
            r'\[.*?\]',                         # Square bracket content
            r'Click here.*$',                   # Click here texts
            r'^\s*\d+\.\s*$',                  # Standalone numbering
            r'Share\s*$',                       # Share buttons
            r'Follow\s*$',                      # Follow buttons
        ]
        
        # Apply all cleanup patterns
        cleaned = text
        for pattern in patterns_to_remove:
            cleaned = re.sub(pattern, '', cleaned, flags=re.MULTILINE|re.IGNORECASE)
        
        # Split into lines and keep only meaningful content
        lines = []
        for line in cleaned.split('\n'):
            line = line.strip()
            # Keep line if it has enough content
            if len(line) > 5 and re.search(r'[A-Za-z]{3,}', line):
                lines.append(line)
        
        # Rejoin cleaned lines
        cleaned = ' '.join(lines)
        
        # Fix spacing around punctuation
        cleaned = re.sub(r'\s+([.,!?])', r'\1', cleaned)
        cleaned = re.sub(r'([.,!?])(?=[^\s])', r'\1 ', cleaned)
        
        return cleaned.strip()
        
    def _split_sentences(self, text: str) -> List[str]:
        """Split text into sentences"""
        # Basic sentence splitting
        sentences = re.split(r'(?<=[.!?])\s+', text)
        return [s.strip() for s in sentences if s.strip()]
        
    def _count_words(self, text: str) -> int:
        """Count words in text"""
        return len(text.split())

    def extract_questions(self, text: str) -> List[str]:
        """Extract questions from text"""
        sentences = self._split_sentences(text)
        questions = []
        
        for sentence in sentences:
            if self.question_pattern.search(sentence):
                questions.append(sentence)
                
        return questions