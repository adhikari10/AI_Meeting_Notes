import pyaudio
import numpy as np
import time

def test_microphone():
    """Quick test to check if microphone is working"""
    p = pyaudio.PyAudio()
    
    print("Testing microphone...")
    print("Speak into your microphone for 3 seconds...")
    
    # Open stream
    stream = p.open(format=pyaudio.paInt16,
                    channels=1,
                    rate=16000,
                    input=True,
                    frames_per_buffer=1024)
    
    # Record for 3 seconds
    frames = []
    for _ in range(0, int(16000 / 1024 * 3)):
        data = stream.read(1024)
        frames.append(data)
    
    stream.stop_stream()
    stream.close()
    p.terminate()
    
    # Convert to numpy array
    audio_data = np.frombuffer(b''.join(frames), dtype=np.int16)
    
    print(f"Recorded {len(audio_data)} samples")
    print(f"Max amplitude: {np.max(np.abs(audio_data))}")
    
    if np.max(np.abs(audio_data)) > 1000:
        print("✅ Microphone is working!")
        return True
    else:
        print("❌ No audio detected. Check your microphone.")
        return False

if __name__ == "__main__":
    test_microphone()