import whisper
from config import Config

class Transcriber:
    def __init__(self):
        self.config = Config()
        self.model = None

        try:
            print(f"🔄 Loading Whisper model ({self.config.WHISPER_MODEL})...")
            # Load Whisper model
            self.model = whisper.load_model(self.config.WHISPER_MODEL)
            print("✅ Model loaded")
        except Exception as e:
            print(f"❌ Failed to load Whisper model: {e}")
            print("Please ensure the model is installed correctly.")
            raise
        
    def transcribe_audio(self, audio_data):
        """Transcribe audio data"""
        if audio_data is None or len(audio_data) == 0:
            return ""
            
        try:
            # Transcribe with Whisper
            result = self.model.transcribe(
                audio_data,
                fp16=False,  # Use FP32 for CPU
                language='en'
            )
            
            return result['text'].strip()
            
        except Exception as e:
            print(f"Transcription error: {e}")
            return ""
            
    def transcribe_file(self, filename):
        """Transcribe audio file"""
        result = self.model.transcribe(filename)
        return result['text']