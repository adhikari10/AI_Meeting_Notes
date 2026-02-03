import time
import threading
from datetime import datetime
from rich.console import Console
from rich.panel import Panel
from rich.live import Live
from rich.text import Text
import json
import uuid

# FIX 14: Import MeetingCapture (the actual class name), not AudioCapture
from meeting_capture import MeetingCapture
from transcriber import Transcriber
from meeting_ai import MeetingAI
from database import MeetingDatabase
from config import Config

class DeepSeekMeetingAssistant:
    def __init__(self):
        self.console = Console()
        self.config = Config()
        self.config.validate()

        # FIX 15: Use MeetingCapture instead of AudioCapture
        self.audio = MeetingCapture()
        self.transcriber = Transcriber()
        self.ai = MeetingAI()
        self.db = MeetingDatabase(self.config.DB_PATH)
        self.is_running = False

        self.meeting_id = str(uuid.uuid4())
        self.meeting_start_time = None
        self.transcript_display = []
        self.analysis_history = []
        
    def create_dashboard(self):
        """Create live dashboard"""
        text = Text()
        
        text.append("🤖 AI Meeting Assistant\n", style="bold cyan")
        text.append(f"Provider: {self.config.AI_PROVIDER} | Model: {self.config.AI_MODEL}\n", style="dim")
        text.append("=" * 50 + "\n")
        
        status = "▶️  Recording..." if self.is_running else "⏸️  Paused"
        text.append(f"{status}\n\n", style="green" if self.is_running else "yellow")
        
        if self.transcript_display:
            text.append("Recent Conversation:\n", style="bold")
            for line in self.transcript_display[-3:]:
                text.append(f"  {line}\n", style="white")
        else:
            text.append("Listening...\n", style="dim")
            
        if self.analysis_history:
            latest = self.analysis_history[-1]
            text.append("\n🤖 AI Analysis:\n", style="bold yellow")
            
            if isinstance(latest, dict):
                if latest.get("summary"):
                    text.append(f"  📝 {latest['summary']}\n", style="yellow")
                
                if latest.get("action_items"):
                    text.append(f"  ✅ Actions: {', '.join(latest['action_items'][:2])}\n", style="green")
                
                if latest.get("decisions"):
                    text.append(f"  🎯 Decisions: {latest['decisions'][0]}\n", style="blue")
            else:
                text.append(f"  {latest}\n", style="yellow")
                
        return Panel(text, title="Live Meeting", border_style="cyan")
        
    def process_audio(self):
        """Process audio in background thread"""
        while self.is_running:
            audio_chunk = self.audio.get_audio_chunk()
            
            if audio_chunk is not None:
                transcript = self.transcriber.transcribe_audio(audio_chunk)
                
                if transcript and len(transcript.strip()) > 10:
                    timestamp = datetime.now().strftime("%H:%M")
                    
                    display_text = f"[{timestamp}] {transcript}"
                    self.transcript_display.append(display_text)
                    
                    if len(self.transcript_display) > 10:
                        self.transcript_display.pop(0)
                    
                    self.console.print(display_text)
                    
                    analysis = self.ai.analyze_chunk(transcript)
                    if analysis:
                        self.analysis_history.append(analysis)

                        try:
                            note_data = {
                                'timestamp': timestamp,
                                'speaker': 'Unknown',
                                'text': transcript,
                                'summary': analysis.get('summary', ''),
                                'action_items': analysis.get('action_items', []),
                                'decisions': analysis.get('decisions', []),
                                'questions': analysis.get('questions', [])
                            }

                            class Note:
                                def __init__(self, data):
                                    self.timestamp = data['timestamp']
                                    self.speaker = data['speaker']
                                    self.text = data['text']
                                    self.summary = data['summary']
                                    self.action_items = data['action_items']
                                    self.decisions = data['decisions']
                                    self.questions = data['questions']

                            self.db.save_live_note(self.meeting_id, Note(note_data))
                        except Exception as e:
                            self.console.print(f"[yellow]⚠️  Database save error: {e}[/yellow]")

                        if analysis.get("action_items"):
                            for action in analysis["action_items"][:2]:
                                self.console.print(f"  [green]✓ {action}[/green]")
                    
    def run(self):
        """Run the assistant"""
        self.console.clear()

        try:
            # FIX 16: Use MeetingCapture's list_audio_sources instead of list_devices
            self.audio.list_audio_sources()

            device_index = input("\nEnter device number (Enter for default): ").strip()
            recording_started = False

            if device_index.isdigit():
                recording_started = self.audio.start_capture(int(device_index))
            else:
                recording_started = self.audio.start_capture()

            if not recording_started:
                print("\n❌ Failed to start recording. Exiting.")
                self.db.close()
                return

            self.meeting_start_time = datetime.now()
            self.is_running = True
            print(f"📝 Meeting ID: {self.meeting_id}")
        except Exception as e:
            print(f"\n❌ Error during setup: {e}")
            self.db.close()
            return
        
        process_thread = threading.Thread(target=self.process_audio, daemon=True)
        process_thread.start()
        
        try:
            with Live(self.create_dashboard(), refresh_per_second=2, screen=True) as live:
                while self.is_running:
                    live.update(self.create_dashboard())
                    time.sleep(0.5)
                    
        except KeyboardInterrupt:
            print("\n\n🛑 Stopping meeting assistant...")
            
        finally:
            self.is_running = False
            # FIX 17: Use .stop() instead of .stop_recording()
            self.audio.stop()
            self.generate_final_report()
            self.db.close()
            
    def generate_final_report(self):
        """Generate and save final report"""
        if not self.transcript_display:
            print("No transcript to summarize.")
            return
            
        print("\n" + "="*60)
        print("📊 GENERATING FINAL MEETING REPORT")
        print("="*60)
        
        final_report = self.ai.final_meeting_report()
        
        if isinstance(final_report, dict):
            print(f"\n📌 Title: {final_report.get('title', 'Untitled Meeting')}")
            print(f"\n📝 Executive Summary:")
            print(final_report.get('executive_summary', 'No summary generated'))
            
            if final_report.get('action_items'):
                print(f"\n✅ Action Items:")
                for i, action in enumerate(final_report['action_items'], 1):
                    print(f"  {i}. {action}")
                    
            if final_report.get('decisions'):
                print(f"\n🎯 Decisions Made:")
                for i, decision in enumerate(final_report['decisions'], 1):
                    print(f"  {i}. {decision}")
                    
            filename = f"meeting_report_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
            with open(filename, 'w') as f:
                json.dump(final_report, f, indent=2)

            print(f"\n💾 Report saved to {filename}")

            try:
                title = final_report.get('title', 'Untitled Meeting')
                self.db.save_final_meeting(self.meeting_id, title, final_report)
                print(f"💾 Meeting saved to database (ID: {self.meeting_id})")
            except Exception as e:
                print(f"⚠️  Database save error: {e}")

        else:
            print("Could not generate final report.")

def main():
    print("🤖 AI Meeting Assistant")
    print("=" * 40)
    
    assistant = DeepSeekMeetingAssistant()
    assistant.run()

if __name__ == "__main__":
    main()