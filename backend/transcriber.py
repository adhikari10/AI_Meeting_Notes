import whisper
import numpy as np
from openai import OpenAI
from config import Config

class Transcriber:
    def __init__(self):
        self.config = Config()
        self.model = None
        self.groq_client = None

        # Confidence threshold — segments below this get sent for correction
        self.CONFIDENCE_THRESHOLD = -0.8  # Whisper uses log probabilities (0 = perfect, -1 = uncertain)

        try:
            print(f"🔄 Loading Whisper model ({self.config.WHISPER_MODEL})...")
            self.model = whisper.load_model(self.config.WHISPER_MODEL)
            print("✅ Whisper model loaded")
        except Exception as e:
            print(f"❌ Failed to load Whisper model: {e}")
            raise

        # Setup Groq for correction
        try:
            if self.config.GROQ_API_KEY:
                self.groq_client = OpenAI(
                    api_key=self.config.GROQ_API_KEY,
                    base_url="https://api.groq.com/openai/v1"
                )
                print("✅ Groq correction layer ready")
            else:
                print("⚠️  No Groq key — correction layer disabled")
        except Exception as e:
            print(f"⚠️  Groq setup failed: {e}")

    # ─────────────────────────────────────────────
    # MAIN METHOD — called during live capture
    # ─────────────────────────────────────────────
    def transcribe_audio(self, audio_data):
        """Transcribe audio with confidence scoring and auto-correction"""
        if audio_data is None or len(audio_data) == 0:
            return ""

        try:
            # Get full result including segment-level data
            result = self.model.transcribe(
                audio_data,
                fp16=False,
                language='en',
                word_timestamps=True,      # Enable word-level timestamps
                verbose=False
            )

            segments = result.get('segments', [])

            if not segments:
                return result['text'].strip()

            # Process each segment, flag low confidence ones
            final_parts = []
            flagged_parts = []

            for seg in segments:
                text = seg['text'].strip()
                avg_logprob = seg.get('avg_logprob', 0)
                no_speech_prob = seg.get('no_speech_prob', 0)

                # Skip if it's probably not speech at all
                if no_speech_prob > 0.6:
                    continue

                if avg_logprob < self.CONFIDENCE_THRESHOLD:
                    # Low confidence — mark for correction
                    flagged_parts.append({
                        'text': text,
                        'confidence': avg_logprob,
                        'index': len(final_parts)
                    })
                    final_parts.append(f"[?]{text}[/?]")  # Placeholder
                    print(f"⚠️  Low confidence segment (score: {avg_logprob:.2f}): '{text}'")
                else:
                    final_parts.append(text)

            # If there are flagged parts and Groq is available, correct them
            if flagged_parts and self.groq_client:
                full_context = ' '.join(p.replace('[?]', '').replace('[/?]', '') 
                                       for p in final_parts)
                
                for flagged in flagged_parts:
                    corrected = self._correct_with_groq(flagged['text'], full_context)
                    if corrected:
                        final_parts[flagged['index']] = corrected
                        print(f"✅ Corrected: '{flagged['text']}' → '{corrected}'")

            return ' '.join(final_parts).strip()

        except Exception as e:
            print(f"Transcription error: {e}")
            return ""

    # ─────────────────────────────────────────────
    # CORRECTION LAYER — Groq fixes bad segments
    # ─────────────────────────────────────────────
    def _correct_with_groq(self, uncertain_text, full_context):
        """Send low-confidence segment to Groq for correction"""
        try:
            prompt = f"""You are correcting a speech-to-text transcription error.

Full transcript context:
"{full_context}"

The following phrase was transcribed with low confidence and may be wrong:
"{uncertain_text}"

Based on the context, what did the speaker most likely say? 
Reply with ONLY the corrected phrase — no explanation, no quotes, just the corrected text.
If the original seems fine, return it as-is."""

            response = self.groq_client.chat.completions.create(
                model=self.config.AI_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=100,
                temperature=0.1  # Low temperature = more deterministic corrections
            )

            corrected = response.choices[0].message.content.strip()

            # Sanity check — if Groq returns something way longer, discard it
            if len(corrected) > len(uncertain_text) * 3:
                return uncertain_text

            return corrected

        except Exception as e:
            print(f"⚠️  Groq correction failed: {e}")
            return uncertain_text  # Fall back to original

    # ─────────────────────────────────────────────
    # STATS — useful for debugging quality
    # ─────────────────────────────────────────────
    def get_transcription_stats(self, audio_data):
        """Returns transcript + quality stats — useful for debugging"""
        if audio_data is None or len(audio_data) == 0:
            return {"transcript": "", "stats": {}}

        result = self.model.transcribe(
            audio_data,
            fp16=False,
            language='en',
            word_timestamps=True
        )

        segments = result.get('segments', [])
        if not segments:
            return {"transcript": result['text'], "stats": {}}

        confidences = [s.get('avg_logprob', 0) for s in segments]
        low_conf_count = sum(1 for c in confidences if c < self.CONFIDENCE_THRESHOLD)

        return {
            "transcript": result['text'].strip(),
            "stats": {
                "total_segments": len(segments),
                "low_confidence_segments": low_conf_count,
                "avg_confidence": round(np.mean(confidences), 3),
                "quality_score": round((1 - low_conf_count / max(len(segments), 1)) * 100, 1)
            }
        }

    # ─────────────────────────────────────────────
    # FILE TRANSCRIPTION — for uploaded files
    # ─────────────────────────────────────────────
    def transcribe_file(self, filename):
        """Transcribe uploaded audio file with correction"""
        result = self.model.transcribe(filename, word_timestamps=True)
        segments = result.get('segments', [])

        if not segments:
            return result['text']

        final_parts = []
        for seg in segments:
            text = seg['text'].strip()
            avg_logprob = seg.get('avg_logprob', 0)
            no_speech_prob = seg.get('no_speech_prob', 0)

            if no_speech_prob > 0.6:
                continue

            if avg_logprob < self.CONFIDENCE_THRESHOLD and self.groq_client:
                full_context = result['text']
                corrected = self._correct_with_groq(text, full_context)
                final_parts.append(corrected)
            else:
                final_parts.append(text)

        return ' '.join(final_parts).strip()