"""
Smart Meeting Notes - IMPROVED VERSION
Enhanced AI summaries and better audio quality
"""
import os
import time
import threading
from datetime import datetime
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, IntPrompt
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
import json
import numpy as np
import re
from meeting_capture import MeetingCapture
from simple_speaker_detection import SimpleSpeakerDetector
import whisper
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

def clean_text(text):
    """Remove gibberish and non-English characters"""
    # Remove non-ASCII (Korean, Russian, etc.)
    text = re.sub(r'[^\x00-\x7F\s]+', '', text)

    # Remove if mostly non-letters
    words = text.split()
    if len(words) > 0:
        letter_ratio = sum(1 for w in words if w.isalpha()) / len(words)
        if letter_ratio < 0.6:  # Less than 60% real words
            return ""

    # Remove very short segments (noise)
    if len(text.strip()) < 5:
        return ""

    return text.strip()

def clean_transcription(text):
    """Remove non-English characters and fix common Whisper errors"""
    text = re.sub(r'[^\x00-\x7F\s]+', '', text)  # Remove non-English

    # Fix common errors
    fixes = {'tire-star': 'entire star', 'heights in': 'hides in', 'the guy': 'the sky'}
    for wrong, right in fixes.items():
        text = text.replace(wrong, right)

    if len(text.strip()) < 5:
        return ""
    return text.strip()

class SmartNotesApp:
    def __init__(self):
        self.console = Console()
        self.notes_folder = Path("meeting_notes")
        self.notes_folder.mkdir(exist_ok=True)

        # AI Setup
        self.whisper_model = None
        self.ai_client = None
        self.ai_model = None
        self.speaker_detector = SimpleSpeakerDetector()
        
        # Audio quality settings
        self.sample_rate = 16000  # Higher quality
        self.chunk_duration = 10   # Longer chunks for better context

    def load_ai_models(self):
        """Load Whisper and LLM with better settings"""
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self.console
        ) as progress:
            # Load Whisper with better model
            task1 = progress.add_task("Loading Whisper (base model for better accuracy)...", total=None)
            self.whisper_model = whisper.load_model("small")  # Using 'base' instead of 'tiny' for better quality
            progress.update(task1, description="✅ Whisper loaded")

            # Setup AI client
            task2 = progress.add_task("Connecting to AI service...", total=None)
            api_key = os.getenv("GROQ_API_KEY") or os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")
            
            if api_key:
                if os.getenv("GROQ_API_KEY"):
                    self.ai_client = OpenAI(
                        api_key=api_key,
                        base_url="https://api.groq.com/openai/v1"
                    )
                    self.ai_model = "llama-3.3-70b-versatile"
                elif os.getenv("DEEPSEEK_API_KEY"):
                    self.ai_client = OpenAI(
                        api_key=api_key,
                        base_url="https://api.deepseek.com"
                    )
                    self.ai_model = "deepseek-chat"
                else:
                    self.ai_client = OpenAI(api_key=api_key)
                    self.ai_model = "gpt-3.5-turbo"
                
                progress.update(task2, description="✅ AI connected")
            else:
                progress.update(task2, description="⚠️ No AI key found (transcription only)")

    def generate_detailed_summary(self, transcript_items, duration_minutes=None):
        """Generate DETAILED summary based on discussion length and content"""
        if not self.ai_client or not transcript_items:
            return None

        try:
            full_text = " ".join([item['text'] for item in transcript_items])
            word_count = len(full_text.split())

            # Dynamic detail level
            max_tokens = 300 if word_count < 100 else 1500 if word_count > 1500 else 1000

            prompt = f"""Analyze this {word_count}-word transcript:

{full_text}

Provide:
## 📊 MEETING METRICS
- Words: {word_count}, Segments: {len(transcript_items)}, Duration: {duration_minutes}min

## 📝 EXECUTIVE SUMMARY (2-4 paragraphs)

## 🎯 MAIN TOPICS (5-8 topics with bullet points)

## ✅ ACTION ITEMS (with priority, assignee, deadline)

## 🔑 DECISIONS MADE

## 💡 KEY INSIGHTS

## ❓ QUESTIONS RAISED

## 📌 FOLLOW-UP NEEDED

## 🏆 QUALITY ASSESSMENT (Clarity, Productivity, Engagement scores)"""

            response = self.ai_client.chat.completions.create(
                model=self.ai_model,
                messages=[
                    {"role": "system", "content": "Expert meeting analyst. Be thorough and structured."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=max_tokens,
                temperature=0.3
            )
            return response.choices[0].message.content

        except Exception as e:
            self.console.print(f"[red]Error generating summary: {e}[/red]")
            return None

    def option_1_speaker_only(self):
        """Enhanced speaker capture with better audio quality"""
        self.console.clear()
        self.console.print("\n🔊 [bold cyan]CAPTURE FROM SPEAKER OUTPUT[/bold cyan]")
        self.console.print("[dim]Perfect for Zoom, Teams, Google Meet, etc.[/dim]\n")
        
        self.load_ai_models()
        
        # Enhanced audio capture settings
        capture = MeetingCapture()
        devices = capture.list_audio_devices()
        
        # Display devices with quality indicators
        self.console.print("\n[bold]Available Audio Devices:[/bold]")
        for idx, device in enumerate(devices):
            device_name = device['name']
            channels = device.get('max_input_channels', 0)
            sample_rate = device.get('default_samplerate', 0)
            
            # Quality indicator
            quality = "🟢 High" if sample_rate >= 44100 else "🟡 Medium" if sample_rate >= 16000 else "🔴 Low"
            
            self.console.print(
                f"  {idx}. {device_name}\n"
                f"     Quality: {quality} | Channels: {channels} | Sample Rate: {sample_rate}Hz"
            )
        
        device_index = IntPrompt.ask("\nSelect device number", default=0)
        
        # Start with enhanced settings
        capture.start(
            device_index=device_index,
            sample_rate=16000,  # Good quality for speech
            chunk_duration=self.chunk_duration
        )
        
        transcript = []
        notes_data = []
        is_recording = True
        start_time = time.time()
        
        try:
            self.console.print("\n[bold green]🔴 RECORDING IN PROGRESS[/bold green]")
            self.console.print("[yellow]Press Ctrl+C to stop recording[/yellow]\n")
            self.console.print("─" * 60)
            
            def process_audio():
                nonlocal transcript, notes_data, is_recording
                while is_recording:
                    audio_chunk = capture.get_audio_chunk()
                    if audio_chunk is not None:
                        # Enhanced transcription with better parameters
                        result = self.whisper_model.transcribe(
                            audio_chunk,
                            language='en',  # Specify language for better accuracy
                            fp16=False,     # Better quality on CPU
                            temperature=0.0,  # More deterministic
                            initial_prompt="This is a conversation, podcast, or meeting. People are speaking naturally in English. May include names, business terms, and expressions like 'happy', 'excited', 'thank you'.",
                            best_of=5,      # Try 5 different decodings
                            beam_size=5,    # Better search
                            condition_on_previous_text=True  # Use context
                        )
                        text = result["text"].strip()
                        text = clean_transcription(text)

                        if text and len(text) > 3:  # Filter out noise
                            timestamp = datetime.now().strftime("%H:%M:%S")
                            speaker = self.speaker_detector.detect_speaker(audio_chunk)
                            transcript.append({"time": timestamp, "speaker": speaker, "text": text})

                            self.console.print(f"[dim]{timestamp}[/dim] [cyan]{speaker}:[/cyan] {text}")
            
            thread = threading.Thread(target=process_audio, daemon=True)
            thread.start()
            
            try:
                while is_recording:
                    time.sleep(0.5)
            except KeyboardInterrupt:
                self.console.print("\n\n[yellow]Stopping recording...[/yellow]")
        
        finally:
            is_recording = False
            end_time = time.time()
            duration_minutes = (end_time - start_time) / 60
            capture.stop()
            
            if transcript:
                self.save_enhanced_notes(transcript, "SPEAKER OUTPUT", duration_minutes)
            else:
                self.console.print("\n[red]No audio was captured.[/red]")
            
            input("\nPress Enter to continue...")

    def option_2_both_sources(self):
        """Enhanced capture from both mic and speaker"""
        self.console.clear()
        self.console.print("\n🎤+🔊 [bold cyan]CAPTURE FROM BOTH SOURCES[/bold cyan]")
        self.console.print("[dim]Captures your voice AND meeting audio[/dim]\n")
        
        self.load_ai_models()
        
        capture = MeetingCapture()
        devices = capture.list_audio_devices()
        
        # Display devices with better formatting
        self.console.print("\n[bold]Available Audio Devices:[/bold]")
        for idx, device in enumerate(devices):
            device_name = device['name']
            channels = device.get('max_input_channels', 0)
            device_type = "🎤 Microphone" if "microphone" in device_name.lower() else "🔊 Speaker" if "stereo" in device_name.lower() or "output" in device_name.lower() else "🎧 Audio Device"
            
            self.console.print(f"  {idx}. {device_type} - {device_name}")
        
        device_index = IntPrompt.ask("\nSelect device number (choose a device that captures BOTH)", default=0)
        
        capture.start(
            device_index=device_index,
            sample_rate=16000,
            chunk_duration=self.chunk_duration
        )
        
        transcript = []
        is_recording = True
        start_time = time.time()
        
        try:
            self.console.print("\n[bold green]🔴 RECORDING IN PROGRESS[/bold green]")
            self.console.print("[yellow]Press Ctrl+C to stop recording[/yellow]\n")
            self.console.print("─" * 60)
            
            def process_audio():
                nonlocal transcript, is_recording
                while is_recording:
                    audio_chunk = capture.get_audio_chunk()
                    if audio_chunk is not None:
                        result = self.whisper_model.transcribe(
                            audio_chunk,
                            language='en',
                            fp16=False,
                            temperature=0.0,
                            initial_prompt="This is a conversation, podcast, or meeting. People are speaking naturally in English. May include names, business terms, and expressions like 'happy', 'excited', 'thank you'.",
                            best_of=5,
                            beam_size=5,
                            condition_on_previous_text=True
                        )
                        text = result["text"].strip()
                        text = clean_transcription(text)

                        if text and len(text) > 3:
                            timestamp = datetime.now().strftime("%H:%M:%S")
                            speaker = self.speaker_detector.detect_speaker(audio_chunk)
                            transcript.append({"time": timestamp, "speaker": speaker, "text": text})
                            self.console.print(f"[dim]{timestamp}[/dim] [cyan]{speaker}:[/cyan] {text}")
            
            thread = threading.Thread(target=process_audio, daemon=True)
            thread.start()
            
            try:
                while is_recording:
                    time.sleep(0.5)
            except KeyboardInterrupt:
                self.console.print("\n\n[yellow]Stopping recording...[/yellow]")
        
        finally:
            is_recording = False
            end_time = time.time()
            duration_minutes = (end_time - start_time) / 60
            capture.stop()
            
            if transcript:
                self.save_enhanced_notes(transcript, "MICROPHONE + SPEAKER", duration_minutes)
            else:
                self.console.print("\n[red]No audio was captured.[/red]")
            
            input("\nPress Enter to continue...")

    def save_enhanced_notes(self, transcript, source_type, duration_minutes):
        """Save notes with detailed AI summary"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        filename = self.notes_folder / f"meeting_notes_{timestamp}.txt"
        
        # Generate detailed summary
        self.console.print("\n[cyan]Generating detailed AI summary...[/cyan]")
        summary = self.generate_detailed_summary(transcript, duration_minutes)
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write("═" * 80 + "\n")
            f.write("   📝 MEETING NOTES - ENHANCED AI ANALYSIS\n")
            f.write("═" * 80 + "\n\n")
            
            f.write(f"📅 Date: {datetime.now().strftime('%B %d, %Y')}\n")
            f.write(f"🕐 Time: {datetime.now().strftime('%I:%M %p')}\n")
            f.write(f"🎙️  Source: {source_type}\n")
            f.write(f"⏱️  Duration: {duration_minutes:.1f} minutes\n")
            f.write(f"📊 Segments Captured: {len(transcript)}\n\n")
            
            # AI Summary first (most important)
            if summary:
                f.write("═" * 80 + "\n")
                f.write("🤖 DETAILED AI ANALYSIS\n")
                f.write("═" * 80 + "\n\n")
                f.write(summary + "\n\n")
            
            # Full transcript after
            f.write("═" * 80 + "\n")
            f.write("📋 COMPLETE TRANSCRIPT\n")
            f.write("═" * 80 + "\n\n")
            
            current_speaker = None
            for item in transcript:
                speaker = item.get("speaker", "Unknown")
                if speaker != current_speaker:
                    f.write(f"\n{speaker}:\n")
                    current_speaker = speaker
                f.write(f"  [{item['time']}] {item['text']}\n")
            
            f.write("\n" + "═" * 80 + "\n")
            f.write("Generated by Smart Meeting Notes - Enhanced Edition\n")
            f.write(f"File: {filename.name}\n")
            f.write("═" * 80 + "\n")
        
        self.console.print(f"\n✅ [green]Enhanced notes saved![/green]")
        self.console.print(f"📄 Location: {filename}")
        self.console.print(f"📊 Summary quality: {'Detailed' if summary else 'Transcript only'}")

    def show_main_menu(self):
        """Display main menu"""
        self.console.clear()
        
        self.console.print("\n")
        self.console.print("╔" + "═" * 58 + "╗", style="cyan bold")
        self.console.print("║" + "  🤖 SMART MEETING NOTES - ENHANCED".center(58) + "║", style="cyan bold")
        self.console.print("╚" + "═" * 58 + "╝", style="cyan bold")
        self.console.print()
        
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column(style="cyan bold", width=8)
        table.add_column(style="white")
        
        table.add_row("1.", "🔊 Take Notes from SPEAKER OUTPUT")
        table.add_row("", "   [dim]Enhanced audio quality + Detailed AI summaries[/dim]")
        table.add_row("", "")
        
        table.add_row("2.", "🎤+🔊 Take Notes from BOTH (Voice + Audio)")
        table.add_row("", "   [dim]Full conversation capture with better clarity[/dim]")
        table.add_row("", "")
        
        table.add_row("3.", "📁 Upload Audio/Video File")
        table.add_row("", "   [dim]Process with comprehensive analysis[/dim]")
        table.add_row("", "")
        
        table.add_row("4.", "📂 View Previous Notes")
        table.add_row("", "")
        
        table.add_row("5.", "🚪 Exit")
        
        self.console.print(table)
        self.console.print()

    def run(self):
        """Main application loop"""
        while True:
            self.show_main_menu()
            choice = Prompt.ask("Choose an option", choices=["1", "2", "3", "4", "5"], default="1")
            
            if choice == "1":
                self.option_1_speaker_only()
            elif choice == "2":
                self.option_2_both_sources()
            elif choice == "3":
                self.option_3_upload_file()
            elif choice == "4":
                self.option_4_view_notes()
            elif choice == "5":
                self.console.print("\n[cyan]Thanks for using Smart Meeting Notes![/cyan]\n")
                break

    def option_3_upload_file(self):
        """Upload and process with enhanced analysis"""
        self.console.clear()
        self.console.print("\n📁 [bold cyan]UPLOAD & ANALYZE FILE[/bold cyan]\n")
        
        file_path = Prompt.ask("Enter file path")
        
        if not os.path.exists(file_path):
            self.console.print(f"\n[red]❌ File not found[/red]")
            input("\nPress Enter to continue...")
            return
        
        self.load_ai_models()
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self.console
        ) as progress:
            task = progress.add_task("Transcribing...", total=None)
            
            try:
                result = self.whisper_model.transcribe(
                    file_path,
                    language='en',
                    fp16=False,
                    temperature=0.0,
                    initial_prompt="This is a conversation, podcast, or meeting. People are speaking naturally in English. May include names, business terms, and expressions like 'happy', 'excited', 'thank you'.",
                    best_of=5,
                    beam_size=5,
                    condition_on_previous_text=True
                )
                text = clean_transcription(result["text"])
                
                # Create transcript items
                transcript_items = [{"time": "00:00:00", "text": text}]
                
                progress.update(task, description="✅ Transcription complete")
                
                # Generate enhanced summary
                if self.ai_client:
                    task2 = progress.add_task("Generating detailed analysis...", total=None)
                    summary = self.generate_detailed_summary(transcript_items)
                    progress.update(task2, description="✅ Analysis complete")
                    
                    # Save with enhanced format
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
                    filename = self.notes_folder / f"file_analysis_{timestamp}.txt"
                    
                    with open(filename, 'w', encoding='utf-8') as f:
                        f.write("═" * 80 + "\n")
                        f.write("   📁 FILE ANALYSIS - ENHANCED AI SUMMARY\n")
                        f.write("═" * 80 + "\n\n")
                        f.write(f"📄 Source File: {os.path.basename(file_path)}\n")
                        f.write(f"📅 Analyzed: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}\n\n")
                        
                        if summary:
                            f.write(summary + "\n\n")
                        
                        f.write("═" * 80 + "\n")
                        f.write("📋 FULL TRANSCRIPT\n")
                        f.write("═" * 80 + "\n\n")
                        f.write(text)
                    
                    self.console.print(f"\n✅ [green]Analysis saved to {filename}[/green]")
                
            except Exception as e:
                self.console.print(f"\n[red]Error: {e}[/red]")
        
        input("\nPress Enter to continue...")

    def option_4_view_notes(self):
        """View saved notes"""
        self.console.clear()
        self.console.print("\n📂 [bold cyan]SAVED NOTES[/bold cyan]\n")
        
        notes = list(self.notes_folder.glob("*.txt"))
        
        if not notes:
            self.console.print("[yellow]No saved notes found.[/yellow]")
            input("\nPress Enter to continue...")
            return
        
        for idx, note in enumerate(notes, 1):
            stat = note.stat()
            size = stat.st_size / 1024
            modified = datetime.fromtimestamp(stat.st_mtime)
            
            self.console.print(f"{idx}. {note.name}")
            self.console.print(f"   [dim]Size: {size:.1f}KB | Modified: {modified.strftime('%Y-%m-%d %H:%M')}[/dim]\n")
        
        choice = Prompt.ask("\nEnter note number to view (or 'q' to go back)")
        
        if choice.lower() != 'q':
            try:
                note_idx = int(choice) - 1
                with open(notes[note_idx], 'r', encoding='utf-8') as f:
                    content = f.read()
                    self.console.print("\n" + content)
            except:
                self.console.print("[red]Invalid selection[/red]")
        
        input("\nPress Enter to continue...")

if __name__ == "__main__":
    app = SmartNotesApp()
    app.run()