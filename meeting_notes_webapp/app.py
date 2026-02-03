import os
import json
import time
import threading
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file
from flask_socketio import SocketIO, emit
from flask_cors import CORS
import whisper
from openai import OpenAI
import pyaudio
import numpy as np
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

load_dotenv()

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['NOTES_FOLDER'] = 'notes'
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB max file size

# Create folders
Path(app.config['UPLOAD_FOLDER']).mkdir(exist_ok=True)
Path(app.config['NOTES_FOLDER']).mkdir(exist_ok=True)

# Initialize extensions
socketio = SocketIO(app, cors_allowed_origins="*")
CORS(app)

# Global variables for recording
recording_active = False
recording_paused = False
recording_thread = None
audio_stream = None

class MeetingAssistant:
    def __init__(self):
        print("Loading AI models...")

        # Load Whisper
        self.whisper_model = whisper.load_model("base")
        print("Whisper model loaded")
        
        # Setup AI providers
        self.setup_ai_providers()
        
    def setup_ai_providers(self):
        """Setup available AI providers"""
        self.providers = {}

        # Groq (Fast & Free)
        groq_key = os.getenv("GROQ_API_KEY")
        if groq_key:
            try:
                self.providers['groq'] = OpenAI(
                    api_key=groq_key,
                    base_url="https://api.groq.com/openai/v1"
                )
                print("Groq API configured")
            except Exception as e:
                print(f"Warning - Groq setup error: {e}")

        # DeepSeek (Cheap)
        deepseek_key = os.getenv("DEEPSEEK_API_KEY")
        if deepseek_key:
            try:
                self.providers['deepseek'] = OpenAI(
                    api_key=deepseek_key,
                    base_url="https://api.deepseek.com"
                )
                print("DeepSeek API configured")
            except Exception as e:
                print(f"Warning - DeepSeek setup error: {e}")

        # OpenAI
        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key:
            try:
                self.providers['openai'] = OpenAI(api_key=openai_key)
                print("OpenAI API configured")
            except Exception as e:
                print(f"Warning - OpenAI setup error: {e}")

        print(f"Available AI providers: {list(self.providers.keys())}")
    
    def transcribe_audio(self, audio_data):
        """Transcribe audio using Whisper"""
        try:
            result = self.whisper_model.transcribe(audio_data)
            return result["text"].strip()
        except Exception as e:
            print(f"Transcription error: {e}")
            return ""
    
    def analyze_with_ai(self, text, provider='groq'):
        """Analyze text with selected AI provider"""
        if not text or len(text) < 10:
            return {"summary": "", "actions": [], "decisions": []}

        if provider not in self.providers:
            # Fallback to simple analysis
            return self.simple_analysis(text)

        try:
            return self.analyze_with_openai(text, provider)
        except Exception as e:
            print(f"AI analysis error: {e}")
            return self.simple_analysis(text)
    
    def analyze_with_openai(self, text, provider):
        """Use OpenAI-compatible API (Groq, DeepSeek, OpenAI)"""
        prompt = f"""Analyze meeting segment and extract JSON with summary, actions, decisions:

{text[:3000]}"""

        client = self.providers[provider]

        # Select appropriate model based on provider
        if provider == "groq":
            model = "llama-3.3-70b-versatile"
        elif provider == "deepseek":
            model = "deepseek-chat"
        else:
            model = "gpt-3.5-turbo"
        
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "Extract meeting insights. Return valid JSON."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=300,
            temperature=0.2
        )
        
        content = response.choices[0].message.content
        
        try:
            import json
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            return json.loads(content)
        except:
            return self.simple_analysis(text)
    
    def simple_analysis(self, text):
        """Simple rule-based analysis"""
        import re
        
        # Extract potential action items
        actions = []
        patterns = [
            r'(\w+)\s+(?:will|should|to)\s+(.+)',
            r'assigned to\s+(\w+)[\s:,]+(.+)',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                if len(match) == 2:
                    actions.append(f"{match[0]}: {match[1]}")
        
        # Create summary (first 2 sentences)
        sentences = [s.strip() for s in text.split('.') if s.strip()]
        summary = '. '.join(sentences[:2]) + '.' if len(sentences) >= 2 else text[:200]
        
        return {
            "summary": summary,
            "actions": actions[:3],
            "decisions": []
        }
    
    def process_file(self, filepath, options):
        """Process uploaded file"""
        # Transcribe
        result = self.whisper_model.transcribe(filepath)
        transcript = result["text"]
        
        # Analyze with AI
        provider = options.get('model', 'gemini')
        analysis = self.analyze_with_ai(transcript, provider)
        
        return {
            "transcript": transcript,
            "summary": analysis.get("summary", ""),
            "actions": analysis.get("actions", []),
            "decisions": analysis.get("decisions", [])
        }
    
    def save_notes(self, data, source_type):
        """Save notes to file"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"meeting_{source_type}_{timestamp}.json"
        filepath = Path(app.config['NOTES_FOLDER']) / filename
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        return filename

# Initialize assistant
assistant = MeetingAssistant()

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/devices')
def get_devices():
    """Get list of audio devices"""
    p = pyaudio.PyAudio()
    devices = []
    
    for i in range(p.get_device_count()):
        info = p.get_device_info_by_index(i)
        if info['maxInputChannels'] > 0:
            devices.append({
                "id": i,
                "name": info['name'],
                "inputs": info['maxInputChannels'],
                "rate": int(info['defaultSampleRate'])
            })
    
    p.terminate()
    return jsonify(devices)

@app.route('/api/process-file', methods=['POST'])
def process_file():
    """Process uploaded audio/video file"""
    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400
    
    # Save uploaded file
    filename = secure_filename(file.filename)
    filepath = Path(app.config['UPLOAD_FOLDER']) / filename
    file.save(filepath)
    
    # Get processing options
    options = {
        'generateSummary': request.form.get('generateSummary') == 'true',
        'extractActions': request.form.get('extractActions') == 'true',
        'detectDecisions': request.form.get('detectDecisions') == 'true',
        'model': request.form.get('model', 'gemini')
    }
    
    try:
        # Process file
        result = assistant.process_file(str(filepath), options)
        
        # Save notes
        notes_data = {
            "title": filename,
            "timestamp": datetime.now().isoformat(),
            "source": "upload",
            "file": filename,
            **result
        }
        
        notes_file = assistant.save_notes(notes_data, "upload")
        
        return jsonify({
            **result,
            "notes_file": notes_file
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/notes')
def get_notes():
    """Get list of saved notes"""
    notes = []
    notes_folder = Path(app.config['NOTES_FOLDER'])
    
    for filepath in sorted(notes_folder.glob("*.json"), key=os.path.getmtime, reverse=True):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            notes.append({
                "id": filepath.stem,
                "title": data.get("title", "Meeting Notes"),
                "date": datetime.fromisoformat(data.get("timestamp")).strftime("%Y-%m-%d %H:%M"),
                "preview": data.get("summary", "")[:100] + "...",
                "duration": data.get("duration", "N/A"),
                "type": data.get("source", "unknown").title(),
                "size": f"{filepath.stat().st_size / 1024:.1f} KB"
            })
        except:
            continue
    
    return jsonify(notes)

@app.route('/api/notes/<note_id>')
def get_note_details(note_id):
    """Get detailed note information"""
    filepath = Path(app.config['NOTES_FOLDER']) / f"{note_id}.json"
    
    if not filepath.exists():
        return jsonify({"error": "Note not found"}), 404
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        return jsonify(data)
    except:
        return jsonify({"error": "Error reading note"}), 500

@app.route('/api/notes/<note_id>/download')
def download_note(note_id):
    """Download note as text file"""
    filepath = Path(app.config['NOTES_FOLDER']) / f"{note_id}.json"
    
    if not filepath.exists():
        return jsonify({"error": "Note not found"}), 404
    
    # Create text version
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    text_content = f"""MEETING NOTES
=============

Title: {data.get('title', 'Meeting Notes')}
Date: {datetime.fromisoformat(data.get('timestamp')).strftime('%Y-%m-%d %H:%M:%S')}
Source: {data.get('source', 'unknown')}

TRANSCRIPT:
{data.get('transcript', '')}

SUMMARY:
{data.get('summary', '')}

ACTION ITEMS:
{chr(10).join(f'- {item}' for item in data.get('actions', []))}

DECISIONS:
{chr(10).join(f'- {item}' for item in data.get('decisions', []))}
"""
    
    # Create temporary text file
    temp_file = Path(app.config['NOTES_FOLDER']) / f"{note_id}.txt"
    with open(temp_file, 'w', encoding='utf-8') as f:
        f.write(text_content)
    
    return send_file(
        temp_file,
        as_attachment=True,
        download_name=f"meeting_notes_{note_id}.txt",
        mimetype='text/plain'
    )

# Socket.IO events
@socketio.on('start_recording')
def handle_start_recording(data):
    global recording_active, recording_paused, recording_thread, audio_stream
    
    if recording_active:
        emit('error', {'message': 'Recording already in progress'})
        return
    
    recording_active = True
    recording_paused = False
    
    # Start recording in background thread
    recording_thread = threading.Thread(
        target=record_audio,
        args=(data.get('deviceId', 0), data.get('type', 'microphone'))
    )
    recording_thread.start()
    
    emit('recording_status', {'status': 'Recording started'})

@socketio.on('stop_recording')
def handle_stop_recording():
    global recording_active, recording_paused
    
    recording_active = False
    recording_paused = False
    
    emit('recording_status', {'status': 'Recording stopped'})
    emit('analysis_update', {
        'summary': 'Recording complete. Generating final summary...',
        'actions': []
    })

@socketio.on('pause_recording')
def handle_pause_recording():
    global recording_paused
    recording_paused = True
    emit('recording_status', {'status': 'Recording paused'})

@socketio.on('resume_recording')
def handle_resume_recording():
    global recording_paused
    recording_paused = False
    emit('recording_status', {'status': 'Recording resumed'})

def record_audio(device_id, capture_type):
    """Record audio in a separate thread"""
    global recording_active, recording_paused, audio_stream
    
    p = pyaudio.PyAudio()
    
    try:
        # Open audio stream
        audio_stream = p.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=16000,
            input=True,
            input_device_index=device_id,
            frames_per_buffer=16000 * 5  # 5-second chunks
        )
        
        chunk_count = 0
        
        while recording_active:
            if recording_paused:
                time.sleep(0.1)
                continue
            
            # Read audio chunk
            audio_data = audio_stream.read(16000 * 5, exception_on_overflow=False)
            
            # Convert to numpy array
            audio_np = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0
            
            # Transcribe
            transcript = assistant.transcribe_audio(audio_np)
            
            if transcript:
                # Emit transcript
                socketio.emit('transcript_update', {
                    'timestamp': datetime.now().strftime("%H:%M:%S"),
                    'text': transcript
                })
                
                # Analyze with AI (every 3 chunks to reduce API calls)
                chunk_count += 1
                if chunk_count % 3 == 0:
                    analysis = assistant.analyze_with_ai(transcript)
                    socketio.emit('analysis_update', analysis)
            
            time.sleep(0.1)
            
    except Exception as e:
        socketio.emit('error', {'message': str(e)})
    
    finally:
        if audio_stream:
            audio_stream.stop_stream()
            audio_stream.close()
        p.terminate()

if __name__ == '__main__':
    print("\n" + "="*50)
    print("   Smart Meeting Notes Web App")
    print("   Running on http://localhost:5000")
    print("="*50)
    print("\nUploads folder:", app.config['UPLOAD_FOLDER'])
    print("Notes folder:", app.config['NOTES_FOLDER'])
    print("\nPress Ctrl+C to stop\n")

    socketio.run(app, debug=True, host='0.0.0.0', port=5000)