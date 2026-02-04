# Safe fallback version - works even without VAD libraries

import os
os.environ["PATH"] = r"C:\ProgramData\chocolatey\bin" + os.pathsep + os.environ.get("PATH", "")

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

# Try to import VAD libraries, but don't fail if they're missing
VAD_AVAILABLE = False
try:
    import webrtcvad
    import noisereduce as nr
    from scipy import signal as scipy_signal
    VAD_AVAILABLE = True
    print("✅ Voice Activity Detection enabled")
except ImportError as e:
    print(f"⚠️  VAD libraries not available: {e}")
    print("   Running without noise suppression (will still work!)")
    print("   To enable: pip install webrtcvad noisereduce scipy")

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['NOTES_FOLDER'] = 'notes'
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024

Path(app.config['UPLOAD_FOLDER']).mkdir(exist_ok=True)
Path(app.config['NOTES_FOLDER']).mkdir(exist_ok=True)

socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')
CORS(app)

recording_active = False
recording_paused = False
recording_thread = None
audio_stream = None
live_transcript = []

class BasicNoiseFilter:
    """Basic noise filtering without external libraries"""

    def __init__(self):
        self.noise_threshold = 0.005  # Reduced from 0.01 for better sensitivity

    def is_speech(self, audio_data):
        """Simple volume-based speech detection"""
        if isinstance(audio_data, bytes):
            audio_np = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0
        else:
            audio_np = audio_data

        # Check if audio is loud enough
        volume = np.mean(np.abs(audio_np))
        print(f"🔍 BasicNoiseFilter - Volume: {volume:.4f}, Threshold: {self.noise_threshold}")
        return volume > self.noise_threshold

    def process_audio(self, audio_chunk):
        """Basic processing - just volume check"""
        if self.is_speech(audio_chunk):
            print("✅ BasicNoiseFilter - Speech detected")
            return audio_chunk
        print("⚠️  BasicNoiseFilter - No speech detected")
        return None

class AdvancedNoiseSuppressionProcessor:
    """Advanced noise suppression (only if libraries available)"""
    
    def __init__(self, sample_rate=16000):
        self.sample_rate = sample_rate
        self.vad = webrtcvad.Vad()
        self.vad.set_mode(2)  # Mode 2 = balanced (not too aggressive)
        self.noise_profile = None
        self.calibration_complete = False
        print("✅ Advanced VAD initialized")
        
    def is_speech(self, audio_data_bytes, sample_rate=16000):
        """Detect speech using WebRTC VAD"""
        try:
            frame_duration_ms = 30
            frame_size = int(sample_rate * frame_duration_ms / 1000)

            if isinstance(audio_data_bytes, np.ndarray):
                audio_int16 = (audio_data_bytes * 32768).astype(np.int16)
                audio_bytes = audio_int16.tobytes()
            else:
                audio_bytes = audio_data_bytes

            speech_frames = 0
            total_frames = 0

            for i in range(0, len(audio_bytes) - frame_size * 2, frame_size * 2):
                frame = audio_bytes[i:i + frame_size * 2]
                if len(frame) == frame_size * 2:
                    try:
                        if self.vad.is_speech(frame, sample_rate):
                            speech_frames += 1
                        total_frames += 1
                    except:
                        continue

            if total_frames > 0:
                speech_ratio = speech_frames / total_frames
                print(f"🔍 AdvancedVAD - Speech ratio: {speech_ratio:.2%} ({speech_frames}/{total_frames} frames)")
                return speech_ratio > 0.05  # Reduced to 5% for much better sensitivity
            return False

        except Exception as e:
            print(f"⚠️  VAD error: {e}, assuming speech")
            return True  # If error, assume speech
    
    def reduce_noise(self, audio_chunk):
        """Apply noise reduction"""
        try:
            reduced_audio = nr.reduce_noise(
                y=audio_chunk,
                sr=self.sample_rate,
                stationary=True,
                prop_decrease=0.8
            )
            return reduced_audio
        except:
            return audio_chunk
    
    def process_audio(self, audio_chunk):
        """Process with VAD and noise reduction"""
        if not self.is_speech(audio_chunk, self.sample_rate):
            return None
        
        return self.reduce_noise(audio_chunk)

class MeetingAssistant:
    def __init__(self):
        print("Loading AI models...")
        
        try:
            self.whisper_model = whisper.load_model("base")
            print("✅ Whisper model loaded")
        except Exception as e:
            print(f"❌ Whisper loading error: {e}")
            self.whisper_model = None
        
        # Initialize appropriate noise processor
        # For now, use BasicNoiseFilter for better compatibility
        # Change to True to enable AdvancedVAD (more aggressive filtering)
        USE_ADVANCED_VAD = False

        if VAD_AVAILABLE and USE_ADVANCED_VAD:
            try:
                self.noise_processor = AdvancedNoiseSuppressionProcessor()
            except Exception as e:
                print(f"⚠️  Failed to init advanced VAD: {e}")
                self.noise_processor = BasicNoiseFilter()
        else:
            self.noise_processor = BasicNoiseFilter()
            print("📌 Using BasicNoiseFilter (simpler, more permissive)")
            
        self.setup_ai_providers()
        
    def setup_ai_providers(self):
        self.providers = {}

        groq_key = os.getenv("GROQ_API_KEY")
        if groq_key:
            try:
                self.providers['groq'] = OpenAI(
                    api_key=groq_key,
                    base_url="https://api.groq.com/openai/v1"
                )
                print("✅ Groq API configured")
            except Exception as e:
                print(f"❌ Groq setup error: {e}")

        print(f"✅ Available AI providers: {list(self.providers.keys())}")
    
    def transcribe_audio(self, audio_data):
        """Transcribe with optional noise filtering"""
        if not self.whisper_model:
            print("⚠️  Whisper model not loaded")
            return ""

        try:
            # Check raw audio level first
            raw_level = np.mean(np.abs(audio_data))
            print(f"🎤 Raw audio level: {raw_level:.4f}")

            # Apply noise filtering
            processed_audio = self.noise_processor.process_audio(audio_data)

            if processed_audio is None:
                print("⚠️  No speech detected by noise processor")
                return ""  # No speech detected

            # Check minimum volume (reduced threshold)
            audio_level = np.mean(np.abs(processed_audio))
            print(f"🔊 Processed audio level: {audio_level:.4f}")

            if audio_level < 0.002:  # Reduced from 0.005
                print(f"⚠️  Audio too quiet: {audio_level:.4f} < 0.002")
                return ""

            # Transcribe
            print("🤖 Transcribing with Whisper...")
            result = self.whisper_model.transcribe(processed_audio)
            text = result["text"].strip()

            print(f"📝 Whisper output: '{text}' (length: {len(text)})")

            # Filter short false positives
            if len(text) < 3:
                print(f"⚠️  Text too short: '{text}'")
                return ""

            print(f"✅ Transcription successful: '{text}'")
            return text

        except Exception as e:
            print(f"❌ Transcription error: {e}")
            import traceback
            traceback.print_exc()
            return ""
    
    def analyze_with_ai(self, text, provider='groq', timeout=30):
        if not text or len(text) < 10:
            return {"summary": "", "actions": [], "decisions": [], "key_points": []}

        if provider not in self.providers:
            if self.providers:
                provider = list(self.providers.keys())[0]
            else:
                return self.simple_analysis(text)

        try:
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(self.analyze_with_openai, text, provider)
                try:
                    result = future.result(timeout=timeout)
                    return result
                except concurrent.futures.TimeoutError:
                    return self.simple_analysis(text)
                    
        except Exception as e:
            print(f"❌ AI analysis error: {e}")
            return self.simple_analysis(text)
    
    def analyze_with_openai(self, text, provider):
        prompt = f"""Analyze briefly:

{text[:2000]}

Return JSON:
{{
  "summary": "2-3 sentences",
  "actions": ["item 1"],
  "decisions": ["decision 1"],
  "key_points": ["point 1"]
}}"""

        client = self.providers[provider]
        
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "Return ONLY valid JSON, no markdown."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=400,
            temperature=0.2
        )
        
        content = response.choices[0].message.content
        
        try:
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            
            return json.loads(content)
        except:
            return self.simple_analysis(text)
    
    def simple_analysis(self, text):
        sentences = [s.strip() for s in text.split('.') if s.strip()]
        return {
            "summary": '. '.join(sentences[:2]) + '.' if len(sentences) >= 2 else text[:200],
            "actions": [],
            "decisions": [],
            "key_points": sentences[:3]
        }
    
    def process_file(self, filepath, options):
        try:
            result = self.whisper_model.transcribe(filepath)
            transcript = result["text"]
            
            analysis = {"summary": "", "actions": [], "decisions": [], "key_points": []}
            
            if options.get('generateSummary', True):
                provider = options.get('model', 'groq')
                analysis = self.analyze_with_ai(transcript, provider, timeout=45)
            
            return {
                "transcript": transcript,
                "summary": analysis.get("summary", ""),
                "actions": analysis.get("actions", []),
                "decisions": analysis.get("decisions", []),
                "key_points": analysis.get("key_points", [])
            }
            
        except Exception as e:
            raise
    
    def save_notes(self, data, source_type):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"meeting_{source_type}_{timestamp}.json"
        filepath = Path(app.config['NOTES_FOLDER']) / filename
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        return filename

assistant = MeetingAssistant()

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/devices')
def get_devices():
    try:
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
    except Exception as e:
        print(f"Error getting devices: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/auto-detect-device')
def auto_detect_device():
    """Detect which audio device is currently receiving audio"""
    try:
        p = pyaudio.PyAudio()
        best_device = None
        max_level = 0
        all_devices_data = []

        print("\n🔍 Auto-detecting active audio device...")

        # Sample each device for a short duration to detect audio activity
        for i in range(p.get_device_count()):
            info = p.get_device_info_by_index(i)
            if info['maxInputChannels'] > 0:
                try:
                    # Try to open stream and read audio
                    stream = p.open(
                        format=pyaudio.paInt16,
                        channels=1,
                        rate=int(info['defaultSampleRate']),
                        input=True,
                        input_device_index=i,
                        frames_per_buffer=2048
                    )

                    # Read multiple chunks to get a better sample (increased from 1 to 3)
                    levels = []
                    for _ in range(3):
                        audio_data = stream.read(2048, exception_on_overflow=False)
                        audio_np = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0
                        levels.append(np.mean(np.abs(audio_np)))

                    # Use the average level
                    audio_level = np.mean(levels)

                    stream.stop_stream()
                    stream.close()

                    device_data = {
                        "id": i,
                        "name": info['name'],
                        "level": float(audio_level)
                    }
                    all_devices_data.append(device_data)

                    print(f"  Device {i}: {info['name'][:40]} - Level: {audio_level:.4f}")

                    if audio_level > max_level:
                        max_level = audio_level
                        best_device = {
                            "device_id": i,
                            "device_name": info['name'],
                            "level": float(audio_level)
                        }

                except Exception as e:
                    # Skip devices that can't be opened
                    print(f"  Device {i}: {info['name'][:40]} - Skipped ({str(e)[:30]})")
                    continue

        p.terminate()

        if best_device and max_level > 0.001:  # Minimum threshold
            print(f"\n✅ Best device: {best_device['device_name']} (level: {max_level:.4f})")
            return jsonify({
                "success": True,
                **best_device
            })
        else:
            print(f"\n⚠️  No active audio detected (max level: {max_level:.4f})")
            return jsonify({
                "success": False,
                "message": "No active audio detected. Please play some audio (music, video, or speak) and try again."
            })

    except Exception as e:
        print(f"❌ Error detecting device: {e}")
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500

@app.route('/api/process-file', methods=['POST'])
def process_file():
    try:
        if 'file' not in request.files:
            return jsonify({"error": "No file provided"}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({"error": "No file selected"}), 400
        
        filename = secure_filename(file.filename)
        filepath = Path(app.config['UPLOAD_FOLDER']) / filename
        file.save(filepath)
        
        options = {
            'generateSummary': request.form.get('generateSummary') == 'true',
            'model': request.form.get('model', 'groq')
        }
        
        result = assistant.process_file(str(filepath), options)
        
        notes_data = {
            "title": filename,
            "timestamp": datetime.now().isoformat(),
            "source": "upload",
            **result
        }
        
        notes_file = assistant.save_notes(notes_data, "upload")
        
        return jsonify({
            **result,
            "notes_file": notes_file
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/api/generate-summary', methods=['POST'])
def generate_summary():
    try:
        global live_transcript

        if not live_transcript:
            return jsonify({"error": "No transcript available"}), 400

        full_text = " ".join([entry['text'] for entry in live_transcript])

        if len(full_text) < 20:
            return jsonify({"error": "Transcript too short"}), 400

        provider = request.json.get('provider', 'groq') if request.json else 'groq'
        analysis = assistant.analyze_with_ai(full_text, provider, timeout=45)

        notes_data = {
            "title": f"Live Meeting {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "timestamp": datetime.now().isoformat(),
            "source": "live",
            "transcript": "\n".join([f"[{e['timestamp']}] {e['text']}" for e in live_transcript]),
            **analysis
        }

        notes_file = assistant.save_notes(notes_data, "live")

        return jsonify({
            **analysis,
            "notes_file": notes_file
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/api/notes')
def get_notes():
    """Get all saved notes"""
    try:
        notes_dir = Path(app.config['NOTES_FOLDER'])
        notes = []

        for note_file in notes_dir.glob('*.json'):
            try:
                with open(note_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                    # Extract preview from transcript or summary
                    preview = ""
                    if data.get('summary'):
                        preview = data['summary'][:150] + "..."
                    elif data.get('transcript'):
                        preview = data['transcript'][:150] + "..."

                    # Parse timestamp
                    timestamp = data.get('timestamp', '')
                    try:
                        date_obj = datetime.fromisoformat(timestamp)
                        date_str = date_obj.strftime('%Y-%m-%d %H:%M')
                    except:
                        date_str = 'Unknown date'

                    notes.append({
                        'id': note_file.stem,
                        'title': data.get('title', note_file.stem),
                        'date': date_str,
                        'preview': preview,
                        'duration': 'N/A',  # Can be calculated if needed
                        'type': data.get('source', 'unknown')
                    })
            except Exception as e:
                print(f"Error reading note {note_file}: {e}")
                continue

        # Sort by date (newest first)
        notes.sort(key=lambda x: x['date'], reverse=True)

        return jsonify(notes)
    except Exception as e:
        print(f"Error getting notes: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/notes/<note_id>')
def get_note(note_id):
    """Get a specific note by ID"""
    try:
        note_file = Path(app.config['NOTES_FOLDER']) / f"{note_id}.json"

        if not note_file.exists():
            return jsonify({"error": "Note not found"}), 404

        with open(note_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Parse timestamp
        timestamp = data.get('timestamp', '')
        try:
            date_obj = datetime.fromisoformat(timestamp)
            date_str = date_obj.strftime('%Y-%m-%d %H:%M')
        except:
            date_str = 'Unknown date'

        # Calculate file size
        file_size = note_file.stat().st_size
        size_str = f"{file_size / 1024:.1f} KB"

        return jsonify({
            'id': note_id,
            'title': data.get('title', note_id),
            'date': date_str,
            'duration': 'N/A',
            'type': data.get('source', 'unknown'),
            'size': size_str,
            'transcript': data.get('transcript', ''),
            'summary': data.get('summary', ''),
            'actions': data.get('actions', []),
            'decisions': data.get('decisions', []),
            'key_points': data.get('key_points', []),
            'analysis': data.get('summary', '')  # For full analysis tab
        })
    except Exception as e:
        print(f"Error getting note: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/notes/<note_id>', methods=['DELETE'])
def delete_note(note_id):
    """Delete a specific note"""
    try:
        note_file = Path(app.config['NOTES_FOLDER']) / f"{note_id}.json"

        if not note_file.exists():
            return jsonify({"error": "Note not found"}), 404

        note_file.unlink()
        return jsonify({"success": True, "message": "Note deleted"})
    except Exception as e:
        print(f"Error deleting note: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/notes/<note_id>/download')
def download_note(note_id):
    """Download a note as a text file"""
    try:
        note_file = Path(app.config['NOTES_FOLDER']) / f"{note_id}.json"

        if not note_file.exists():
            return jsonify({"error": "Note not found"}), 404

        with open(note_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Create formatted text content
        content = f"""MEETING NOTES
=============

Title: {data.get('title', 'Untitled')}
Date: {data.get('timestamp', 'Unknown')}
Source: {data.get('source', 'Unknown')}

TRANSCRIPT:
{data.get('transcript', 'No transcript available')}

SUMMARY:
{data.get('summary', 'No summary available')}

KEY POINTS:
{chr(10).join(['- ' + p for p in data.get('key_points', [])])}

ACTION ITEMS:
{chr(10).join(['- ' + a for a in data.get('actions', [])])}

DECISIONS:
{chr(10).join(['- ' + d for d in data.get('decisions', [])])}

Generated by Smart Meeting Notes
"""

        # Create a temporary file
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        return send_file(
            tmp_path,
            as_attachment=True,
            download_name=f"{note_id}.txt",
            mimetype='text/plain'
        )
    except Exception as e:
        print(f"Error downloading note: {e}")
        return jsonify({"error": str(e)}), 500

@socketio.on('start_recording')
def handle_start_recording(data):
    global recording_active, recording_paused, recording_thread, live_transcript
    
    if recording_active:
        emit('error', {'message': 'Recording already in progress'})
        return
    
    recording_active = True
    recording_paused = False
    live_transcript = []
    
    recording_thread = threading.Thread(
        target=record_audio,
        args=(data.get('deviceId', 0), data.get('type', 'microphone'))
    )
    recording_thread.start()
    
    status_msg = 'Recording started'
    if VAD_AVAILABLE:
        status_msg += ' (with noise suppression)'
    
    emit('recording_status', {'status': status_msg})

@socketio.on('stop_recording')
def handle_stop_recording():
    global recording_active
    recording_active = False
    emit('recording_status', {'status': 'Recording stopped'})
    emit('recording_complete', {'message': 'Click "Generate Summary" to analyze'})

@socketio.on('pause_recording')
def handle_pause_recording():
    global recording_paused
    recording_paused = True
    emit('recording_status', {'status': 'Paused'})

@socketio.on('resume_recording')
def handle_resume_recording():
    global recording_paused
    recording_paused = False
    emit('recording_status', {'status': 'Recording...'})

@socketio.on('reset_transcript')
def handle_reset_transcript():
    global live_transcript
    live_transcript = []
    print("🔄 Transcript reset by user")
    emit('recording_status', {'status': 'Ready to record'})

def record_audio(device_id, capture_type):
    global recording_active, recording_paused, audio_stream, live_transcript

    print(f"\n{'='*60}")
    print(f"🎙️  Starting recording from device {device_id} ({capture_type})")
    print(f"{'='*60}\n")

    p = pyaudio.PyAudio()

    try:
        # Get device info
        device_info = p.get_device_info_by_index(device_id)
        print(f"📱 Device: {device_info['name']}")
        print(f"📊 Sample rate: {device_info['defaultSampleRate']}")

        audio_stream = p.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=16000,
            input=True,
            input_device_index=device_id,
            frames_per_buffer=16000 * 5
        )

        print("✅ Audio stream opened successfully")
        chunk_count = 0

        while recording_active:
            if recording_paused:
                time.sleep(0.1)
                continue

            chunk_count += 1
            print(f"\n--- Chunk {chunk_count} ---")

            audio_data = audio_stream.read(16000 * 5, exception_on_overflow=False)
            audio_np = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0

            print(f"📦 Audio chunk size: {len(audio_np)} samples")

            transcript = assistant.transcribe_audio(audio_np)

            if transcript:
                timestamp = datetime.now().strftime("%H:%M:%S")
                live_transcript.append({
                    'timestamp': timestamp,
                    'text': transcript
                })

                print(f"🎯 Emitting transcript update: [{timestamp}] {transcript}")

                socketio.emit('transcript_update', {
                    'timestamp': timestamp,
                    'text': transcript
                })
            else:
                print("⚠️  No transcript generated for this chunk")

            time.sleep(0.1)

    except Exception as e:
        print(f"❌ Recording error: {e}")
        import traceback
        traceback.print_exc()
        socketio.emit('error', {'message': str(e)})
    finally:
        print("\n🛑 Stopping recording...")
        if audio_stream:
            audio_stream.stop_stream()
            audio_stream.close()
        p.terminate()
        print("✅ Recording stopped cleanly")

if __name__ == '__main__':
    print("\n" + "="*50)
    print("   Smart Meeting Notes")
    if VAD_AVAILABLE:
        print("   🔇 Noise Suppression: ENABLED")
    else:
        print("   🔇 Noise Suppression: DISABLED (basic mode)")
    print("   Running on http://localhost:5000")
    print("="*50 + "\n")

    socketio.run(app, debug=True, host='0.0.0.0', port=5000)