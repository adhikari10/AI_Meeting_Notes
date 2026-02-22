import numpy as np
from scipy import signal

class SimpleSpeakerDetector:
    def __init__(self):
        self.speaker_profiles = []
        self.current_speaker_id = 0

    def extract_voice_features(self, audio_chunk):
        """Extract pitch and energy from audio"""
        # Pitch estimation
        autocorr = np.correlate(audio_chunk, audio_chunk, mode='full')
        autocorr = autocorr[len(autocorr)//2:]
        peaks = signal.find_peaks(autocorr)[0]
        pitch = 16000 / peaks[0] if len(peaks) > 0 else 0

        # Energy
        energy = np.sqrt(np.mean(audio_chunk ** 2))

        return {"pitch": pitch, "energy": energy}

    def detect_speaker(self, audio_chunk):
        """Detect which speaker (returns 'Speaker 1', 'Speaker 2', etc.)"""
        features = self.extract_voice_features(audio_chunk)

        if not self.speaker_profiles:
            self.speaker_profiles.append(features)
            return "Speaker 1"

        # Find closest match
        min_distance = float('inf')
        best_match = 0

        for i, profile in enumerate(self.speaker_profiles):
            distance = abs(features["pitch"] - profile["pitch"]) / 200
            if distance < min_distance:
                min_distance = distance
                best_match = i

        # New speaker if distance too large
        if min_distance > 0.3:
            self.speaker_profiles.append(features)
            return f"Speaker {len(self.speaker_profiles)}"

        return f"Speaker {best_match + 1}"
