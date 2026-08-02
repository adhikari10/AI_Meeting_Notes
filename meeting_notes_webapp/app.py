# Safe fallback version - works even without VAD libraries

import os
import uuid
os.environ["PATH"] = r"C:\ProgramData\chocolatey\bin" + os.pathsep + os.environ.get("PATH", "")

# CLOUD_MODE=true runs the app upload-only, for servers with no audio
# hardware: no PyAudio/device libraries are imported or initialised, local
# Whisper (live-mic only) isn't loaded, and the live-record UI is disabled.
# Default (unset/false) is the existing desktop behaviour, unchanged.
CLOUD_MODE = os.getenv("CLOUD_MODE", "false").strip().lower() == "true"

import json
import time
import threading
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for
from flask_socketio import SocketIO, emit
from flask_cors import CORS
import whisper
from openai import OpenAI

# Audio-device libraries (PyAudio / PyAudioWPatch) touch real sound hardware
# at initialisation time — skip importing them entirely in CLOUD_MODE so a
# server with no audio devices (or without PyAudio installed at all) still
# boots cleanly. PYAUDIO_AVAILABLE gates every route/handler that would
# otherwise call pyaudio.PyAudio().
PYAUDIO_AVAILABLE = False
pyaudio = None

if CLOUD_MODE:
    print("☁️  CLOUD_MODE enabled — skipping PyAudio (audio-device library) import")
else:
    try:
        import pyaudiowpatch as pyaudio
        PYAUDIO_AVAILABLE = True
    except ImportError:
        try:
            import pyaudio
            PYAUDIO_AVAILABLE = True
        except ImportError as e:
            print(f"⚠️  PyAudio not available: {e}")
            print("   Live microphone/speaker recording will be disabled.")

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

try:
    import yt_dlp
    YTDLP_AVAILABLE = True
    print("✅ yt-dlp available — URL transcription enabled")
except ImportError:
    YTDLP_AVAILABLE = False
    print("⚠️  yt-dlp not installed — URL transcription disabled")

import sys

# ── Dynamic paths — work in both dev and PyInstaller one-folder bundle ─────────
_FROZEN = getattr(sys, 'frozen', False)
if _FROZEN:
    _HERE    = Path(sys._MEIPASS)            # read-only: templates, static, compiled modules
    BASE_DIR = Path(sys.executable).parent   # next to .exe — user-writable
else:
    _HERE    = Path(__file__).parent         # meeting_notes_webapp/
    BASE_DIR = _HERE

ENV_PATH = BASE_DIR / '.env'

# Backend path (only needed in dev; PyInstaller bundles the module automatically)
if not _FROZEN:
    sys.path.insert(0, str(_HERE.parent / 'backend'))

# Speaker diarization (resemblyzer) is only ever used on the live-recording
# path (post-recording diarization of audio_buffer) — never on uploaded
# files, which go through Groq transcription instead. Safe to skip in
# CLOUD_MODE for a lighter boot with no loss of upload functionality.
SPEAKER_DETECTION_AVAILABLE = False
if CLOUD_MODE:
    print("☁️  CLOUD_MODE enabled — skipping speaker-detection (resemblyzer) import")
else:
    try:
        from simple_speaker_detection import SimpleSpeakerDetector
        SPEAKER_DETECTION_AVAILABLE = True
        print("✅ Speaker detection enabled")
    except ImportError as e:
        print(f"⚠️  Speaker detection not available: {e}")

try:
    from transcription_providers import GroqTranscriptionProvider, probe_duration
    TRANSCRIPTION_PROVIDER_AVAILABLE = True
except ImportError as e:
    TRANSCRIPTION_PROVIDER_AVAILABLE = False
    print(f"⚠️  Groq transcription provider not available: {e}")

load_dotenv(dotenv_path=ENV_PATH)

app = Flask(__name__,
            template_folder=str(_HERE / 'templates'),
            static_folder=str(_HERE / 'static'))

# SECRET_KEY is effectively mandatory in cloud deployment: with no env var
# set, each process falls back to its own random key, so signed sessions
# break the moment there's more than one gunicorn worker (or a restart) —
# a request signed by worker A won't validate on worker B. Fine for a
# single-process local run; not fine behind a multi-worker cloud deploy.
_secret_key = os.getenv("SECRET_KEY")
if not _secret_key:
    import secrets as _secrets
    _secret_key = _secrets.token_hex(32)
    print("⚠️  SECRET_KEY not set — using a random key for this process only.")
    print("   Sessions will break across restarts, and across workers if")
    print("   running under multiple gunicorn workers. Set SECRET_KEY in")
    print("   production/cloud deployments.")
app.config['SECRET_KEY'] = _secret_key

app.config['UPLOAD_FOLDER'] = os.getenv("UPLOAD_FOLDER", str(BASE_DIR / 'uploads'))
app.config['NOTES_FOLDER']  = os.getenv("NOTES_FOLDER", str(BASE_DIR / 'notes'))
app.config['MAX_CONTENT_LENGTH'] = int(os.getenv("MAX_UPLOAD_MB", "500")) * 1024 * 1024

Path(app.config['UPLOAD_FOLDER']).mkdir(exist_ok=True)
Path(app.config['NOTES_FOLDER']).mkdir(exist_ok=True)

socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')
CORS(app)


@app.context_processor
def inject_cloud_mode():
    return {'cloud_mode': CLOUD_MODE}


recording_active = False
recording_paused = False
recording_thread = None
audio_stream = None
live_transcript = []
audio_buffer = []   # (chunk_index, timestamp, audio_np) tuples — for post-recording diarization

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
        
        # Local Whisper is only used by live-mic transcription
        # (transcribe_audio(), called from the PyAudio recording thread).
        # File/URL uploads always go through Groq (transcription_provider)
        # regardless of mode, so skipping this load in CLOUD_MODE doesn't
        # affect the upload path — it just avoids loading an unused model.
        if CLOUD_MODE:
            print("☁️  CLOUD_MODE enabled — skipping local Whisper model load (live recording only)")
            self.whisper_model = None
        else:
            try:
                _whisper_size = os.getenv("WHISPER_MODEL", "base")
                self.whisper_model = whisper.load_model(_whisper_size)
                print(f"✅ Whisper model loaded ({_whisper_size})")
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

        if SPEAKER_DETECTION_AVAILABLE:
            self.speaker_detector = SimpleSpeakerDetector()
            print("✅ Speaker detector initialised")
        else:
            self.speaker_detector = None

        self.transcription_provider = None
        if TRANSCRIPTION_PROVIDER_AVAILABLE:
            try:
                self.transcription_provider = GroqTranscriptionProvider()
                print("✅ Groq file-transcription provider initialised")
            except Exception as e:
                print(f"❌ Groq transcription provider setup error: {e}")

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

        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key:
            try:
                self.providers['openai'] = OpenAI(api_key=openai_key)
                print("✅ OpenAI API configured")
            except Exception as e:
                print(f"❌ OpenAI setup error: {e}")

        deepseek_key = os.getenv("DEEPSEEK_API_KEY")
        if deepseek_key:
            try:
                self.providers['deepseek'] = OpenAI(
                    api_key=deepseek_key,
                    base_url="https://api.deepseek.com/v1"
                )
                print("✅ DeepSeek API configured")
            except Exception as e:
                print(f"❌ DeepSeek setup error: {e}")

        print(f"✅ Available AI providers: {list(self.providers.keys())}")
    
    def is_gibberish(self, text: str) -> bool:
        """Return True if *text* looks like a Whisper hallucination or noise artefact."""
        import re

        # 0. Heavy-repetition check — catches word loops.
        words = text.split()
        if len(words) > 8:
            unique_ratio = len(set(words)) / len(words)
            if unique_ratio < 0.20:
                print(f"⚠️  Gibberish (word loop, unique ratio {unique_ratio:.0%}): '{text[:60]}'")
                return True

        # 1. Non-ASCII ratio
        non_ascii = sum(1 for c in text if ord(c) > 127)
        if len(text) > 0 and non_ascii / len(text) > 0.15:
            print(f"⚠️  Gibberish (non-ASCII ratio {non_ascii/len(text):.0%}): '{text}'")
            return True

        # 2. Real-word ratio
        tokens = words  # already split above
        if tokens:
            real_words = sum(1 for t in tokens if re.search(r'[a-zA-Z]', t))
            if real_words / len(tokens) < 0.5:
                print(f"⚠️  Gibberish (real-word ratio {real_words/len(tokens):.0%}): '{text}'")
                return True

        # 3. Repetition — unique-word ratio below 30 % for longer utterances
        if len(tokens) >= 6:
            unique_ratio = len(set(t.lower() for t in tokens)) / len(tokens)
            if unique_ratio < 0.30:
                print(f"⚠️  Gibberish (repetition, unique ratio {unique_ratio:.0%}): '{text}'")
                return True

        # 4. Known Whisper hallucination phrases (mostly English — always apply)
        HALLUCINATION_PHRASES = [
            "thank you for watching",
            "thanks for watching",
            "please subscribe",
            "like and subscribe",
            "don't forget to subscribe",
            "subtitles by",
            "transcribed by",
            "www.",
            ".com",
            "♪",
            "[ music ]",
            "[music]",
            "[applause]",
            "[ applause ]",
        ]
        lower = text.lower()
        for phrase in HALLUCINATION_PHRASES:
            if phrase in lower:
                print(f"⚠️  Gibberish (hallucination phrase '{phrase}'): '{text}'")
                return True

        # 5. Alpha-character ratio — .isalpha() is Unicode-aware so it works for
        #    Devanagari, Arabic, CJK, Cyrillic etc.  Apply to all languages.
        alpha = sum(1 for c in text if c.isalpha())
        if len(text) > 0 and alpha / len(text) < 0.40:
            print(f"⚠️  Gibberish (alpha ratio {alpha/len(text):.0%}): '{text}'")
            return True

        return False

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
            result = self.whisper_model.transcribe(
                processed_audio,
                language='en',
                temperature=0.0,
                condition_on_previous_text=False,
            )
            text = result["text"].strip()

            print(f"📝 Whisper output: '{text}' (length: {len(text)})")

            # Filter short false positives
            if len(text) < 3:
                print(f"⚠️  Text too short: '{text}'")
                return ""

            # Filter gibberish / hallucinations
            if self.is_gibberish(text):
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
        word_count = len(text.split())

        # Scale settings based on transcript length
        if word_count < 100:
            scale = "short"
            max_tokens = 300
            char_limit = 1000
        elif word_count < 400:
            scale = "medium"
            max_tokens = 600
            char_limit = 2500
        elif word_count < 1000:
            scale = "standard"
            max_tokens = 900
            char_limit = 5000
        else:
            scale = "long"
            max_tokens = 1400
            char_limit = 10000

        print(f"📊 Smart summary: {word_count} words → scale={scale}, max_tokens={max_tokens}")

        if scale == "short":
            prompt = f"""Short conversation snippet ({word_count} words). Be concise.

    {text[:char_limit]}

    Return JSON:
    {{
    "summary": "1-2 sentence summary",
    "actions": ["action item if any"],
    "decisions": ["decision if any"],
    "key_points": ["main point"]
    }}"""

        elif scale == "medium":
            prompt = f"""Short meeting transcript ({word_count} words).

    {text[:char_limit]}

    Return JSON:
    {{
    "summary": "2-3 sentence summary of the main discussion",
    "actions": ["action items with owner if mentioned"],
    "decisions": ["decisions made"],
    "key_points": ["2-4 key points discussed"],
    "topics": ["main topics covered"]
    }}"""

        elif scale == "standard":
            prompt = f"""Meeting transcript ({word_count} words). Be thorough.

    {text[:char_limit]}

    Return JSON:
    {{
    "summary": "3-5 sentence executive summary of what was discussed and concluded",
    "actions": ["action items with owner and deadline if mentioned"],
    "decisions": ["all decisions made"],
    "key_points": ["5-7 important points"],
    "topics": ["all main topics covered"],
    "questions_raised": ["open questions that came up"],
    "next_steps": ["follow-up items"]
    }}"""

        else:
            prompt = f"""Long meeting transcript ({word_count} words). Be comprehensive.

    {text[:char_limit]}

    Return JSON:
    {{
    "summary": "4-6 sentence executive summary covering all major themes and outcomes",
    "actions": ["detailed action items with owner, deadline, and priority"],
    "decisions": ["all decisions made with context"],
    "key_points": ["8-12 important points spanning the full discussion"],
    "topics": ["all topics and subtopics covered"],
    "questions_raised": ["open questions and unresolved issues"],
    "next_steps": ["concrete follow-up items"],
    "insights": ["notable insights or risks mentioned"],
    "participants_mentioned": ["names of people mentioned"]
    }}"""

        client = self.providers[provider]

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": f"You are an expert meeting analyst. This is a {scale} transcript. Return ONLY valid JSON, no markdown, no extra text."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=max_tokens,
            temperature=0.2,
            response_format={"type": "json_object"}
        )

        content = response.choices[0].message.content

        try:
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            content = (content
                       .replace('“', '"').replace('”', '"')
                       .replace('‘', "'").replace('’', "'"))

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

    def analyze_upload_with_ai(self, transcript, provider, duration_seconds=None):
        """
        Smart summarization for uploaded files.
        Uses actual duration + map-reduce for long content.
        """
        if not transcript or len(transcript.strip()) < 20:
            return self.simple_analysis(transcript)

        if provider not in self.providers:
            if self.providers:
                provider = list(self.providers.keys())[0]
            else:
                return self.simple_analysis(transcript)

        word_count = len(transcript.split())
        duration_min = round(duration_seconds / 60, 1) if duration_seconds else None

        # Scale by whichever signal implies richer content — a short, dense
        # recording (e.g. a fast-paced lecture) should get the same depth as
        # a longer sparse one with the same word count. Using duration alone
        # was bucketing dense short clips into shallow tiers.
        if duration_seconds:
            if duration_seconds < 180:        # under 3 min
                duration_scale = "short"
            elif duration_seconds < 900:      # 3-15 min
                duration_scale = "medium"
            elif duration_seconds < 2700:     # 15-45 min
                duration_scale = "standard"
            else:                             # 45+ min
                duration_scale = "long"
        else:
            duration_scale = None

        if word_count < 100:
            word_scale = "short"
        elif word_count < 400:
            word_scale = "medium"
        elif word_count < 1000:
            word_scale = "standard"
        else:
            word_scale = "long"

        _scale_rank = {"short": 0, "medium": 1, "standard": 2, "long": 3}
        scale = max(
            [s for s in (duration_scale, word_scale) if s],
            key=lambda s: _scale_rank[s]
        )

        print(f"📊 Upload summary: {word_count} words, {duration_min}min → scale={scale}")

        # For long content use map-reduce: summarize chunks then combine
        if scale == "long" and word_count > 2000:
            return self.map_reduce_summarize(transcript, provider, duration_min)

        # For short/medium/standard use single prompt with duration context
        duration_context = f"Duration: {duration_min} minutes. " if duration_min else ""

        context_instructions = (
            "First, work out from the content what this recording actually is — "
            "a business meeting, a lecture/lesson, a talk or presentation, an "
            "interview, or something else — and tailor your response to that. "
            "For lecture/talk/educational content: focus the summary and key "
            "points on the concepts, arguments, and information conveyed, "
            "written so someone who never watched it can understand what the "
            "speaker was teaching or explaining. Leave 'actions' and "
            "'decisions' empty for non-meeting content — don't force them."
        )

        if scale == "short":
            max_tokens = 400
            prompt = f"""{duration_context}Transcript ({word_count} words):

{transcript[:2500]}

{context_instructions}

Return JSON:
{{
  "summary": "2-3 sentences covering what this is about and its main point",
  "actions": ["action if any, else leave empty"],
  "decisions": ["decision if any, else leave empty"],
  "key_points": ["1-3 substantive points, each a full explanatory sentence"]
}}"""

        elif scale == "medium":
            max_tokens = 900
            prompt = f"""{duration_context}Transcript ({word_count} words):

{transcript[:7000]}

{context_instructions}

Return JSON:
{{
  "summary": "3-5 sentences explaining what was discussed or taught and why it matters",
  "actions": ["action items with owner if mentioned, else leave empty"],
  "decisions": ["decisions made, else leave empty"],
  "key_points": ["4-7 substantive points — each a full sentence explaining a specific concept, fact, or discussion point in enough detail to stand alone"],
  "topics": ["main topics/subjects covered"]
}}"""

        else:  # standard
            max_tokens = 1600
            prompt = f"""{duration_context}Transcript ({word_count} words):

{transcript[:16000]}

{context_instructions}

Return JSON:
{{
  "summary": "5-8 sentence in-depth overview: what this covers, the structure/flow of the content, and why it matters",
  "actions": ["action items with owner and deadline if mentioned, else leave empty"],
  "decisions": ["all decisions made, else leave empty"],
  "key_points": ["7-12 substantive points — each a full sentence explaining a specific concept, argument, or fact in enough detail that someone who didn't watch this could understand what the speaker covered"],
  "topics": ["all main topics/subjects covered"],
  "questions_raised": ["open questions raised"],
  "next_steps": ["follow-up items or what comes next, if any"]
}}"""

        try:
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    self._call_ai,
                    prompt,
                    provider,
                    max_tokens,
                    f"Expert analyst who adapts to the type of content — meeting, lecture, talk, or interview. {duration_context}Return ONLY valid JSON."
                )
                result = future.result(timeout=60)
                return result
        except Exception as e:
            print(f"❌ Upload AI error: {e}")
            return self.simple_analysis(transcript)

    def map_reduce_summarize(self, transcript, provider, duration_min=None):
        """
        For long transcripts: summarize in chunks then combine.
        Prevents cutting off the last 80% of a long meeting.
        """
        print(f"🗺️  Using map-reduce for long transcript...")
        map_reduce_start = time.time()

        # Split transcript into chunks of ~1500 words each
        words = transcript.split()
        chunk_size = 1500
        chunks = []
        for i in range(0, len(words), chunk_size):
            chunk = ' '.join(words[i:i + chunk_size])
            chunks.append(chunk)

        print(f"   Split into {len(chunks)} chunks")

        # MAP phase: summarize each chunk
        chunk_summaries = []
        for i, chunk in enumerate(chunks):
            print(f"   Summarizing chunk {i+1}/{len(chunks)}...")
            chunk_prompt = f"""Summarize this section of a transcript (part {i+1} of {len(chunks)}).
This could be a meeting, a lecture/lesson, a talk, or an interview — judge
from the content and adapt. For lecture/educational content, focus on the
concepts and information explained rather than forcing meeting-style fields.

{chunk}

Return JSON:
{{
  "summary": "2-4 sentences on what this section covers",
  "actions": ["action items in this section, else leave empty"],
  "decisions": ["decisions in this section, else leave empty"],
  "key_points": ["3-6 substantive points — each a full sentence explaining a specific concept, fact, or discussion point from this section"]
}}"""

            chunk_start = time.time()
            try:
                result = self._call_ai(chunk_prompt, provider, 600,
                                       "Summarize transcript sections, adapting to whether the content is a meeting, lecture, talk, or interview. Return ONLY valid JSON.")
                if result and result.get('summary'):
                    chunk_summaries.append(result)
                print(f"   ...chunk {i+1} done in {time.time() - chunk_start:.1f}s")
            except Exception as e:
                print(f"   ⚠️ Chunk {i+1} failed after {time.time() - chunk_start:.1f}s: {e}")
                continue
            # No artificial delay between chunks — Groq's rate limits comfortably
            # cover this volume; if 429s start showing up here, reintroduce a
            # short backoff instead of a flat sleep on every chunk.

        if not chunk_summaries:
            return self.simple_analysis(transcript)

        # REDUCE phase: combine all chunk summaries into final summary
        print(f"   Combining {len(chunk_summaries)} chunk summaries...")

        all_summaries = "\n\n".join([
            f"Section {i+1}: {s.get('summary', '')}"
            for i, s in enumerate(chunk_summaries)
        ])

        all_actions = []
        all_decisions = []
        all_key_points = []
        for s in chunk_summaries:
            all_actions.extend(s.get('actions', []))
            all_decisions.extend(s.get('decisions', []))
            all_key_points.extend(s.get('key_points', []))

        duration_context = f"Total duration: {duration_min} minutes." if duration_min else ""

        reduce_prompt = f"""{duration_context}
This is a long recording broken into {len(chunks)} sections — it could be a
meeting, a lecture/lesson, a talk, or an interview. Here are summaries of
each section:

{all_summaries}

Combine these into a final comprehensive report, adapted to what this
content actually is. For lecture/educational content, the summary and key
points should let someone who never watched it understand what the speaker
taught or discussed — don't force meeting-style fields onto it.

Return JSON:
{{
  "summary": "6-10 sentence in-depth overview covering the full arc of the content and why it matters",
  "actions": {json.dumps(list(dict.fromkeys(all_actions)))},
  "decisions": {json.dumps(list(dict.fromkeys(all_decisions)))},
  "key_points": ["10-15 most important points from the whole recording — each a full sentence explaining a specific concept, argument, or fact in enough detail to stand alone"],
  "topics": ["all major topics/subjects covered across all sections"],
  "questions_raised": ["open questions from any section"],
  "next_steps": ["all follow-up items, if any"],
  "insights": ["notable patterns, themes, or insights across the whole recording"]
}}"""

        try:
            reduce_start = time.time()
            final = self._call_ai(reduce_prompt, provider, 2200,
                                  "Expert analyst combining section summaries, adapting to whether the content is a meeting, lecture, talk, or interview. Return ONLY valid JSON.")
            print(f"   ...reduce phase done in {time.time() - reduce_start:.1f}s")
            print(f"🗺️  Map-reduce total: {time.time() - map_reduce_start:.1f}s")
            return final if final else self._stitched_chunk_fallback(chunk_summaries, all_actions, all_decisions, all_key_points)
        except Exception as e:
            print(f"❌ Reduce phase error: {e}")
            # The merge step failed, but the per-chunk summaries above already
            # succeeded — stitch those together instead of dropping back to
            # simple_analysis(transcript), which only grabs 1-2 raw sentences
            # and throws away all the map-phase work.
            return self._stitched_chunk_fallback(chunk_summaries, all_actions, all_decisions, all_key_points)

    def _stitched_chunk_fallback(self, chunk_summaries, all_actions, all_decisions, all_key_points):
        """Best-effort combined result built from already-succeeded chunk
        summaries, used when the reduce (merge) call itself fails."""
        summary = ' '.join(s.get('summary', '') for s in chunk_summaries if s.get('summary'))
        return {
            "summary": summary,
            "actions": list(dict.fromkeys(all_actions)),
            "decisions": list(dict.fromkeys(all_decisions)),
            "key_points": list(dict.fromkeys(all_key_points)),
        }

    def _call_ai(self, prompt, provider, max_tokens, system_prompt):
        """Reusable AI call with JSON parsing.

        Raises on failure instead of degrading silently — callers already
        catch exceptions and fall back to simple_analysis(transcript), which
        uses the real transcript. Returning simple_analysis(content) from
        here used to fall back on the model's raw (sometimes truncated,
        invalid-JSON) completion text instead, which could surface as a
        garbled fragment mislabeled as a "summary".
        """
        client = self.providers[provider]

        def _request(tokens):
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=tokens,
                temperature=0.2,
                response_format={"type": "json_object"}
            )
            return response.choices[0]

        choice = _request(max_tokens)

        # If the model ran out of budget mid-response, retry once with more
        # room rather than parsing (and failing on) a truncated payload.
        if choice.finish_reason == "length":
            print(f"⚠️  AI response truncated at {max_tokens} tokens — retrying with more room")
            choice = _request(min(max_tokens * 2, 4096))

        content = choice.message.content

        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        # Defensive normalization — models occasionally emit "smart" quotes
        # (curly “ ” / ‘ ’) inside otherwise-valid JSON, which breaks strict
        # parsing. response_format=json_object should prevent this, but keep
        # the fallback in case a provider ignores that flag.
        content = (content
                   .replace('“', '"').replace('”', '"')
                   .replace('‘', "'").replace('’', "'"))

        return json.loads(content)

    def process_file(self, filepath, options):
        import re
        try:
            if not self.transcription_provider:
                raise RuntimeError(
                    "Groq transcription provider is not available (check GROQ_API_KEY)"
                )

            duration_seconds = probe_duration(filepath)
            if duration_seconds:
                print(f"⏱️  Detected duration: {duration_seconds:.1f}s ({duration_seconds/60:.1f}min)")

            transcribe_start = time.time()
            raw_transcript = self.transcription_provider.transcribe_file(filepath, language='en')
            print(f"⏱️  Transcription took {time.time() - transcribe_start:.1f}s "
                  f"({len(raw_transcript.split())} words)")

            # --- sentence-level gibberish filter + deduplication ---
            # NOTE: checks 1-2 in is_gibberish() (non-ASCII ratio, real-word
            # ratio) were tuned around local Whisper's noisier hallucinations;
            # they may end up firing less often on Groq's cleaner output. Left
            # as-is for now — not removing anything without evidence.
            sentences = re.split(r'(?<=[.!?])\s+', raw_transcript.strip())
            seen = set()
            clean_sentences = []
            for sentence in sentences:
                sentence = sentence.strip()
                if not sentence:
                    continue
                if self.is_gibberish(sentence):
                    print(f"⚠️  Filtered gibberish sentence from file: '{sentence}'")
                    continue
                key = sentence.lower()
                if key in seen:
                    print(f"⚠️  Duplicate sentence removed: '{sentence}'")
                    continue
                seen.add(key)
                clean_sentences.append(sentence)

            transcript = ' '.join(clean_sentences)
            # --------------------------------------------------------

            analysis = {"summary": "", "actions": [], "decisions": [], "key_points": []}

            if options.get('generateSummary', True):
                provider = options.get('model', 'groq')
                summary_start = time.time()
                analysis = self.analyze_upload_with_ai(transcript, provider, duration_seconds)
                print(f"⏱️  Summary generation took {time.time() - summary_start:.1f}s")

            return {
                "transcript": transcript,
                "summary": analysis.get("summary", ""),
                "actions": analysis.get("actions", []),
                "decisions": analysis.get("decisions", []),
                "key_points": analysis.get("key_points", []),
                "topics": analysis.get("topics", []),
                "questions_raised": analysis.get("questions_raised", []),
                "next_steps": analysis.get("next_steps", []),
                "duration_seconds": duration_seconds
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


# ── First-Run Setup ────────────────────────────────────────────────────────────

def is_setup_complete():
    """Return True if any supported AI provider key is present."""
    for var in ('GROQ_API_KEY', 'OPENAI_API_KEY', 'DEEPSEEK_API_KEY'):
        key = os.environ.get(var, '').strip()
        if key and not key.startswith('your-'):
            return True
    return False


@app.before_request
def check_setup():
    """Redirect to /setup when no API key is configured."""
    allowed_endpoints = {'setup', 'setup_save', 'static'}
    if request.endpoint in allowed_endpoints:
        return None
    if not is_setup_complete():
        return redirect(url_for('setup'))
    return None


_PROVIDER_KEY_VAR = {
    'groq':     'GROQ_API_KEY',
    'openai':   'OPENAI_API_KEY',
    'deepseek': 'DEEPSEEK_API_KEY',
}
_PROVIDER_BASE_URL = {
    'groq':     'https://api.groq.com/openai/v1',
    'openai':   None,
    'deepseek': 'https://api.deepseek.com/v1',
}
_PROVIDER_DEFAULT_MODEL = {
    'groq':     'llama-3.3-70b-versatile',
    'openai':   'gpt-4o-mini',
    'deepseek': 'deepseek-chat',
}


def _current_provider():
    return os.environ.get('AI_PROVIDER', 'groq')


def _masked_key():
    provider = _current_provider()
    key = os.environ.get(_PROVIDER_KEY_VAR.get(provider, 'GROQ_API_KEY'), '')
    if len(key) > 12:
        return key[:8] + '****' + key[-4:]
    return '(not set)' if not key else '****'


@app.route('/api/validate-key', methods=['POST'])
def validate_key():
    """Test an API key against the chosen provider without saving it."""
    data     = request.get_json(silent=True) or {}
    api_key  = data.get('api_key', '').strip()
    provider = data.get('provider', 'groq')

    if provider not in _PROVIDER_KEY_VAR:
        return jsonify({'valid': False, 'error': 'Unknown provider.'})
    if not api_key:
        return jsonify({'valid': False, 'error': 'API key is required.'})

    try:
        kwargs = {'api_key': api_key}
        base   = _PROVIDER_BASE_URL.get(provider)
        if base:
            kwargs['base_url'] = base
        client = OpenAI(**kwargs)
        client.models.list()          # lightweight — just verifies auth
        return jsonify({'valid': True})
    except Exception as exc:
        msg = str(exc)
        if any(t in msg.lower() for t in ('401', 'invalid_api_key', 'authentication', 'unauthorized', 'incorrect')):
            return jsonify({'valid': False, 'error': 'Invalid API key — please check and try again.'})
        return jsonify({'valid': False, 'error': f'Connection error: {msg[:140]}'})


@app.route('/setup', methods=['GET'])
def setup():
    provider = _current_provider()
    return render_template('setup.html',
                           already_configured=is_setup_complete(),
                           api_key_masked=_masked_key(),
                           whisper_model=os.environ.get('WHISPER_MODEL', 'base'),
                           ai_provider=provider,
                           error=None)


@app.route('/setup', methods=['POST'])
def setup_save():
    api_key    = request.form.get('api_key', '').strip()
    model_size = request.form.get('whisper_model', 'base')
    provider   = request.form.get('ai_provider', 'groq')

    if provider not in _PROVIDER_KEY_VAR:
        provider = 'groq'

    if not api_key:
        return render_template('setup.html',
                               already_configured=is_setup_complete(),
                               api_key_masked=_masked_key(),
                               whisper_model=model_size,
                               ai_provider=provider,
                               error='API key is required.')

    key_var  = _PROVIDER_KEY_VAR[provider]
    ai_model = _PROVIDER_DEFAULT_MODEL[provider]

    env_content = (
        f"{key_var}={api_key}\n"
        f"AI_PROVIDER={provider}\n"
        f"AI_MODEL={ai_model}\n"
        f"WHISPER_MODEL={model_size}\n"
    )
    ENV_PATH.write_text(env_content, encoding='utf-8')

    load_dotenv(dotenv_path=ENV_PATH, override=True)
    os.environ[key_var]          = api_key
    os.environ['WHISPER_MODEL']  = model_size
    os.environ['AI_PROVIDER']    = provider
    os.environ['AI_MODEL']       = ai_model

    assistant.setup_ai_providers()
    return redirect('/')


@app.route('/api/settings')
def get_settings():
    provider = _current_provider()
    return jsonify({
        'api_key_masked': _masked_key(),
        'whisper_model':  os.environ.get('WHISPER_MODEL', 'base'),
        'ai_model':       os.environ.get('AI_MODEL', _PROVIDER_DEFAULT_MODEL.get(provider, '')),
        'ai_provider':    provider,
    })


# Routes
@app.route('/health')
def health():
    """Unauthenticated liveness/readiness probe for hosting platforms."""
    return jsonify({
        'status': 'ok',
        'cloud_mode': CLOUD_MODE,
        'groq_configured': bool(os.getenv('GROQ_API_KEY')),
    })

@app.route('/')
def home():
    return render_template('home.html')

@app.route('/meeting')
def meeting():
    return render_template('meeting.html')

@app.route('/notes/<note_id>')
def note_detail_page(note_id):
    """Standalone page for a single note — opened in its own tab from My Notes."""
    note_id = secure_filename(note_id)
    note_file = Path(app.config['NOTES_FOLDER']) / f"{note_id}.json"
    found = note_file.exists()
    return render_template('note_detail.html', note_id=note_id, not_found=not found), (200 if found else 404)

@app.route('/api/devices')
def get_devices():
    if CLOUD_MODE or not PYAUDIO_AVAILABLE:
        return jsonify([])
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
    if CLOUD_MODE or not PYAUDIO_AVAILABLE:
        return jsonify({
            "success": False,
            "message": "Audio device detection is not available in cloud mode."
        })
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
        unique_name = f"{uuid.uuid4().hex}_{filename}"
        filepath = Path(app.config['UPLOAD_FOLDER']) / unique_name
        file.save(filepath)

        try:
            options = {
                'generateSummary': request.form.get('generateSummary') == 'true',
                'model': request.form.get('model', 'groq')
            }

            result = assistant.process_file(str(filepath), options)

            notes_data = {
                "title": filename,
                "timestamp": datetime.now().isoformat(),
                "source": "upload",
                "duration": f"{round(result.get('duration_seconds', 0) / 60, 1)} min"
                            if result.get('duration_seconds') else "N/A",
                **result
            }

            notes_file = assistant.save_notes(notes_data, "upload")

            return jsonify({
                **result,
                "notes_file": notes_file
            })
        finally:
            # Cloud deployments don't retain uploaded audio — the transcript/
            # note is already saved by this point, so a stuck file here isn't
            # worth failing the request over.
            try:
                filepath.unlink(missing_ok=True)
            except Exception as e:
                print(f"⚠️  Failed to delete uploaded file {filepath}: {e}")
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/api/notes/<note_id>/chat', methods=['POST'])
def chat_with_note(note_id):
    try:
        note_file = Path(app.config['NOTES_FOLDER']) / f"{note_id}.json"
        if not note_file.exists():
            return jsonify({"error": "Note not found"}), 404

        with open(note_file, 'r', encoding='utf-8') as f:
            note_data = json.load(f)

        transcript = note_data.get('transcript', '')
        if not transcript or len(transcript.strip()) < 20:
            return jsonify({"error": "This note has no transcript to chat with"}), 400

        data = request.json
        question = data.get('question', '').strip()
        chat_history = data.get('history', [])

        if not question:
            return jsonify({"error": "No question provided"}), 400

        messages = [
            {
                "role": "system",
                "content": f"""You are a helpful meeting assistant.
Answer questions based ONLY on the meeting transcript provided.
If the answer is not in the transcript, say "I couldn't find that in this meeting's transcript."
Be concise and direct. Use bullet points for lists.

MEETING TRANSCRIPT:
{transcript[:8000]}

MEETING SUMMARY (for context):
{note_data.get('summary', 'No summary available')}"""
            }
        ]

        for msg in chat_history[-6:]:
            messages.append({
                "role": msg['role'],
                "content": msg['content']
            })

        messages.append({
            "role": "user",
            "content": question
        })

        provider = 'groq'
        if provider not in assistant.providers:
            if assistant.providers:
                provider = list(assistant.providers.keys())[0]
            else:
                return jsonify({"error": "No AI provider available"}), 500

        client = assistant.providers[provider]

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            max_tokens=500,
            temperature=0.3
        )

        answer = response.choices[0].message.content

        return jsonify({
            "answer": answer,
            "question": question
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route('/api/process-url', methods=['POST'])
def process_url():
    try:
        if not YTDLP_AVAILABLE:
            return jsonify({"error": "yt-dlp is not installed on this server"}), 501

        data = request.json
        url = data.get('url', '').strip()

        if not url:
            return jsonify({"error": "No URL provided"}), 400

        if not url.startswith(('http://', 'https://')):
            return jsonify({"error": "Invalid URL — must start with http:// or https://"}), 400

        upload_dir = Path(app.config['UPLOAD_FOLDER'])
        output_template = str(upload_dir / f'{uuid.uuid4().hex}_%(title)s.%(ext)s')

        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': output_template,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'quiet': True,
            'no_warnings': True,
        }

        print(f"📥 Downloading audio from: {url}")

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            video_title = info.get('title', 'Unknown Title')
            duration = info.get('duration', 0)

            # yt-dlp changes the extension after postprocessing
            filename = ydl.prepare_filename(info)
            audio_path = Path(filename).with_suffix('.mp3')

        if not audio_path.exists():
            return jsonify({"error": "Audio download failed — file not found after conversion"}), 500

        print(f"✅ Downloaded: {video_title} ({duration}s)")

        socketio.emit('url_processing_status', {
            'status': 'transcribing',
            'message': f'Transcribing: {video_title}...'
        })

        try:
            options = {
                'generateSummary': data.get('generateSummary', True),
                'model': data.get('model', 'groq')
            }

            result = assistant.process_file(str(audio_path), options)

            notes_data = {
                "title": video_title,
                "timestamp": datetime.now().isoformat(),
                "source": "url",
                "url": url,
                "duration": duration,
                **result
            }

            notes_file = assistant.save_notes(notes_data, "url")

            return jsonify({
                **result,
                "title": video_title,
                "duration": duration,
                "notes_file": notes_file
            })
        finally:
            # Cloud deployments don't retain downloaded audio — the transcript/
            # note is already saved by this point, so a stuck file here isn't
            # worth failing the request over.
            try:
                audio_path.unlink(missing_ok=True)
            except Exception as e:
                print(f"⚠️  Failed to delete downloaded audio {audio_path}: {e}")

    except yt_dlp.utils.DownloadError as e:
        error_msg = str(e)
        if 'Private video' in error_msg:
            return jsonify({"error": "This video is private"}), 400
        elif 'not available' in error_msg:
            return jsonify({"error": "Video not available in your region"}), 400
        else:
            return jsonify({"error": f"Download failed: {error_msg[:200]}"}), 500
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

        full_text = " ".join([
            f"{entry.get('speaker', 'Speaker 1')}: {entry['text']}"
            for entry in live_transcript
        ])

        if len(full_text) < 20:
            return jsonify({"error": "Transcript too short"}), 400

        provider = request.json.get('provider', 'groq') if request.json else 'groq'
        analysis = assistant.analyze_with_ai(full_text, provider, timeout=45)

        notes_data = {
            "title": f"Live Meeting {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "timestamp": datetime.now().isoformat(),
            "source": "live",
            "transcript": "\n".join([
                f"[{e['timestamp']}] {e.get('speaker', 'Speaker 1')}: {e['text']}"
                for e in live_transcript
            ]),
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
            'topics': data.get('topics', []),
            'questions_raised': data.get('questions_raised', []),
            'next_steps': data.get('next_steps', []),
            'insights': data.get('insights', []),
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
    global recording_active, recording_paused, recording_thread, live_transcript, audio_buffer

    if CLOUD_MODE or not PYAUDIO_AVAILABLE:
        emit('error', {'message': 'Live recording is not available in cloud mode'})
        return

    if recording_active:
        emit('error', {'message': 'Recording already in progress'})
        return

    recording_active = True
    recording_paused = False
    live_transcript = []
    audio_buffer = []

    if assistant.speaker_detector:
        assistant.speaker_detector.reset()
        print("🔄 Speaker detector reset for new meeting")

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
    global recording_active, recording_thread
    recording_active = False
    emit('recording_status', {'status': 'Recording stopped'})
    emit('speaker_detection_start', {'message': 'Analyzing speakers... please wait'})

    # Run diarization in a background thread so the UI stays responsive.
    # We wait for the recording thread to fully drain its last chunk first.
    def diarize_after_stop():
        if recording_thread and recording_thread.is_alive():
            recording_thread.join(timeout=15)
        run_speaker_diarization()

    diarization_thread = threading.Thread(target=diarize_after_stop)
    diarization_thread.daemon = True
    diarization_thread.start()

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
    global recording_active, recording_paused, audio_stream, live_transcript, audio_buffer

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

            # Store raw audio for post-recording diarization
            audio_buffer.append({
                'timestamp': datetime.now().strftime("%H:%M:%S"),
                'chunk_index': chunk_count,
                'audio': audio_np.copy(),
            })

            transcript = assistant.transcribe_audio(audio_np)

            if transcript:
                timestamp = datetime.now().strftime("%H:%M:%S")
                speaker = "Analyzing..."   # will be updated after diarization

                live_transcript.append({
                    'timestamp': timestamp,
                    'text': transcript,
                    'speaker': speaker,
                    'chunk_index': chunk_count,
                })

                print(f"🎯 Emitting transcript update: [{timestamp}] {transcript}")

                socketio.emit('transcript_update', {
                    'timestamp': timestamp,
                    'text': transcript,
                    'speaker': speaker,
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

def run_speaker_diarization():
    """Process full audio buffer after recording to assign speaker labels."""
    global audio_buffer, live_transcript

    # Emit recording_complete so the Generate Summary button always appears
    def finish():
        socketio.emit('recording_complete', {'message': 'Click "Generate Summary" to analyze'})

    if not audio_buffer or not SPEAKER_DETECTION_AVAILABLE:
        print("ℹ️  Skipping diarization (no audio or resemblyzer unavailable)")
        finish()
        return

    try:
        print("🔍 Running post-recording speaker diarization...")

        # Fresh detector for each diarization pass
        detector = SimpleSpeakerDetector()

        # Map chunk_index → detected speaker
        chunk_speakers = {}
        for chunk_data in audio_buffer:
            chunk_idx = chunk_data['chunk_index']
            audio = chunk_data['audio']

            if np.sqrt(np.mean(audio ** 2)) > 0.01:
                speaker = detector.detect_speaker(audio)
            else:
                speaker = detector.last_speaker  # carry forward last known speaker

            chunk_speakers[chunk_idx] = speaker
            print(f"  Chunk {chunk_idx}: {speaker}")

        # Patch live_transcript entries with the detected speaker labels
        for entry in live_transcript:
            chunk_idx = entry.get('chunk_index', 1)
            entry['speaker'] = chunk_speakers.get(chunk_idx, 'Speaker 1')

        print(f"✅ Speaker diarization complete — {len(chunk_speakers)} chunks processed")

        socketio.emit('speaker_detection_complete', {
            'transcript': live_transcript
        })

    except Exception as e:
        print(f"❌ Speaker diarization error: {e}")
        import traceback
        traceback.print_exc()

    finally:
        finish()


if __name__ == '__main__':
    _host = os.getenv("HOST", "0.0.0.0")
    _port = int(os.getenv("PORT", "5000"))
    # Fails safe: Flask's debug mode exposes the Werkzeug interactive
    # debugger, which lets anyone who can reach a stack trace run arbitrary
    # code. Default OFF; set FLASK_DEBUG=true for local desktop development.
    _debug = os.getenv("FLASK_DEBUG", "false").strip().lower() == "true"

    print("\n" + "="*50)
    print("   Smart Meeting Notes")
    if VAD_AVAILABLE:
        print("   🔇 Noise Suppression: ENABLED")
    else:
        print("   🔇 Noise Suppression: DISABLED (basic mode)")
    print(f"   Running on http://{_host}:{_port}")
    print("="*50 + "\n")

    socketio.run(app, debug=_debug, host=_host, port=_port)