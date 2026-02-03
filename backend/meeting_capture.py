import pyaudio
import numpy as np
import whisper
import threading
import queue
import time
from enum import Enum

class AudioSource(Enum):
    MICROPHONE = "mic"
    SPEAKER_OUTPUT = "speaker"
    BOTH = "both"

class MeetingCapture:
    def __init__(self, source_type=AudioSource.SPEAKER_OUTPUT):
        self.source_type = source_type
        self.p = pyaudio.PyAudio()
        self.audio_queue = queue.Queue()
        self.is_recording = False
        
    def list_audio_sources(self):
        """List all audio devices categorized"""
        print("\n" + "="*60)
        print("🎯 SELECT AUDIO SOURCE FOR MEETING CAPTURE")
        print("="*60)
        
        microphones = []
        speakers_out = []
        
        for i in range(self.p.get_device_count()):
            info = self.p.get_device_info_by_index(i)
            
            if info['maxInputChannels'] > 0:
                if "microphone" in info['name'].lower() or "mic" in info['name'].lower():
                    microphones.append((i, info['name'], "🎤 MIC"))
                elif "stereo mix" in info['name'].lower() or "what you hear" in info['name'].lower():
                    speakers_out.append((i, info['name'], "🔊 SPEAKER OUTPUT"))
                elif "output" in info['name'].lower() or "speaker" in info['name'].lower():
                    speakers_out.append((i, info['name'], "🔊 SPEAKER"))
                else:
                    microphones.append((i, info['name'], "🎤 INPUT"))
        
        print("\n🎤 MICROPHONES (Your voice):")
        for idx, name, typ in microphones:
            print(f"  [{idx}] {typ}: {name}")
            
        print("\n🔊 SPEAKER OUTPUTS (Meeting audio):")
        for idx, name, typ in speakers_out:
            print(f"  [{idx}] {typ}: {name}")
            
        print("\n💡 RECOMMENDATION:")
        print("  • For Zoom/Teams meetings with your participation:")
        print("    → Choose BOTH (mic + speaker) ⭐ BEST OPTION")
        print("  • For listening to meetings only: Choose SPEAKER OUTPUT")
        print("  • For in-person meetings: Choose MICROPHONE")
        print("="*60)
        
        return microphones, speakers_out
        
    def start_capture(self, device_index=None, capture_both=False):
        """Start capturing audio"""
        self.is_recording = True

        if capture_both:
            # Capture from BOTH microphone and speaker output
            print("🔍 Finding audio devices...")
            mic_index = self._find_microphone()
            speaker_index = self._find_stereo_mix()

            if mic_index is None or speaker_index is None:
                self.is_recording = False
                print("❌ Cannot start dual capture - device not found")
                return False

            print(f"🎯 Starting DUAL capture:")
            print(f"   🎤 Microphone: device {mic_index}")
            print(f"   🔊 Speaker output: device {speaker_index}")

            # Start two threads for dual capture
            self.mic_thread = threading.Thread(
                target=self._capture_loop_dual,
                args=(mic_index, "mic"),
                daemon=True
            )
            self.speaker_thread = threading.Thread(
                target=self._capture_loop_dual,
                args=(speaker_index, "speaker"),
                daemon=True
            )

            self.mic_thread.start()
            self.speaker_thread.start()

        else:
            # Single source capture
            if device_index is None:
                # Auto-select based on source type
                print("🔍 Finding audio device...")
                if self.source_type == AudioSource.SPEAKER_OUTPUT:
                    device_index = self._find_stereo_mix()
                else:
                    device_index = self._find_microphone()

            if device_index is None:
                self.is_recording = False
                print("❌ Cannot start capture - device not found")
                return False

            print(f"🎯 Starting capture from device {device_index}...")

            # Start recording thread
            self.thread = threading.Thread(
                target=self._capture_loop,
                args=(device_index,),
                daemon=True
            )
            self.thread.start()

        return True
        
    def _validate_device(self, device_index):
        """Validate if device can be opened"""
        try:
            # Try to open a test stream
            test_stream = self.p.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=16000,
                input=True,
                input_device_index=device_index,
                frames_per_buffer=1024
            )
            test_stream.close()
            return True
        except Exception as e:
            print(f"   Device {device_index} validation failed: {e}")
            return False

    def _find_stereo_mix(self):
        """Find Stereo Mix or similar device"""
        # First pass: Look for stereo mix
        for i in range(self.p.get_device_count()):
            try:
                info = self.p.get_device_info_by_index(i)
                if info['maxInputChannels'] > 0:
                    name_lower = info['name'].lower()
                    if "stereo mix" in name_lower or "what you hear" in name_lower or "waveout" in name_lower:
                        if self._validate_device(i):
                            return i
            except:
                continue

        # Second pass: Try speaker outputs
        for i in range(self.p.get_device_count()):
            try:
                info = self.p.get_device_info_by_index(i)
                if info['maxInputChannels'] > 0 and ("output" in info['name'].lower() or "speaker" in info['name'].lower()):
                    if self._validate_device(i):
                        return i
            except:
                continue

        # Last resort: try default input
        try:
            default_idx = self.p.get_default_input_device_info()['index']
            if self._validate_device(default_idx):
                return default_idx
        except:
            pass

        print("\n❌ ERROR: No valid speaker output device found!")
        print("   Please enable 'Stereo Mix' in Windows Sound settings:")
        print("   1. Right-click speaker icon → Sounds")
        print("   2. Recording tab → Right-click → Show Disabled Devices")
        print("   3. Enable 'Stereo Mix'\n")
        return None

    def _find_microphone(self):
        """Find a microphone"""
        # Look for microphone
        for i in range(self.p.get_device_count()):
            try:
                info = self.p.get_device_info_by_index(i)
                if info['maxInputChannels'] > 0 and ("microphone" in info['name'].lower() or "mic" in info['name'].lower()):
                    if self._validate_device(i):
                        return i
            except:
                continue

        # Try default input
        try:
            default_idx = self.p.get_default_input_device_info()['index']
            if self._validate_device(default_idx):
                return default_idx
        except:
            pass

        print("\n❌ ERROR: No valid microphone device found!")
        return None
        
    def _capture_loop(self, device_index):
        """Capture audio continuously from single source"""
        try:
            stream = self.p.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=16000,
                input=True,
                input_device_index=device_index,
                frames_per_buffer=16000*5  # 5 seconds
            )
        except Exception as e:
            print(f"❌ Failed to open audio stream: {e}")
            self.is_recording = False
            return

        while self.is_recording:
            try:
                # Read 5 seconds of audio
                audio_data = stream.read(16000*5, exception_on_overflow=False)

                # Convert to numpy
                audio_np = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0

                # Put in queue
                self.audio_queue.put(audio_np)

            except Exception as e:
                print(f"Audio capture error: {e}")
                break

        try:
            stream.stop_stream()
            stream.close()
        except:
            pass

    def _capture_loop_dual(self, device_index, source_name):
        """Capture audio from one source for dual capture mode"""
        stream = None
        try:
            stream = self.p.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=16000,
                input=True,
                input_device_index=device_index,
                frames_per_buffer=16000*5  # 5 seconds
            )

            print(f"   ✅ {source_name} stream opened successfully")

            # Create a separate queue for this source
            if not hasattr(self, 'mic_queue'):
                self.mic_queue = queue.Queue()
                self.speaker_queue = queue.Queue()

            while self.is_recording:
                try:
                    # Read 5 seconds of audio
                    audio_data = stream.read(16000*5, exception_on_overflow=False)

                    # Convert to numpy
                    audio_np = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0

                    # Put in appropriate queue
                    if source_name == "mic":
                        self.mic_queue.put(audio_np)
                    else:
                        self.speaker_queue.put(audio_np)

                    # Try to mix if both queues have data
                    self._try_mix_audio()

                except Exception as e:
                    print(f"Audio capture error ({source_name}): {e}")
                    break

        except Exception as e:
            print(f"❌ Failed to open {source_name} stream: {e}")
            print(f"   Device {device_index} cannot be opened")

        finally:
            if stream:
                try:
                    stream.stop_stream()
                    stream.close()
                except:
                    pass

    def _try_mix_audio(self):
        """Mix audio from both sources if available"""
        try:
            # Check if both queues have data
            if hasattr(self, 'mic_queue') and hasattr(self, 'speaker_queue'):
                if not self.mic_queue.empty() and not self.speaker_queue.empty():
                    mic_audio = self.mic_queue.get_nowait()
                    speaker_audio = self.speaker_queue.get_nowait()

                    # Mix the audio (average them)
                    mixed_audio = (mic_audio + speaker_audio) / 2.0

                    # Put mixed audio in main queue
                    self.audio_queue.put(mixed_audio)

        except queue.Empty:
            pass
        except Exception as e:
            print(f"Audio mixing error: {e}")
        
    def get_audio_chunk(self):
        """Get next audio chunk"""
        try:
            return self.audio_queue.get(timeout=1)
        except queue.Empty:
            return None
            
    def stop(self):
        """Stop capturing"""
        self.is_recording = False

        # Wait for threads to finish
        if hasattr(self, 'thread'):
            self.thread.join()
        if hasattr(self, 'mic_thread'):
            self.mic_thread.join()
        if hasattr(self, 'speaker_thread'):
            self.speaker_thread.join()

        self.p.terminate()