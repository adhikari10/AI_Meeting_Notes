import time
import threading
from datetime import datetime
from rich.console import Console
from rich.panel import Panel
from rich.live import Live
from rich.text import Text
import json

from meeting_capture import MeetingCapture, AudioSource
import whisper
from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()

class SmartMeetingAssistant:
    def __init__(self):
        self.console = Console()
        self.capture = None
        self.is_running = False
        
        # Load AI models
        print("🔄 Loading Whisper model...")
        self.whisper_model = whisper.load_model("base")
        
        # Setup AI client
        api_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")
        if api_key:
            if os.getenv("AI_PROVIDER") == "deepseek":
                self.ai_client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
                self.ai_model = "deepseek-chat"
            else:
                self.ai_client = OpenAI(api_key=api_key)
                self.ai_model = "gpt-3.5-turbo"
            print(f"🤖 AI Model: {self.ai_model}")
        else:
            self.ai_client = None
            print("⚠️  No API key found. AI features disabled.")
        
        # Data storage
        self.transcript = []
        self.notes = []
        
    def select_audio_source(self):
        """Let user select audio source"""
        self.capture = MeetingCapture()
        mics, speakers = self.capture.list_audio_sources()

        while True:
            choice = input("\nSelect audio source type:\n"
                          "  1. 🎤 Microphone only (you speaking)\n"
                          "  2. 🔊 Speaker Output only (Zoom/Teams meeting)\n"
                          "  3. 🎤+🔊 BOTH (your voice + meeting audio) ⭐ RECOMMENDED\n"
                          "  4. 📋 List all devices and choose manually\n"
                          "Your choice (1-4): ").strip()

            if choice == "1":
                print("🎤 Using microphone only...")
                device_index = self.capture._find_microphone()
                return device_index, False
            elif choice == "2":
                print("🔊 Capturing speaker output only...")
                print("   Make sure your meeting/video is playing!")
                device_index = self.capture._find_stereo_mix()
                return device_index, False
            elif choice == "3":
                print("🎤+🔊 Capturing BOTH microphone and speaker output!")
                print("   This will capture both your voice and meeting audio")
                return None, True  # None device_index, True for both
            elif choice == "4":
                print("\nAll available input devices:")
                for i in range(self.capture.p.get_device_count()):
                    info = self.capture.p.get_device_info_by_index(i)
                    if info['maxInputChannels'] > 0:
                        print(f"  [{i}] {info['name']}")

                device_index = int(input("\nEnter device number: "))
                return device_index, False
            else:
                print("❌ Invalid choice. Try again.")
        
    def process_audio(self):
        """Process audio in background"""
        while self.is_running:
            audio_chunk = self.capture.get_audio_chunk()
            
            if audio_chunk is not None:
                # Transcribe
                result = self.whisper_model.transcribe(audio_chunk)
                text = result["text"].strip()
                
                if text:
                    # Add timestamp
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    
                    # Store transcript
                    self.transcript.append({
                        "time": timestamp,
                        "text": text
                    })
                    
                    # Display
                    self.console.print(f"[dim]{timestamp}[/dim] {text}")
                    
                    # AI analysis if available
                    if self.ai_client and len(text) > 10:
                        self.analyze_with_ai(text, timestamp)
                        
    def analyze_with_ai(self, text, timestamp):
        """Analyze text with AI"""
        try:
            prompt = f"""Analyze this meeting snippet and extract:
            1. Brief summary (1 sentence)
            2. Action items (if any)
            3. Decisions made (if any)
            4. Questions raised (if any)
            
            Text: {text}
            
            Return as JSON."""
            
            response = self.ai_client.chat.completions.create(
                model=self.ai_model,
                messages=[
                    {"role": "system", "content": "You extract meeting insights. Return ONLY JSON."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=200,
                temperature=0.3
            )
            
            content = response.choices[0].message.content
            
            # Try to parse JSON
            try:
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0]
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0]
                    
                analysis = json.loads(content)
                analysis["time"] = timestamp
                self.notes.append(analysis)
                
                # Display insights
                if analysis.get("action_items"):
                    for action in analysis["action_items"][:2]:
                        self.console.print(f"  [green]✅ {action}[/green]")
                        
            except:
                self.notes.append({"time": timestamp, "summary": content[:100] + "..."})
                
        except Exception as e:
            print(f"AI error: {e}")
            
    def create_dashboard(self):
        """Create live dashboard"""
        text = Text()
        
        text.append("🤖 SMART MEETING ASSISTANT\n", style="bold cyan")
        text.append("="*50 + "\n")
        
        # Status
        status = "🔴 Recording" if self.is_running else "⏸️ Stopped"
        text.append(f"Status: {status}\n\n", style="green" if self.is_running else "yellow")
        
        # Recent transcript
        if self.transcript:
            text.append("Recent Conversation:\n", style="bold")
            for item in self.transcript[-3:]:
                text.append(f"  [{item['time']}] {item['text'][:50]}...\n", style="white")
        else:
            text.append("Listening...\n", style="dim")
            
        # Recent analysis
        if self.notes:
            text.append("\n📊 AI Insights:\n", style="bold yellow")
            for note in self.notes[-2:]:
                if "summary" in note:
                    text.append(f"  📝 {note['summary']}\n", style="yellow")
                if "action_items" in note and note["action_items"]:
                    text.append(f"  ✅ {note['action_items'][0]}\n", style="green")
                    
        return Panel(text, title="Live Meeting", border_style="cyan")
        
    def run(self):
        """Main run loop"""
        self.console.clear()
        
        print("🤖 Starting Smart Meeting Assistant...\n")
        
        # Select audio source
        device_index, capture_both = self.select_audio_source()

        # Start capture
        try:
            if not self.capture.start_capture(device_index, capture_both=capture_both):
                print("❌ Failed to start audio capture")
                return
        except Exception as e:
            print(f"❌ Error starting capture: {e}")
            return

        self.is_running = True
        
        # Start processing thread
        process_thread = threading.Thread(target=self.process_audio, daemon=True)
        process_thread.start()
        
        try:
            # Live display
            with Live(self.create_dashboard(), refresh_per_second=2, screen=True) as live:
                while self.is_running:
                    live.update(self.create_dashboard())
                    time.sleep(0.5)
                    
        except KeyboardInterrupt:
            print("\n\n🛑 Stopping...")
            
        finally:
            self.is_running = False
            if self.capture:
                self.capture.stop()
            
            # Save results
            self.save_results()
            
    def save_results(self):
        """Save meeting results"""
        if not self.transcript:
            return
            
        filename = f"meeting_{datetime.now().strftime('%Y%m%d_%H%M')}.txt"
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write("="*60 + "\n")
            f.write("MEETING TRANSCRIPT & ANALYSIS\n")
            f.write("="*60 + "\n\n")
            
            f.write("📝 FULL TRANSCRIPT:\n")
            f.write("-"*40 + "\n")
            for item in self.transcript:
                f.write(f"[{item['time']}] {item['text']}\n")
                
            f.write("\n\n🤖 AI ANALYSIS:\n")
            f.write("-"*40 + "\n")
            for note in self.notes:
                if "time" in note:
                    f.write(f"\n[{note['time']}]\n")
                for key, value in note.items():
                    if key != "time":
                        if isinstance(value, list):
                            f.write(f"  {key}: {', '.join(value)}\n")
                        else:
                            f.write(f"  {key}: {value}\n")
                            
        print(f"\n💾 Meeting saved to: {filename}")

def main():
    assistant = SmartMeetingAssistant()
    assistant.run()

if __name__ == "__main__":
    main()