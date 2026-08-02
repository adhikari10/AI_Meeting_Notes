import os
import shutil
import subprocess
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path

from openai import OpenAI


class TranscriptionProvider(ABC):
    """Interface for pluggable file-based transcription backends."""

    @abstractmethod
    def transcribe_file(self, path: str, language: str = None) -> str:
        ...


class GroqTranscriptionProvider(TranscriptionProvider):
    """Transcribes audio files via Groq's OpenAI-compatible Whisper endpoint.

    Groq caps uploads at ~25MB, so files above max_chunk_bytes are re-encoded
    to low-bitrate mono mp3 and split into duration-based segments with ffmpeg
    first, then transcribed one chunk at a time and joined.
    """

    MODEL = "whisper-large-v3-turbo"
    DEFAULT_MAX_CHUNK_BYTES = 24 * 1024 * 1024  # stay under Groq's ~25MB cap
    CHUNK_BITRATE_KBPS = 64  # mono, speech-optimized — keeps chunk sizes predictable

    def __init__(self):
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GROQ_API_KEY is not set — required for Groq file transcription."
            )
        self.client = OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")

        # Overridable so a small test file can be forced through the chunking
        # path without needing a real multi-hour recording.
        self.max_chunk_bytes = int(
            os.getenv("GROQ_TRANSCRIBE_CHUNK_BYTES", self.DEFAULT_MAX_CHUNK_BYTES)
        )

    def transcribe_file(self, path: str, language: str = None) -> str:
        path = str(path)
        size = os.path.getsize(path)

        if size <= self.max_chunk_bytes:
            return self._transcribe_single(path, language)

        tmp_dir, chunk_paths = self._split_for_size(path)
        try:
            texts = [self._transcribe_single(p, language) for p in chunk_paths]
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

        # NOTE: naive space-join for v1 — word-level seams between chunks
        # aren't handled, so a word right at a chunk boundary can occasionally
        # be clipped or duplicated. Revisit with overlap/stitch logic if
        # boundary artefacts turn out to matter in practice.
        return ' '.join(t.strip() for t in texts if t and t.strip())

    def _transcribe_single(self, path: str, language: str = None) -> str:
        with open(path, 'rb') as f:
            kwargs = {"model": self.MODEL, "file": f}
            if language:
                kwargs["language"] = language
            result = self.client.audio.transcriptions.create(**kwargs)
        return result.text

    def _split_for_size(self, path: str):
        bytes_per_second = (self.CHUNK_BITRATE_KBPS * 1000) / 8
        # 90% safety margin under the byte cap to absorb container overhead
        chunk_seconds = max(1, int((self.max_chunk_bytes * 0.9) / bytes_per_second))

        tmp_dir = Path(tempfile.mkdtemp(prefix="groq_chunks_"))
        pattern = str(tmp_dir / "chunk_%03d.mp3")

        cmd = [
            "ffmpeg", "-y", "-i", path,
            "-vn", "-ac", "1", "-ar", "16000",
            "-c:a", "libmp3lame", "-b:a", f"{self.CHUNK_BITRATE_KBPS}k",
            "-f", "segment", "-segment_time", str(chunk_seconds),
            pattern,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        chunk_files = sorted(tmp_dir.glob("chunk_*.mp3"))

        if proc.returncode != 0 or not chunk_files:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            raise RuntimeError(f"ffmpeg chunking failed: {proc.stderr[-500:]}")

        print(f"🔪 Split '{Path(path).name}' into {len(chunk_files)} chunk(s) "
              f"(~{chunk_seconds}s each) for Groq transcription")
        return tmp_dir, [str(p) for p in chunk_files]


def probe_duration(path: str):
    """Return audio duration in seconds via ffprobe, or None on failure."""
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path),
    ]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return float(out.stdout.strip())
    except Exception:
        return None
