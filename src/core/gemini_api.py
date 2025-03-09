import logging
from typing import Optional, List
import google.generativeai as genai
from dataclasses import dataclass
import os

# Update API key
GEMINI_API_KEY = "AIzaSyBz18SaAgyflzCjHzJfXMQXwjxo7Jgw8j4"

@dataclass
class AnalysisResult:
    summary: str
    questions: List[str]
    answers: List[str]
    error: Optional[str] = None

class GeminiProcessor:
    def __init__(self):
        try:
            # Configure with new API key
            genai.configure(api_key=GEMINI_API_KEY)
            # Update model to Gemini 2.0
            self.model = genai.GenerativeModel("models/gemini-2.0-flash")
            # Configure model parameters
            self.generation_config = {
                'temperature': 0.7,
                'top_p': 0.8,
                'top_k': 40,
                'max_output_tokens': 2048,
            }
            logging.info("Gemini 2.0 API initialized successfully")
        except Exception as e:
            logging.error(f"Failed to initialize Gemini API: {str(e)}")
            raise RuntimeError("Failed to initialize Gemini API")

    def _construct_prompt(self, text: str) -> str:
        """Construct appropriate prompt based on content type"""
        # Enhanced question detection
        has_question = ('?' in text or 
                       any(word in text.lower() for word in ['what', 'who', 'when', 'where', 'why', 'how']) or
                       any(phrase in text.lower() for phrase in ['explain', 'tell me', 'describe', 'define', 'summarize']))
        
        if has_question:
            prompt = (
                "You are a knowledgeable AI assistant. Provide a comprehensive response that includes "
                "both detailed answers and statistical information.\n\n"
                "Format your response as:\n\n"
                "MAIN ANSWER:\n"
                "[Clear, direct answer to the question]\n\n"
                "KEY FACTS & STATISTICS:\n"
                "📊 [Important statistic/fact 1]\n"
                "📊 [Important statistic/fact 2]\n"
                "📊 [Important statistic/fact 3]\n\n"
                "DETAILED EXPLANATION:\n"
                "• [Important detail 1]\n"
                "• [Important detail 2]\n"
                "• [Important detail 3]\n\n"
                "RELATED INSIGHTS:\n"
                "[Additional context and implications]\n\n"
                "COMMON QUESTIONS:\n"
                "Q1: [Frequently asked question 1]\n"
                "A1: [Clear answer with data if applicable]\n"
                "Q2: [Frequently asked question 2]\n"
                "A2: [Clear answer with data if applicable]\n\n"
                f"Question/Topic to analyze:\n{text}"
            )
        else:
            prompt = (
                "You are a knowledgeable AI assistant. Analyze and summarize the following content "
                "with focus on both key information and numerical data.\n\n"
                "Format your response as:\n\n"
                "EXECUTIVE SUMMARY:\n"
                "[2-3 sentences capturing main points]\n\n"
                "STATISTICAL HIGHLIGHTS:\n"
                "📊 [Key statistic/metric 1]\n"
                "📊 [Key statistic/metric 2]\n"
                "📊 [Key statistic/metric 3]\n\n"
                "KEY FINDINGS:\n"
                "• [Major finding 1]\n"
                "• [Major finding 2]\n"
                "• [Major finding 3]\n\n"
                "DETAILED ANALYSIS:\n"
                "[In-depth analysis with facts and figures]\n\n"
                "IMPORTANT QUESTIONS COVERED:\n"
                "Q1: [Key question from content]\n"
                "A1: [Answer with supporting data]\n\n"
                "CONCLUSIONS & IMPLICATIONS:\n"
                "[Key takeaways with relevant metrics]\n\n"
                f"Content to analyze:\n{text}"
            )
        return prompt

    def analyze_text(self, text: str) -> AnalysisResult:
        """Analyze text using Gemini 2.0"""
        try:
            # Clean the text
            cleaned_text = text.replace('filepath:', '').replace('PS C:\\>', '')
            
            # Generate response with configured parameters
            response = self.model.generate_content(
                self._construct_prompt(cleaned_text),
                generation_config=self.generation_config
            )
            
            # Extract Q&A pairs
            questions, answers = self._extract_qa(response.text)
            
            # Format the response with enhanced styling
            formatted_response = self._process_response(response.text)
            
            return AnalysisResult(
                summary=formatted_response,
                questions=questions,
                answers=answers
            )
                
        except Exception as e:
            logging.error(f"Error in text analysis: {str(e)}")
            return AnalysisResult(
                summary=f"Error analyzing text: {str(e)}",
                questions=[],
                answers=[]
            )

    def _process_response(self, response_text: str) -> str:
        """Process and format the response for better readability"""
        formatted_text = ""
        sections = []
        current_section = ""
        current_content = []
        
        # Custom styling
        section_separator = "=" * 60
        bullet = "•"
        stat_emoji = "📊"
        
        # Section formatting templates
        section_header = lambda x: f"\n{section_separator}\n** {x.upper()} **\n{section_separator}\n\n"
        bullet_point = lambda x: f"{bullet} {x}\n"
        stat_point = lambda x: f"{stat_emoji} {x}\n"
        qa_format = lambda q, a: f"Q: {q}\nA: {a}\n\n"
        
        for line in response_text.split('\n'):
            line = line.strip()
            if not line:
                continue
                
            # Handle section headers
            if line.endswith(':'):
                if current_section and current_content:
                    sections.append((current_section, current_content))
                current_section = line[:-1]
                current_content = []
            else:
                current_content.append(line)
        
        # Add the last section
        if current_section and current_content:
            sections.append((current_section, current_content))
        
        # Format each section
        for section, content in sections:
            formatted_text += section_header(section)
            
            for line in content:
                # Handle different line types
                if line.startswith('•'):
                    formatted_text += bullet_point(line[1:].strip())
                elif line.startswith('Q'):
                    q_text = line[line.find(':')+1:].strip()
                    # Find corresponding answer
                    a_text = next((c[c.find(':')+1:].strip() for c in content if c.startswith('A')), "")
                    formatted_text += qa_format(q_text, a_text)
                elif line.startswith('A'):
                    continue  # Skip answers as they're handled with questions
                elif any(char.isdigit() for char in line) and not line.startswith(('Q', 'A')):
                    formatted_text += stat_point(line)
                else:
                    # Regular text with paragraph formatting
                    formatted_text += f"{line}\n\n"
        
        return formatted_text.strip()

    def _format_section(self, title: str, content: list) -> str:
        """Helper method to format a section with consistent styling"""
        formatted = f"\n{'=' * 60}\n"
        formatted += f"** {title.upper()} **\n"
        formatted += f"{'=' * 60}\n\n"
        
        for line in content:
            if line.startswith('•'):
                formatted += f"  • {line[1:].strip()}\n"
            elif line.startswith('📊'):
                formatted += f"  📊 {line[1:].strip()}\n"
            else:
                formatted += f"{line}\n"
                
        return formatted + "\n"

    def _extract_qa(self, response_text: str) -> tuple[list, list]:
        """Extract questions and answers from the response"""
        questions = []
        answers = []
        
        for line in response_text.split('\n'):
            line = line.strip()
            if line.startswith('Q'):
                questions.append(line[line.find(':')+1:].strip())
            elif line.startswith('A'):
                answers.append(line[line.find(':')+1:].strip())
                
        return questions, answers