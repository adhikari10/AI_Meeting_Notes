from datetime import datetime
from api_client import AIClient

class MeetingAI:
    def __init__(self):
        self.ai_client = AIClient()
        self.transcript_chunks = []
        self.meeting_context = []
        
    def add_transcript_chunk(self, text, timestamp=None):
        """Add a transcript chunk"""
        if not text or len(text.strip()) < 5:
            return False
            
        chunk = {
            'timestamp': timestamp or datetime.now().strftime("%H:%M:%S"),
            'text': text
        }
        self.transcript_chunks.append(chunk)
        return True
        
    def analyze_chunk(self, text):
        """Analyze a single chunk with AI"""
        if not text:
            return {}

        # Store the transcript chunk
        self.add_transcript_chunk(text)

        if not self.ai_client.client:
            return {}

        prompt = f"""As a meeting assistant, analyze this conversation snippet:

{text}

Extract and return ONLY a JSON object with these keys:
- "summary": Brief 1-sentence summary
- "action_items": Array of action items (empty array if none)
- "decisions": Array of decisions made (empty array if none)
- "questions": Array of questions raised (empty array if none)

Return ONLY the JSON, no other text."""

        response = self.ai_client.chat_completion([
            {"role": "system", "content": "You extract structured information from meetings."},
            {"role": "user", "content": prompt}
        ], max_tokens=300)
        
        if response:
            result = self.ai_client.extract_json(response)
            return result or {}
        return {}
        
    def get_recent_summary(self, last_n=5):
        """Get summary of recent chunks"""
        if not self.transcript_chunks:
            return "No transcript yet."
            
        recent_chunks = self.transcript_chunks[-last_n:]
        recent_text = "\n".join([chunk['text'] for chunk in recent_chunks])
        
        if not self.ai_client.client:
            return recent_text
            
        prompt = f"""Summarize this recent conversation in 1-2 sentences:

{recent_text}"""

        response = self.ai_client.chat_completion([
            {"role": "system", "content": "You summarize conversations concisely."},
            {"role": "user", "content": prompt}
        ], max_tokens=100)
        
        return response or "Could not generate summary."
        
    def final_meeting_report(self):
        """Generate comprehensive final report"""
        if not self.transcript_chunks:
            return {"error": "No transcript available"}
            
        full_transcript = "\n".join([
            f"[{chunk['timestamp']}] {chunk['text']}"
            for chunk in self.transcript_chunks
        ])
        
        prompt = f"""Generate a comprehensive meeting report from this transcript:

{full_transcript}

Return a JSON object with:
- "title": Suggested meeting title
- "executive_summary": 3-4 sentence summary
- "key_points": Array of key discussion points
- "action_items": Array with "person: task (deadline)"
- "decisions": Array of decisions made
- "next_steps": Array of next steps
- "participants": Array of detected participant names
- "duration_minutes": Estimated duration

Be thorough and professional."""

        response = self.ai_client.chat_completion([
            {"role": "system", "content": "You are an expert meeting analyst."},
            {"role": "user", "content": prompt}
        ], max_tokens=800)
        
        if response:
            result = self.ai_client.extract_json(response)
            return result or {"summary": "Could not generate full report"}
        return {"summary": "API error"}