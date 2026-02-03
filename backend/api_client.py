import os
import openai
from openai import OpenAI
import json
from typing import Optional
from config import Config

class AIClient:
    def __init__(self):
        self.config = Config()
        self.provider = self.config.AI_PROVIDER.lower()
        self.model = self.config.AI_MODEL

        # Initialize based on provider
        if self.provider == "groq":
            self.client = OpenAI(
                api_key=self.config.GROQ_API_KEY,
                base_url="https://api.groq.com/openai/v1"
            )
            print("🤖 Using Groq API")

        elif self.provider == "deepseek":
            self.client = OpenAI(
                api_key=self.config.DEEPSEEK_API_KEY,
                base_url="https://api.deepseek.com"
            )
            print("🤖 Using DeepSeek API")

        elif self.provider == "openai":
            self.client = OpenAI(api_key=self.config.OPENAI_API_KEY)
            print("🤖 Using OpenAI API")

        else:
            print("⚠️  No AI provider configured. Some features will be disabled.")
            self.client = None
            
    def chat_completion(self, messages, max_tokens=500, temperature=0.3):
        """Send chat completion request"""
        if not self.client:
            return None
            
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            print(f"❌ API Error ({self.provider}): {e}")
            return None
            
    def extract_json(self, text):
        """Extract JSON from AI response"""
        if not text:
            return None
            
        try:
            # Try to find JSON in the response
            if "```json" in text:
                json_str = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                json_str = text.split("```")[1].split("```")[0]
            else:
                json_str = text
                
            return json.loads(json_str.strip())
        except:
            # If not JSON, return as plain text
            return {"text": text}