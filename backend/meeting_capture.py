"""
Meeting Capture - ENHANCED with PyAudioWPatch support
Auto-detects and uses PyAudioWPatch if available for better Windows audio
"""
import numpy as np
import threading
import queue
import time
from enum import Enum

# Try to import PyAudioWPatch first (better for Windows), fallback to regular PyAudio
try:
    import pyaudiowpatch as pyaudio
    USING_WPATCH = True
    print("✅ Using PyAudioWPatch - Enhanced Windows audio support enabled!")
except ImportError:
    try:
        import pyaudio
        USING_WPATCH = False
        print("ℹ️  Using standard PyAudio")
    except ImportError:
        print("❌ ERROR: Neither PyAudioWPatch nor PyAudio found!")
        print("   Install with: pip install PyAudioWPatch")
        raise

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
        self.using_wpatch = USING_WPATCH
        
    def list_audio_devices(self):
        """List all available audio devices with quality info"""
        devices = []
        
        for i in range(self.p.get_device_count()):
            try:
                info = self.p.get_device_info_by_index(i)
                devices.append({
                    'index': i,
                    'name': info['name'],
                    'max_input_channels': info['maxInputChannels'],
                    'max_output_channels': info['maxOutputChannels'],
                    'default_samplerate': int(info['defaultSampleRate']),
                    'hostapi': info['hostApi']
                })
            except Exception as e:
                print(f"Warning: Could not get info for device {i}: {e}")
                continue
        
        return devices
        
    def list_audio_sources(self):
        """List all audio devices categorized - ENHANCED"""
        print("\n" + "="*70)
        print("🎯 SELECT AUDIO SOURCE FOR MEETING CAPTURE")
        if self.using_wpatch:
            print("   ✅ PyAudioWPatch ENABLED - Loopback capture available!")
        print("="*70)
        
        microphones = []
        speakers_out = []
        loopback = []  # For PyAudioWPatch loopback devices
        
        for i in range(self.p.get_device_count()):
            try:
                info = self.p.get_device_info_by_index(i)
                
                # PyAudioWPatch loopback devices (WASAPI)
                if self.using_wpatch and info.get('isLoopbackDevice', False):
                    loopback.append((i, info['name'], "🔄 LOOPBACK", info))
                
                # Regular input devices
                elif info['maxInputChannels'] > 0:
                    name_lower = info['name'].lower()
                    sample_rate = int(info['defaultSampleRate'])
                    channels = info['maxInputChannels']
                    
                    # Quality indicator
                    if sample_rate >= 44100:
                        quality = "🟢 HIGH"
                    elif sample_rate >= 16000:
                        quality = "🟡 GOOD"
                    else:
                        quality = "🔴 LOW"
                    
                    device_info = (i, info['name'], quality, sample_rate, channels)
                    
                    if "microphone" in name_lower or "mic" in name_lower:
                        microphones.append(device_info)
                    elif "stereo mix" in name_lower or "what you hear" in name_lower:
                        speakers_out.append(device_info)
                    elif "output" in name_lower or "speaker" in name_lower:
                        speakers_out.append(device_info)
                    else:
                        microphones.append(device_info)
            except Exception as e:
                continue
        
        # Display with enhanced info
        if self.using_wpatch and loopback:
            print("\n🔄 LOOPBACK DEVICES (BEST - Captures system audio directly):")
            print("   ⭐ RECOMMENDED for Zoom/Teams/Meet")
            for idx, name, typ, info in loopback:
                sample_rate = int(info['defaultSampleRate'])
                print(f"  [{idx}] {name}")
                print(f"       Quality: 🟢 HIGH | Sample Rate: {sample_rate}Hz | Type: WASAPI Loopback")
        
        print("\n🎤 MICROPHONES (Your voice):")
        for idx, name, quality, sr, ch in microphones:
            print(f"  [{idx}] {name}")
            print(f"       Quality: {quality} | Sample Rate: {sr}Hz | Channels: {ch}")
        
        print("\n🔊 SPEAKER OUTPUTS (Meeting audio - Stereo Mix):")
        if not speakers_out:
            print("  ⚠️  No Stereo Mix found - you may need to enable it in Windows Sound settings")
        for idx, name, quality, sr, ch in speakers_out:
            print(f"  [{idx}] {name}")
            print(f"       Quality: {quality} | Sample Rate: {sr}Hz | Channels: {ch}")
        
        print("\n💡 RECOMMENDATION:")
        if self.using_wpatch and loopback:
            print("  ⭐ BEST: Choose a LOOPBACK device above (captures system audio perfectly)")
        print("  • For Zoom/Teams WITH your voice: Choose BOTH (mic + speaker/loopback)")
        print("  • For listening only: Choose SPEAKER OUTPUT or LOOPBACK")
        print("  • For in-person meetings: Choose MICROPHONE")
        print("="*70)
        
        return microphones, speakers_out, loopback if self.using_wpatch else []
    
    def get_wasapi_loopback_device(self):
        """Get default WASAPI loopback device (PyAudioWPatch only)"""
        if not self.using_wpatch:
            return None
        
        try:
            # Get default WASAPI output device
            wasapi_info = self.p.get_host_api_info_by_type(pyaudio.paWASAPI)
            default_speakers = wasapi_info["defaultOutputDevice"]
            
            if default_speakers != -1:
                # Get loopback device for default speakers
                speakers_info = self.p.get_device_info_by_index(default_speakers)
                
                # Check if this is already a loopback device
                if not speakers_info.get('isLoopbackDevice', False):
                    # Find corresponding loopback device
                    for i in range(self.p.get_device_count()):
                        info = self.p.get_device_info_by_index(i)
                        if (info.get('isLoopbackDevice', False) and 
                            info['name'] == speakers_info['name']):
                            return i
                else:
                    return default_speakers
        except Exception as e:
            print(f"Could not get WASAPI loopback: {e}")
        
        return None
        
    def start(self, device_index=None, sample_rate=16000, chunk_duration=5, capture_both=False):
        """
        Start capturing audio - ENHANCED
        
        Args:
            device_index: Device to use (None = auto-detect)
            sample_rate: Sample rate (16000 good for speech)
            chunk_duration: Seconds per chunk (5 recommended)
            capture_both: Capture mic + speaker simultaneously
        """
        self.is_recording = True
        self.sample_rate = sample_rate
        self.chunk_size = sample_rate * chunk_duration

        if capture_both:
            # Capture from BOTH microphone and speaker output
            print("🔍 Finding audio devices for dual capture...")
            
            mic_index = self._find_microphone()
            
            # For speaker, prefer loopback if available
            if self.using_wpatch:
                speaker_index = self.get_wasapi_loopback_device()
                if speaker_index is None:
                    speaker_index = self._find_stereo_mix()
            else:
                speaker_index = self._find_stereo_mix()

            if mic_index is None or speaker_index is None:
                self.is_recording = False
                print("❌ Cannot start dual capture - device not found")
                return False

            print(f"🎯 Starting DUAL capture:")
            print(f"   🎤 Microphone: device {mic_index}")
            print(f"   🔊 Speaker: device {speaker_index}")
            if self.using_wpatch:
                print(f"   ✅ Using WASAPI Loopback for better quality!")

            # Start two threads for dual capture
            self.mic_thread = threading.Thread(
                target=self._capture_loop_dual,
                args=(mic_index, "mic", sample_rate, chunk_duration),
                daemon=True
            )
            self.speaker_thread = threading.Thread(
                target=self._capture_loop_dual,
                args=(speaker_index, "speaker", sample_rate, chunk_duration),
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
                    # Prefer WASAPI loopback if available
                    if self.using_wpatch:
                        device_index = self.get_wasapi_loopback_device()
                        if device_index:
                            print("✅ Using WASAPI Loopback device (best quality)")
                    
                    if device_index is None:
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
                args=(device_index, sample_rate, chunk_duration),
                daemon=True
            )
            self.thread.start()

        return True
    
    def _capture_loop(self, device_index, sample_rate, chunk_duration):
        """Capture audio continuously from single source - ENHANCED"""
        try:
            # For WASAPI loopback, use specific settings
            if self.using_wpatch:
                info = self.p.get_device_info_by_index(device_index)
                is_loopback = info.get('isLoopbackDevice', False)
                
                if is_loopback:
                    # Loopback device settings
                    stream = self.p.open(
                        format=pyaudio.paInt16,
                        channels=2,  # Loopback is typically stereo
                        rate=int(info['defaultSampleRate']),
                        input=True,
                        input_device_index=device_index,
                        frames_per_buffer=int(info['defaultSampleRate'] * chunk_duration)
                    )
                    actual_rate = int(info['defaultSampleRate'])
                else:
                    # Regular device
                    stream = self.p.open(
                        format=pyaudio.paInt16,
                        channels=1,
                        rate=sample_rate,
                        input=True,
                        input_device_index=device_index,
                        frames_per_buffer=sample_rate * chunk_duration
                    )
                    actual_rate = sample_rate
            else:
                # Standard PyAudio
                stream = self.p.open(
                    format=pyaudio.paInt16,
                    channels=1,
                    rate=sample_rate,
                    input=True,
                    input_device_index=device_index,
                    frames_per_buffer=sample_rate * chunk_duration
                )
                actual_rate = sample_rate
                
        except Exception as e:
            print(f"❌ Failed to open audio stream: {e}")
            self.is_recording = False
            return

        print(f"✅ Audio stream started (Rate: {actual_rate}Hz)")

        while self.is_recording:
            try:
                # Read chunk
                chunk_samples = int(actual_rate * chunk_duration)
                audio_data = stream.read(chunk_samples, exception_on_overflow=False)

                # Convert to numpy
                audio_np = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0

                # Normalize volume
                max_val = np.max(np.abs(audio_np))
                if max_val > 0:
                    audio_np = audio_np / max_val * 0.95

                # Noise gate
                audio_np[np.abs(audio_np) < 0.01] = 0

                # If stereo, convert to mono
                if len(audio_np.shape) > 1 or audio_np.size > chunk_samples:
                    audio_np = audio_np.reshape(-1, 2).mean(axis=1) if audio_np.size % 2 == 0 else audio_np[:chunk_samples]
                
                # Resample if needed (for Whisper we want 16000Hz)
                if actual_rate != 16000:
                    audio_np = self._resample(audio_np, actual_rate, 16000)

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
    
    def _resample(self, audio, orig_sr, target_sr):
        """Simple resampling (linear interpolation)"""
        if orig_sr == target_sr:
            return audio
        
        duration = len(audio) / orig_sr
        target_length = int(duration * target_sr)
        
        indices = np.linspace(0, len(audio) - 1, target_length)
        resampled = np.interp(indices, np.arange(len(audio)), audio)
        
        return resampled.astype(np.float32)

    def _capture_loop_dual(self, device_index, source_name, sample_rate, chunk_duration):
        """Capture audio from one source for dual capture mode - ENHANCED"""
        stream = None
        try:
            # Check if it's a loopback device
            is_loopback = False
            actual_rate = sample_rate
            channels = 1
            
            if self.using_wpatch:
                info = self.p.get_device_info_by_index(device_index)
                is_loopback = info.get('isLoopbackDevice', False)
                
                if is_loopback:
                    actual_rate = int(info['defaultSampleRate'])
                    channels = 2
            
            stream = self.p.open(
                format=pyaudio.paInt16,
                channels=channels,
                rate=actual_rate,
                input=True,
                input_device_index=device_index,
                frames_per_buffer=actual_rate * chunk_duration
            )

            print(f"   ✅ {source_name} stream opened (Rate: {actual_rate}Hz, Channels: {channels})")

            # Create separate queues for dual sources
            if not hasattr(self, 'mic_queue'):
                self.mic_queue = queue.Queue()
                self.speaker_queue = queue.Queue()

            while self.is_recording:
                try:
                    # Read chunk
                    chunk_samples = int(actual_rate * chunk_duration)
                    audio_data = stream.read(chunk_samples, exception_on_overflow=False)

                    # Convert to numpy
                    audio_np = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0

                    # Convert stereo to mono if needed
                    if channels == 2:
                        audio_np = audio_np.reshape(-1, 2).mean(axis=1)
                    
                    # Resample if needed
                    if actual_rate != 16000:
                        audio_np = self._resample(audio_np, actual_rate, 16000)

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

        finally:
            if stream:
                try:
                    stream.stop_stream()
                    stream.close()
                except:
                    pass

    def _try_mix_audio(self):
        """Mix audio from both sources"""
        if not hasattr(self, 'mic_queue') or not hasattr(self, 'speaker_queue'):
            return

        # Check if both queues have data
        if not self.mic_queue.empty() and not self.speaker_queue.empty():
            mic_audio = self.mic_queue.get()
            speaker_audio = self.speaker_queue.get()

            # Make same length
            min_len = min(len(mic_audio), len(speaker_audio))
            mic_audio = mic_audio[:min_len]
            speaker_audio = speaker_audio[:min_len]

            # Mix (average)
            mixed = (mic_audio + speaker_audio) / 2.0

            # Put in main queue
            self.audio_queue.put(mixed)

    def _validate_device(self, device_index):
        """Validate if device can be opened"""
        try:
            # Get device info
            info = self.p.get_device_info_by_index(device_index)
            
            # For WASAPI loopback, different validation
            if self.using_wpatch and info.get('isLoopbackDevice', False):
                test_stream = self.p.open(
                    format=pyaudio.paInt16,
                    channels=2,
                    rate=int(info['defaultSampleRate']),
                    input=True,
                    input_device_index=device_index,
                    frames_per_buffer=1024
                )
            else:
                # Regular device
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
            return False

    def _find_stereo_mix(self):
        """Find Stereo Mix or similar device"""
        # If using WPatch, prefer loopback
        if self.using_wpatch:
            loopback = self.get_wasapi_loopback_device()
            if loopback is not None:
                return loopback
        
        # First pass: Look for stereo mix
        for i in range(self.p.get_device_count()):
            try:
                info = self.p.get_device_info_by_index(i)
                if info['maxInputChannels'] > 0:
                    name_lower = info['name'].lower()
                    if "stereo mix" in name_lower or "what you hear" in name_lower or "wave out" in name_lower:
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

        print("\n❌ ERROR: No valid speaker output device found!")
        if self.using_wpatch:
            print("   PyAudioWPatch is installed but no loopback devices found.")
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

    def get_audio_chunk(self):
        """Get next audio chunk from queue"""
        try:
            return self.audio_queue.get(timeout=0.5)
        except queue.Empty:
            return None

    def stop(self):
        """Stop recording"""
        self.is_recording = False
        
        # Wait for threads to finish
        if hasattr(self, 'thread') and self.thread.is_alive():
            self.thread.join(timeout=2)
        
        if hasattr(self, 'mic_thread') and self.mic_thread.is_alive():
            self.mic_thread.join(timeout=2)
            
        if hasattr(self, 'speaker_thread') and self.speaker_thread.is_alive():
            self.speaker_thread.join(timeout=2)
        
        # Clear queue
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
            except:
                break
        
        print("🛑 Recording stopped")

    def __del__(self):
        """Cleanup"""
        try:
            self.stop()
            self.p.terminate()
        except:
            pass