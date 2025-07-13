# Requires the 'sounddevice' package. Install with: pip install sounddevice
import threading
import time
import numpy as np
import sounddevice as sd


def dB_to_amplitude(dB):
    """Convert decibels to amplitude"""
    return 10 ** (dB / 20)


class VoiceDetector:
    def __init__(self, threshold, sample_rate=44100, chunk_size=1024, callback=None):
        """
        threshold: Amplitude threshold for detecting voice activity
        sample_rate: Microphone sample rate
        chunk_size: Number of samples per read
        callback: Function to call when talking state changes (is_talking: bool)
        """
        self.threshold = threshold
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.callback = callback
        self.is_talking = False
        self._stop_event = threading.Event()
        self._thread = None

    def start(self):
        if self._thread is None or not self._thread.is_alive():
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=1)

    def _run(self):
        try:
            with sd.InputStream(
                channels=1, samplerate=self.sample_rate, blocksize=self.chunk_size
            ) as stream:
                while not self._stop_event.is_set():
                    audio_chunk, _ = stream.read(self.chunk_size)
                    level = np.max(np.abs(audio_chunk))
                    new_state = level >= self.threshold

                    if new_state != self.is_talking:
                        self.is_talking = new_state
                        if self.callback:
                            self.callback(self.is_talking)
                    time.sleep(0.05)  # Check ~20 times per second
        except Exception as e:
            print(f"VoiceDetector error: {e}")
