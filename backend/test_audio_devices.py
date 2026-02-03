"""
Audio Device Diagnostic Tool
Tests your audio devices and provides setup guidance
"""
import pyaudio
import numpy as np

def list_all_devices():
    """List all audio devices with detailed info"""
    p = pyaudio.PyAudio()

    print("\n" + "="*70)
    print("🔍 AUDIO DEVICE DIAGNOSTIC")
    print("="*70)

    print(f"\n📊 Total devices found: {p.get_device_count()}")

    microphones = []
    speakers_input = []
    outputs_only = []

    for i in range(p.get_device_count()):
        try:
            info = p.get_device_info_by_index(i)
            name = info['name']
            max_in = info['maxInputChannels']
            max_out = info['maxOutputChannels']

            print(f"\n[{i}] {name}")
            print(f"    Input channels: {max_in}")
            print(f"    Output channels: {max_out}")
            print(f"    Default sample rate: {int(info['defaultSampleRate'])} Hz")

            if max_in > 0:
                name_lower = name.lower()
                if "stereo mix" in name_lower or "what you hear" in name_lower:
                    speakers_input.append((i, name, "🔊 STEREO MIX"))
                    print(f"    ✅ Type: STEREO MIX (captures speaker output)")
                elif "microphone" in name_lower or "mic" in name_lower:
                    microphones.append((i, name, "🎤 MICROPHONE"))
                    print(f"    ✅ Type: MICROPHONE")
                else:
                    microphones.append((i, name, "🎤 INPUT"))
                    print(f"    ℹ️  Type: INPUT DEVICE")

            if max_out > 0 and max_in == 0:
                outputs_only.append((i, name))
                print(f"    ℹ️  Type: OUTPUT ONLY (speakers/headphones)")

        except Exception as e:
            print(f"\n[{i}] Error reading device: {e}")

    print("\n" + "="*70)
    print("📋 SUMMARY")
    print("="*70)

    print(f"\n🎤 Microphones found: {len(microphones)}")
    for idx, name, typ in microphones:
        print(f"   [{idx}] {name}")

    print(f"\n🔊 Stereo Mix devices found: {len(speakers_input)}")
    if speakers_input:
        for idx, name, typ in speakers_input:
            print(f"   [{idx}] {name}")
    else:
        print("   ❌ NO STEREO MIX FOUND!")

    print(f"\n🔈 Output-only devices: {len(outputs_only)}")

    p.terminate()

    return microphones, speakers_input

def test_device(device_index):
    """Test if a device can capture audio"""
    print(f"\n" + "="*70)
    print(f"🧪 TESTING DEVICE {device_index}")
    print("="*70)

    p = pyaudio.PyAudio()

    try:
        # Get device info
        info = p.get_device_info_by_index(device_index)
        print(f"\nDevice: {info['name']}")
        print(f"Testing for 3 seconds... (make some noise or play audio)")

        # Try to open stream
        stream = p.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=16000,
            input=True,
            input_device_index=device_index,
            frames_per_buffer=1024
        )

        print("✅ Stream opened successfully!")
        print("🎧 Recording...")

        # Record for 3 seconds
        frames = []
        for _ in range(0, int(16000 / 1024 * 3)):
            data = stream.read(1024, exception_on_overflow=False)
            frames.append(data)

        stream.stop_stream()
        stream.close()

        # Analyze audio
        audio_data = np.frombuffer(b''.join(frames), dtype=np.int16)
        max_amplitude = np.max(np.abs(audio_data))
        avg_amplitude = np.mean(np.abs(audio_data))

        print(f"\n📊 Audio Analysis:")
        print(f"   Max amplitude: {max_amplitude}")
        print(f"   Avg amplitude: {avg_amplitude:.2f}")

        if max_amplitude > 1000:
            print(f"\n✅ SUCCESS! Device is capturing audio properly!")
            return True
        else:
            print(f"\n⚠️  WARNING: Very low audio detected. Device may not be working correctly.")
            return False

    except Exception as e:
        print(f"\n❌ ERROR: Cannot use this device!")
        print(f"   Error: {e}")
        return False
    finally:
        p.terminate()

def show_setup_guide():
    """Show setup instructions for Windows"""
    print("\n" + "="*70)
    print("📖 SETUP GUIDE FOR WINDOWS")
    print("="*70)

    print("""
To capture meeting audio (speaker output), you need to enable Stereo Mix:

1. Right-click the 🔊 speaker icon in your taskbar
2. Select "Sounds" or "Sound settings"
3. Click on the "Recording" tab
4. Right-click in the empty space and select:
   ✅ "Show Disabled Devices"
   ✅ "Show Disconnected Devices"
5. You should now see "Stereo Mix" in the list
6. Right-click "Stereo Mix" → "Enable"
7. (Optional) Right-click "Stereo Mix" → "Set as Default Device"

Alternative methods if Stereo Mix is not available:
- Use VB-Cable or Virtual Audio Cable (free software)
- Use OBS Virtual Camera with audio routing
- Some audio drivers (Realtek) may need to be updated

For Zoom/Teams/Meet specifically:
- Make sure audio is playing through your speakers/headphones
- Stereo Mix captures what your speakers are playing
""")

def main():
    print("Audio Device Test & Setup Tool")

    # List all devices
    microphones, stereo_mix = list_all_devices()

    # Check for Stereo Mix
    if not stereo_mix:
        print("\n" + "⚠️ "*35)
        print("WARNING: No Stereo Mix device found!")
        print("You won't be able to capture meeting audio (speaker output)")
        print("⚠️ "*35)
        show_setup_guide()
    else:
        print(f"\n✅ Great! Stereo Mix is available.")

    # Offer to test devices
    print("\n" + "="*70)
    choice = input("\nWould you like to test a device? (enter device number or 'n' to skip): ").strip()

    if choice.isdigit():
        device_idx = int(choice)
        test_device(device_idx)

    # Recommendations
    print("\n" + "="*70)
    print("💡 RECOMMENDATIONS")
    print("="*70)

    if stereo_mix:
        print(f"\nFor capturing Zoom/Teams meetings:")
        print(f"   Use device [{stereo_mix[0][0]}] {stereo_mix[0][1]}")

    if microphones:
        print(f"\nFor capturing your voice:")
        print(f"   Use device [{microphones[0][0]}] {microphones[0][1]}")

    print("\n" + "="*70)

if __name__ == "__main__":
    main()
