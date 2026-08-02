import numpy as np

try:
    from resemblyzer import VoiceEncoder, preprocess_wav
    RESEMBLYZER_AVAILABLE = True
except ImportError:
    RESEMBLYZER_AVAILABLE = False


class SimpleSpeakerDetector:
    """
    Speaker diarisation using Resemblyzer's 256-dimensional voice embeddings.

    Compares embeddings via cosine similarity so that even speakers with
    very different recording volumes are distinguished reliably.

    If resemblyzer is not installed the detector degrades gracefully:
    detect_speaker() always returns "Speaker 1" without crashing the app.

    Parameters
    ----------
    similarity_threshold : float
        Cosine similarity above which two segments are considered the same
        speaker.  0.75 is a good default for meeting audio.
    max_speakers : int
        Hard cap on the number of distinct speakers tracked (default 6).
    sample_rate : int
        Input audio sample rate in Hz (default 16 000).
    """

    def __init__(
        self,
        similarity_threshold: float = 0.82,
        max_speakers: int = 6,
        sample_rate: int = 16000,
    ):
        self.similarity_threshold = similarity_threshold
        self.max_speakers = max_speakers
        self.sample_rate = sample_rate

        # Each entry is the mean embedding vector for that speaker.
        self.speaker_profiles: list[np.ndarray] = []
        self.last_speaker = "Speaker 1"

        if RESEMBLYZER_AVAILABLE:
            try:
                self.encoder = VoiceEncoder()
                print("✅ Resemblyzer VoiceEncoder loaded")
            except Exception as e:
                print(f"⚠️  VoiceEncoder failed to load: {e}")
                self.encoder = None
        else:
            self.encoder = None
            print("⚠️  Resemblyzer not installed — speaker detection disabled")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def reset(self):
        """Clear all stored speaker profiles (call at the start of each meeting)."""
        self.speaker_profiles = []
        self.last_speaker = "Speaker 1"

    def extract_voice_features(self, audio_chunk: np.ndarray) -> dict:
        """
        Return a feature dict for *audio_chunk*.

        Keys
        ----
        embedding : ndarray | None
            256-dim Resemblyzer embedding, or None if unavailable.
        energy : float
            RMS amplitude of the chunk.
        """
        audio = audio_chunk.astype(np.float32)
        energy = float(np.sqrt(np.mean(audio ** 2)))

        embedding = None
        if self.encoder is not None:
            try:
                processed = preprocess_wav(audio, source_sr=self.sample_rate)
                embedding = self.encoder.embed_utterance(processed)
            except Exception as e:
                print(f"⚠️  Embedding extraction failed: {e}")

        return {"embedding": embedding, "energy": energy}

    def detect_speaker(self, audio_chunk: np.ndarray) -> str:
        """
        Identify the most likely speaker for *audio_chunk*.

        Returns a string such as ``'Speaker 1'``, ``'Speaker 2'``, etc.

        If Resemblyzer is unavailable or fails to process the chunk the
        method returns the last successfully detected speaker label instead
        of raising an exception.
        """
        audio = audio_chunk.astype(np.float32)

        # Skip silent / low-energy chunks — return the last known speaker
        energy = float(np.sqrt(np.mean(audio ** 2)))
        if energy < 0.01:
            return self.last_speaker

        if self.encoder is None:
            # No model — stay with the last known speaker
            return self.last_speaker

        try:
            processed = preprocess_wav(audio, source_sr=self.sample_rate)
            embedding = self.encoder.embed_utterance(processed)
        except Exception as e:
            print(f"⚠️  Speaker detection failed, keeping '{self.last_speaker}': {e}")
            return self.last_speaker

        speaker = self._match_or_create(embedding)
        self.last_speaker = speaker
        return speaker

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        """Cosine similarity between two vectors."""
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))

    def _match_or_create(self, embedding: np.ndarray) -> str:
        """
        Compare *embedding* against all stored profiles.

        * If the best cosine similarity >= threshold → matched speaker.
        * Otherwise, if under the speaker cap → new speaker.
        * If at the cap → assign to the closest existing speaker anyway.

        Matched profiles are updated with a rolling average
        (80 % old, 20 % new) to adapt gradually to voice changes.
        """
        # First segment ever
        if not self.speaker_profiles:
            self.speaker_profiles.append(embedding.copy())
            return "Speaker 1"

        # Rank all existing profiles by cosine similarity
        best_sim = -1.0
        best_idx = 0
        for i, profile in enumerate(self.speaker_profiles):
            sim = self._cosine_similarity(embedding, profile)
            if sim > best_sim:
                best_sim = sim
                best_idx = i

        if best_sim >= self.similarity_threshold:
            # Recognised speaker — update profile (rolling average 90/10)
            self.speaker_profiles[best_idx] = (
                0.9 * self.speaker_profiles[best_idx] + 0.1 * embedding
            )
            return f"Speaker {best_idx + 1}"

        if len(self.speaker_profiles) < self.max_speakers:
            # New speaker, still under the cap
            self.speaker_profiles.append(embedding.copy())
            return f"Speaker {len(self.speaker_profiles)}"

        # At the cap — assign to closest profile without updating it
        return f"Speaker {best_idx + 1}"
