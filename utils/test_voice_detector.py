from voice_detector import VoiceDetector, dB_to_amplitude
import time

# Set threshold in dB (adjust as needed)
THRESHOLD_DB = -35  # Try -40, -35, -30, etc.


def on_talking(is_talking):
    if is_talking:
        print("Talking!")
    else:
        print("Silent.")


def main():
    print(
        f"Testing VoiceDetector with threshold {THRESHOLD_DB} dB (amplitude: {dB_to_amplitude(THRESHOLD_DB):.5f})"
    )
    detector = VoiceDetector(
        threshold=dB_to_amplitude(THRESHOLD_DB), callback=on_talking
    )
    detector.start()
    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nStopping VoiceDetector...")
        detector.stop()


if __name__ == "__main__":
    main()
