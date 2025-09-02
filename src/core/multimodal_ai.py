import google.generativeai as genai
from PIL import Image
import cv2
import numpy as np
from typing import Dict, List, Optional, Union, Tuple
import base64
import io
import time
import logging
from dataclasses import dataclass
import json
from pathlib import Path
import asyncio
import aiohttp
from concurrent.futures import ThreadPoolExecutor
import threading

@dataclass
class MultiModalInput:
    text: str = ""
    image: Optional[np.ndarray] = None
    context: Optional[Dict] = None
    metadata: Optional[Dict] = None
    priority: int = 1  # 1 = high, 2 = medium, 3 = low

@dataclass
class AIResponse:
    summary: str
    detailed_analysis: str
    action_suggestions: List[str]
    confidence_score: float
    processing_time: float
    context_used: Dict
    follow_up_questions: List[str]

class MultiModalAIProcessor:
    """Advanced AI processor with multi-modal capabilities and context awareness"""
    
    def __init__(self, api_key: str):
        genai.configure(api_key=api_key)
        self.text_model = genai.GenerativeModel('gemini-pro')
        self.vision_model = genai.GenerativeModel('gemini-pro-vision')
        self.conversation_history = []
        self.context_memory = {}
        self.processing_queue = asyncio.Queue()
        self.executor = ThreadPoolExecutor(max_workers=3)
        
    async def process_multimodal_input(self, inputs: List[MultiModalInput]) -> AIResponse:
        """Process multiple inputs with different modalities"""
        start_time = time.time()
        
        # Sort inputs by priority
        inputs.sort(key=lambda x: x.priority)
        
        # Combine and analyze all inputs
        combined_analysis = await self._analyze_combined_inputs(inputs)
        
        # Generate comprehensive response
        response = await self._generate_comprehensive_response(combined_analysis, inputs)
        
        processing_time = time.time() - start_time
        response.processing_time = processing_time
        
        # Store in conversation history
        self._update_conversation_history(inputs, response)
        
        return response
    
    async def _analyze_combined_inputs(self, inputs: List[MultiModalInput]) -> Dict:
        """Analyze all inputs and create a combined understanding"""
        
        analyses = []
        
        for input_item in inputs:
            analysis = {}
            
            # Text analysis
            if input_item.text:
                analysis['text_analysis'] = await self._analyze_text_advanced(input_item.text)
            
            # Image analysis
            if input_item.image is not None:
                analysis['image_analysis'] = await self._analyze_image_advanced(input_item.image)
            
            # Context analysis
            if input_item.context:
                analysis['context_analysis'] = await self._analyze_context(input_item.context)
            
            analyses.append(analysis)
        
        # Combine all analyses
        combined = {
            'individual_analyses': analyses,
            'cross_modal_insights': await self._find_cross_modal_patterns(analyses),
            'temporal_patterns': await self._analyze_temporal_patterns(inputs),
            'confidence_assessment': self._assess_overall_confidence(analyses)
        }
        
        return combined
    
    async def _analyze_text_advanced(self, text: str) -> Dict:
        """Advanced text analysis with multiple techniques"""
        
        prompt = f"""
        Analyze this text comprehensively:
        
        Text: {text}
        
        Provide analysis in JSON format:
        {{
            "main_topics": ["topic1", "topic2"],
            "sentiment": "positive/negative/neutral",
            "intent": "what the user wants to accomplish",
            "entities": ["person", "place", "organization"],
            "questions_present": ["question1", "question2"],
            "action_items": ["action1", "action2"],
            "technical_content": "yes/no",
            "urgency_level": "high/medium/low",
            "context_clues": ["clue1", "clue2"],
            "knowledge_gaps": ["gap1", "gap2"]
        }}
        """
        
        try:
            response = await asyncio.get_event_loop().run_in_executor(
                self.executor, 
                lambda: self.text_model.generate_content(prompt)
            )
            
            # Parse JSON response
            try:
                return json.loads(response.text)
            except json.JSONDecodeError:
                # Fallback to simple analysis
                return {
                    "main_topics": ["general"],
                    "sentiment": "neutral",
                    "intent": "information seeking",
                    "entities": [],
                    "questions_present": [],
                    "action_items": [],
                    "technical_content": "unknown",
                    "urgency_level": "medium",
                    "context_clues": [],
                    "knowledge_gaps": []
                }
                
        except Exception as e:
            logging.error(f"Error in advanced text analysis: {e}")
            return {"error": str(e)}
    
    async def _analyze_image_advanced(self, image: np.ndarray) -> Dict:
        """Advanced image analysis with vision model"""
        
        # Convert numpy array to PIL Image
        if len(image.shape) == 3:
            # Convert BGR to RGB if necessary
            image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        else:
            image_rgb = image
            
        pil_image = Image.fromarray(image_rgb)
        
        prompt = """
        Analyze this image comprehensively and provide a JSON response:
        
        {
            "scene_description": "detailed description of what's in the image",
            "text_detected": "any text visible in the image",
            "ui_elements": ["button", "menu", "text field"],
            "application_type": "web browser/text editor/game/etc",
            "visual_context": "what activity is being performed",
            "notable_features": ["feature1", "feature2"],
            "technical_elements": ["code", "diagrams", "charts"],
            "action_opportunities": ["what actions could be taken"],
            "attention_areas": ["areas that draw attention"],
            "accessibility_notes": ["accessibility considerations"]
        }
        """
        
        try:
            response = await asyncio.get_event_loop().run_in_executor(
                self.executor,
                lambda: self.vision_model.generate_content([prompt, pil_image])
            )
            
            # Parse JSON response
            try:
                return json.loads(response.text)
            except json.JSONDecodeError:
                # Fallback to simple analysis
                return {
                    "scene_description": response.text,
                    "text_detected": "",
                    "ui_elements": [],
                    "application_type": "unknown",
                    "visual_context": "general computer use",
                    "notable_features": [],
                    "technical_elements": [],
                    "action_opportunities": [],
                    "attention_areas": [],
                    "accessibility_notes": []
                }
                
        except Exception as e:
            logging.error(f"Error in advanced image analysis: {e}")
            return {"error": str(e)}
    
    async def _analyze_context(self, context: Dict) -> Dict:
        """Analyze provided context information"""
        
        context_analysis = {
            "application_insights": {},
            "user_behavior_patterns": {},
            "environmental_factors": {},
            "historical_context": {}
        }
        
        # Analyze application context
        if 'application' in context:
            app = context['application']
            context_analysis["application_insights"] = {
                "app_type": self._categorize_application(app.get('process_name', '')),
                "usage_intensity": self._assess_usage_intensity(app),
                "capabilities": self._identify_app_capabilities(app.get('process_name', ''))
            }
        
        # Analyze user behavior
        if 'recent_actions' in context:
            context_analysis["user_behavior_patterns"] = {
                "activity_type": self._classify_user_activity(context['recent_actions']),
                "workflow_stage": self._identify_workflow_stage(context),
                "focus_level": self._assess_focus_level(context)
            }
        
        return context_analysis
    
    async def _find_cross_modal_patterns(self, analyses: List[Dict]) -> Dict:
        """Find patterns across different modalities"""
        
        patterns = {
            "text_image_alignment": 0.0,
            "context_consistency": 0.0,
            "information_completeness": 0.0,
            "conflicting_signals": [],
            "complementary_insights": []
        }
        
        # Analyze alignment between text and image content
        text_topics = []
        image_content = []
        
        for analysis in analyses:
            if 'text_analysis' in analysis and 'main_topics' in analysis['text_analysis']:
                text_topics.extend(analysis['text_analysis']['main_topics'])
            
            if 'image_analysis' in analysis and 'scene_description' in analysis['image_analysis']:
                image_content.append(analysis['image_analysis']['scene_description'])
        
        # Simple alignment assessment (could be enhanced with embeddings)
        if text_topics and image_content:
            patterns["text_image_alignment"] = self._calculate_content_alignment(text_topics, image_content)
        
        return patterns
    
    async def _analyze_temporal_patterns(self, inputs: List[MultiModalInput]) -> Dict:
        """Analyze patterns over time"""
        
        temporal_analysis = {
            "activity_trend": "increasing/decreasing/stable",
            "attention_shift": "focused/scattered/transitioning",
            "task_progression": "beginning/middle/end",
            "interruption_pattern": "frequent/occasional/none"
        }
        
        # This would analyze the timing and sequence of inputs
        # For now, return placeholder analysis
        
        return temporal_analysis
    
    async def _generate_comprehensive_response(self, combined_analysis: Dict, inputs: List[MultiModalInput]) -> AIResponse:
        """Generate a comprehensive response based on all analyses"""
        
        # Create a comprehensive prompt
        prompt = f"""
        Based on this comprehensive analysis of user's screen content and context:
        
        Analysis: {json.dumps(combined_analysis, indent=2)}
        
        Generate a helpful response that:
        1. Summarizes what the user is doing
        2. Provides relevant insights or answers
        3. Suggests helpful actions
        4. Identifies any questions that need answers
        5. Rates confidence in the analysis
        
        Format as JSON:
        {{
            "summary": "Brief summary of current activity and content",
            "detailed_analysis": "Comprehensive analysis with insights",
            "action_suggestions": ["suggestion1", "suggestion2"],
            "confidence_score": 0.0-1.0,
            "context_used": {{"key": "value"}},
            "follow_up_questions": ["question1", "question2"]
        }}
        """
        
        try:
            response = await asyncio.get_event_loop().run_in_executor(
                self.executor,
                lambda: self.text_model.generate_content(prompt)
            )
            
            # Parse response
            try:
                response_data = json.loads(response.text)
                return AIResponse(
                    summary=response_data.get('summary', ''),
                    detailed_analysis=response_data.get('detailed_analysis', ''),
                    action_suggestions=response_data.get('action_suggestions', []),
                    confidence_score=response_data.get('confidence_score', 0.5),
                    processing_time=0.0,  # Will be set by caller
                    context_used=response_data.get('context_used', {}),
                    follow_up_questions=response_data.get('follow_up_questions', [])
                )
            except json.JSONDecodeError:
                # Fallback response
                return AIResponse(
                    summary=response.text[:200],
                    detailed_analysis=response.text,
                    action_suggestions=["Review the analysis provided"],
                    confidence_score=0.7,
                    processing_time=0.0,
                    context_used={},
                    follow_up_questions=[]
                )
                
        except Exception as e:
            logging.error(f"Error generating comprehensive response: {e}")
            return AIResponse(
                summary="Error in analysis",
                detailed_analysis=f"An error occurred: {str(e)}",
                action_suggestions=["Try again or check system logs"],
                confidence_score=0.0,
                processing_time=0.0,
                context_used={},
                follow_up_questions=[]
            )
    
    def _categorize_application(self, process_name: str) -> str:
        """Categorize application type"""
        categories = {
            'browser': ['chrome', 'firefox', 'edge', 'safari'],
            'editor': ['code', 'notepad', 'sublime', 'atom'],
            'office': ['word', 'excel', 'powerpoint', 'outlook'],
            'media': ['vlc', 'spotify', 'photoshop'],
            'development': ['visual studio', 'pycharm', 'intellij'],
            'communication': ['teams', 'slack', 'discord', 'zoom']
        }
        
        process_lower = process_name.lower()
        for category, apps in categories.items():
            if any(app in process_lower for app in apps):
                return category
        
        return 'unknown'
    
    def _assess_usage_intensity(self, app_info: Dict) -> str:
        """Assess how intensively the application is being used"""
        cpu_percent = app_info.get('cpu_percent', 0)
        memory_usage = app_info.get('memory_usage', 0)
        
        if cpu_percent > 50 or memory_usage > 500_000_000:  # 500MB
            return 'high'
        elif cpu_percent > 10 or memory_usage > 100_000_000:  # 100MB
            return 'medium'
        else:
            return 'low'
    
    def _identify_app_capabilities(self, process_name: str) -> List[str]:
        """Identify what capabilities the application has"""
        capabilities_map = {
            'chrome': ['web_browsing', 'javascript', 'extensions'],
            'code': ['text_editing', 'syntax_highlighting', 'debugging'],
            'word': ['document_creation', 'formatting', 'collaboration'],
            'excel': ['spreadsheets', 'calculations', 'charts'],
            'photoshop': ['image_editing', 'layers', 'filters']
        }
        
        for app, capabilities in capabilities_map.items():
            if app in process_name.lower():
                return capabilities
        
        return ['general_purpose']
    
    def _classify_user_activity(self, recent_actions: List[str]) -> str:
        """Classify the type of activity the user is performing"""
        if not recent_actions:
            return 'unknown'
        
        # Simple classification based on action keywords
        action_text = ' '.join(recent_actions).lower()
        
        if any(word in action_text for word in ['type', 'edit', 'write']):
            return 'content_creation'
        elif any(word in action_text for word in ['click', 'navigate', 'browse']):
            return 'information_seeking'
        elif any(word in action_text for word in ['debug', 'compile', 'test']):
            return 'development'
        else:
            return 'general_use'
    
    def _identify_workflow_stage(self, context: Dict) -> str:
        """Identify what stage of a workflow the user is in"""
        # This would analyze context to determine workflow stage
        return 'active'  # Placeholder
    
    def _assess_focus_level(self, context: Dict) -> str:
        """Assess the user's current focus level"""
        # This would analyze patterns to determine focus
        return 'focused'  # Placeholder
    
    def _calculate_content_alignment(self, text_topics: List[str], image_content: List[str]) -> float:
        """Calculate how well text and image content align"""
        # Simple keyword matching - could be enhanced with embeddings
        if not text_topics or not image_content:
            return 0.0
        
        matches = 0
        total = len(text_topics)
        
        image_text = ' '.join(image_content).lower()
        for topic in text_topics:
            if topic.lower() in image_text:
                matches += 1
        
        return matches / total if total > 0 else 0.0
    
    def _assess_overall_confidence(self, analyses: List[Dict]) -> float:
        """Assess overall confidence in the analysis"""
        # This would evaluate the quality and consistency of analyses
        return 0.8  # Placeholder
    
    def _update_conversation_history(self, inputs: List[MultiModalInput], response: AIResponse):
        """Update conversation history for context"""
        entry = {
            'timestamp': time.time(),
            'inputs': len(inputs),
            'response_summary': response.summary,
            'confidence': response.confidence_score
        }
        
        self.conversation_history.append(entry)
        
        # Keep only recent history
        if len(self.conversation_history) > 50:
            self.conversation_history = self.conversation_history[-50:]