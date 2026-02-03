"""
Smart Meeting Notes - AI-Powered Note Taker
Captures meetings from speaker output, microphone, or uploaded files
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

from meeting_capture import MeetingCapture
import whisper
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

class SmartNotesApp:
    def __init__(self):
        self.console = Console()
        self.notes_folder = Path("meeting_notes")
        self.notes_folder.mkdir(exist_ok=True)

        # AI Setup
        self.whisper_model = None
        self.ai_client = None
        self.ai_model = None

    def show_main_menu(self):
        """Display main menu"""
        self.console.clear()

        # Create header
        self.console.print("\n")
        self.console.print("╔" + "═" * 58 + "╗", style="cyan bold")
        self.console.print("║" + "  🤖 SMART MEETING NOTES - AI Note Taker".center(58) + "║", style="cyan bold")
        self.console.print("╚" + "═" * 58 + "╝", style="cyan bold")
        self.console.print()

        # Create menu table
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column(style="cyan bold", width=8)
        table.add_column(style="white")

        table.add_row("1.", "🔊 Take Notes from SPEAKER OUTPUT (Zoom/Teams/Meet)")
        table.add_row("", "   [dim]Perfect for online meetings - captures what you hear[/dim]")
        table.add_row("", "")

        table.add_row("2.", "🎤+🔊 Take Notes from BOTH (Your Voice + Meeting Audio)")
        table.add_row("", "   [dim]Best for active participation - full conversation capture[/dim]")
        table.add_row("", "")

        table.add_row("3.", "📁 Upload Audio/Video File and Get Summary")
        table.add_row("", "   [dim]Process recorded meetings or video files[/dim]")
        table.add_row("", "")

        table.add_row("4.", "📂 View & Download Previous Notes")
        table.add_row("", "   [dim]Access your saved meeting notes[/dim]")
        table.add_row("", "")

        table.add_row("5.", "❌ Exit")

        panel = Panel(table, border_style="cyan", padding=(1, 2))
        self.console.print(panel)
        self.console.print()

        choice = Prompt.ask(
            "Choose an option",
            choices=["1", "2", "3", "4", "5"],
            default="1"
        )

        return choice

    def load_ai_models(self):
        """Load AI models"""
        if self.whisper_model is None:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=self.console
            ) as progress:
                task = progress.add_task("Loading Whisper model...", total=None)
                self.whisper_model = whisper.load_model("base")
                progress.update(task, description="✅ Whisper model loaded")

        if self.ai_client is None:
            provider = os.getenv("AI_PROVIDER", "groq")

            if provider == "groq":
                api_key = os.getenv("GROQ_API_KEY")
                if api_key:
                    self.ai_client = OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")
                    self.ai_model = os.getenv("AI_MODEL", "llama-3.3-70b-versatile")
                    self.console.print(f"✅ AI Model: {self.ai_model} (Groq)", style="green")
            elif provider == "deepseek":
                api_key = os.getenv("DEEPSEEK_API_KEY")
                if api_key:
                    self.ai_client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
                    self.ai_model = os.getenv("AI_MODEL", "deepseek-chat")
                    self.console.print(f"✅ AI Model: {self.ai_model} (DeepSeek)", style="green")
            elif provider == "openai":
                api_key = os.getenv("OPENAI_API_KEY")
                if api_key:
                    self.ai_client = OpenAI(api_key=api_key)
                    self.ai_model = os.getenv("AI_MODEL", "gpt-3.5-turbo")
                    self.console.print(f"✅ AI Model: {self.ai_model} (OpenAI)", style="green")

            if self.ai_client is None:
                self.console.print("⚠️  No API key found. AI summaries will be basic.", style="yellow")

    def option_1_speaker_only(self):
        """Option 1: Capture from speaker output"""
        self.console.clear()
        self.console.print("\n🔊 [bold cyan]CAPTURING FROM SPEAKER OUTPUT[/bold cyan]\n")
        self.console.print("[dim]This will capture audio from Zoom, Teams, Google Meet, etc.[/dim]")
        self.console.print("[dim]Make sure your meeting is playing![/dim]\n")

        self.load_ai_models()

        # Start capture
        self.run_live_capture(capture_both=False, source_type="speaker")

    def option_2_both(self):
        """Option 2: Capture from both mic and speaker"""
        self.console.clear()
        self.console.print("\n🎤+🔊 [bold cyan]CAPTURING FROM BOTH SOURCES[/bold cyan]\n")
        self.console.print("[dim]This will capture both your voice and meeting audio[/dim]\n")

        self.load_ai_models()

        # Start capture
        self.run_live_capture(capture_both=True, source_type="both")

    def run_live_capture(self, capture_both=False, source_type="speaker"):
        """Run live audio capture"""
        capture = MeetingCapture()
        transcript = []
        notes_data = []
        is_recording = True

        # Start capture
        try:
            capture.start_capture(device_index=None, capture_both=capture_both)
            self.console.print("\n✅ [green]Recording started![/green]")
            self.console.print("[yellow]Press Ctrl+C to stop recording[/yellow]\n")
            self.console.print("─" * 60)

            # Process audio
            def process_audio():
                nonlocal transcript, notes_data, is_recording
                while is_recording:
                    audio_chunk = capture.get_audio_chunk()
                    if audio_chunk is not None:
                        result = self.whisper_model.transcribe(audio_chunk)
                        text = result["text"].strip()

                        if text:
                            timestamp = datetime.now().strftime("%H:%M:%S")
                            transcript.append({"time": timestamp, "text": text})

                            self.console.print(f"[dim]{timestamp}[/dim] {text}")

                            # AI analysis
                            if self.ai_client and len(text) > 15:
                                analysis = self.quick_analysis(text)
                                if analysis:
                                    notes_data.append({"time": timestamp, "analysis": analysis})

            thread = threading.Thread(target=process_audio, daemon=True)
            thread.start()

            # Wait for user to stop
            try:
                while is_recording:
                    time.sleep(0.5)
            except KeyboardInterrupt:
                self.console.print("\n\n[yellow]Stopping recording...[/yellow]")

        finally:
            is_recording = False
            capture.stop()

            # Generate and save notes
            if transcript:
                self.save_human_notes(transcript, notes_data, source_type)
            else:
                self.console.print("\n[red]No audio was captured.[/red]")

            input("\nPress Enter to continue...")

    def quick_analysis(self, text):
        """Quick AI analysis of text chunk"""
        try:
            response = self.ai_client.chat.completions.create(
                model=self.ai_model,
                messages=[
                    {"role": "system", "content": "Extract key points, action items, or decisions. Be brief."},
                    {"role": "user", "content": f"Analyze: {text}"}
                ],
                max_tokens=100,
                temperature=0.3
            )
            return response.choices[0].message.content.strip()
        except:
            return None

    def option_3_upload_file(self):
        """Option 3: Upload and process audio/video file"""
        self.console.clear()
        self.console.print("\n📁 [bold cyan]UPLOAD AUDIO/VIDEO FILE[/bold cyan]\n")

        # Ask for file path
        file_path = Prompt.ask("Enter the path to your audio/video file")

        if not os.path.exists(file_path):
            self.console.print(f"\n[red]❌ File not found: {file_path}[/red]")
            input("\nPress Enter to continue...")
            return

        self.console.print(f"\n[green]✅ File found: {os.path.basename(file_path)}[/green]")
        self.load_ai_models()

        # Process file
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self.console
        ) as progress:
            task = progress.add_task("Transcribing audio...", total=None)

            try:
                result = self.whisper_model.transcribe(file_path)
                text = result["text"]

                progress.update(task, description="✅ Transcription complete")

                self.console.print(f"\n[green]✅ Transcription completed![/green]")
                self.console.print(f"[dim]Length: {len(text)} characters[/dim]\n")

                # Generate summary
                if self.ai_client:
                    task2 = progress.add_task("Generating AI summary...", total=None)
                    summary = self.generate_file_summary(text)
                    progress.update(task2, description="✅ Summary generated")
                else:
                    summary = None

                # Save
                self.save_file_notes(file_path, text, summary)

            except Exception as e:
                self.console.print(f"\n[red]❌ Error processing file: {e}[/red]")

        input("\nPress Enter to continue...")

    def generate_file_summary(self, full_text):
        """Generate comprehensive summary from full transcript"""
        try:
            prompt = f"""Analyze this meeting transcript and create a comprehensive summary.

Transcript:
{full_text[:4000]}

Provide:
1. Brief Overview (2-3 sentences)
2. Key Topics Discussed
3. Important Points
4. Action Items (if any)
5. Decisions Made (if any)
6. Questions Raised (if any)

Format it in a clear, readable way."""

            response = self.ai_client.chat.completions.create(
                model=self.ai_model,
                messages=[
                    {"role": "system", "content": "You are a professional meeting analyst. Create clear, actionable summaries."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=1000,
                temperature=0.3
            )

            return response.choices[0].message.content

        except Exception as e:
            return f"Error generating summary: {e}"

    def save_human_notes(self, transcript, notes_data, source_type):
        """Save notes in human-readable format"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        filename = self.notes_folder / f"meeting_notes_{timestamp}.txt"

        with open(filename, 'w', encoding='utf-8') as f:
            f.write("═" * 70 + "\n")
            f.write("   📝 MEETING NOTES - AI GENERATED SUMMARY\n")
            f.write("═" * 70 + "\n\n")

            f.write(f"📅 Date: {datetime.now().strftime('%B %d, %Y')}\n")
            f.write(f"🕐 Time: {datetime.now().strftime('%I:%M %p')}\n")
            f.write(f"🎙️  Source: {source_type.upper()}\n")
            f.write(f"⏱️  Duration: {len(transcript)} segments\n\n")

            f.write("─" * 70 + "\n")
            f.write("📋 FULL TRANSCRIPT\n")
            f.write("─" * 70 + "\n\n")

            for item in transcript:
                f.write(f"[{item['time']}] {item['text']}\n\n")

            # AI Summary if available
            if self.ai_client and transcript:
                f.write("\n" + "─" * 70 + "\n")
                f.write("🤖 AI ANALYSIS & SUMMARY\n")
                f.write("─" * 70 + "\n\n")

                full_text = " ".join([item['text'] for item in transcript])
                summary = self.generate_file_summary(full_text)
                f.write(summary + "\n\n")

            f.write("\n" + "═" * 70 + "\n")
            f.write("Generated by Smart Meeting Notes\n")
            f.write(f"File: {filename.name}\n")
            f.write("═" * 70 + "\n")

        self.console.print(f"\n\n✅ [green]Notes saved successfully![/green]")
        self.console.print(f"📁 Location: [cyan]{filename}[/cyan]")

    def save_file_notes(self, file_path, transcript, summary):
        """Save notes from uploaded file"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        original_name = Path(file_path).stem
        filename = self.notes_folder / f"summary_{original_name}_{timestamp}.txt"

        with open(filename, 'w', encoding='utf-8') as f:
            f.write("═" * 70 + "\n")
            f.write("   📝 AUDIO/VIDEO FILE SUMMARY\n")
            f.write("═" * 70 + "\n\n")

            f.write(f"📁 Original File: {os.path.basename(file_path)}\n")
            f.write(f"📅 Processed: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}\n\n")

            f.write("─" * 70 + "\n")
            f.write("📋 FULL TRANSCRIPT\n")
            f.write("─" * 70 + "\n\n")
            f.write(transcript + "\n\n")

            if summary:
                f.write("─" * 70 + "\n")
                f.write("🤖 AI SUMMARY & ANALYSIS\n")
                f.write("─" * 70 + "\n\n")
                f.write(summary + "\n\n")

            f.write("\n" + "═" * 70 + "\n")
            f.write("Generated by Smart Meeting Notes\n")
            f.write("═" * 70 + "\n")

        self.console.print(f"\n✅ [green]Summary saved successfully![/green]")
        self.console.print(f"📁 Location: [cyan]{filename}[/cyan]")

    def option_4_view_notes(self):
        """Option 4: View and download previous notes"""
        self.console.clear()
        self.console.print("\n📂 [bold cyan]YOUR SAVED NOTES[/bold cyan]\n")

        # List all notes files
        notes_files = sorted(self.notes_folder.glob("*.txt"), key=os.path.getmtime, reverse=True)

        if not notes_files:
            self.console.print("[yellow]No saved notes found.[/yellow]")
            input("\nPress Enter to continue...")
            return

        # Create table
        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("#", style="cyan", width=4)
        table.add_column("File Name", style="white")
        table.add_column("Date", style="dim")
        table.add_column("Size", style="green")

        for idx, file in enumerate(notes_files[:20], 1):  # Show last 20
            stat = file.stat()
            date = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
            size = f"{stat.st_size / 1024:.1f} KB"
            table.add_row(str(idx), file.name, date, size)

        self.console.print(table)
        self.console.print()

        choice = Prompt.ask(
            "Enter number to view, 'open' to open folder, or 'back' to return",
            default="back"
        )

        if choice.lower() == "back":
            return
        elif choice.lower() == "open":
            os.startfile(self.notes_folder)
            input("\nPress Enter to continue...")
        elif choice.isdigit() and 1 <= int(choice) <= len(notes_files):
            # Display file content
            file = notes_files[int(choice) - 1]
            self.console.clear()
            self.console.print(f"\n📄 [bold]{file.name}[/bold]\n")

            with open(file, 'r', encoding='utf-8') as f:
                content = f.read()
                self.console.print(content)

            input("\nPress Enter to continue...")

    def run(self):
        """Main application loop"""
        while True:
            choice = self.show_main_menu()

            if choice == "1":
                self.option_1_speaker_only()
            elif choice == "2":
                self.option_2_both()
            elif choice == "3":
                self.option_3_upload_file()
            elif choice == "4":
                self.option_4_view_notes()
            elif choice == "5":
                self.console.print("\n[cyan]👋 Goodbye![/cyan]\n")
                break

def main():
    app = SmartNotesApp()
    app.run()

if __name__ == "__main__":
    main()
