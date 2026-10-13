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
        self._stop_event = threading.Event()
        self._thread = None

    def start(self):
        """Listen on a new thread until stop(). Each run has its own stop event, so a
        run still winding down can neither swallow this start nor keep going."""
        self.stop()
        self._stop_event = threading.Event()
        self._thread = threading.Thread(
            target=self._run, args=(self._stop_event,), daemon=True
        )
        self._thread.start()

    def stop(self):
        """Let go of the mic within ~0.1 s. Doesn't wait: the thread may be blocked
        handing the callback's work to the caller's (Tk) thread."""
        self._stop_event.set()

    def is_alive(self):
        """True until the latest run has let go of the mic."""
        return self._thread is not None and self._thread.is_alive()

    def _run(self, stop_event):
        is_talking = False  # each run starts silent
        try:
            with sd.InputStream(
                channels=1, samplerate=self.sample_rate, blocksize=self.chunk_size
            ) as stream:
                while not stop_event.is_set():
                    audio_chunk, _ = stream.read(self.chunk_size)
                    level = np.max(np.abs(audio_chunk))
                    new_state = level >= self.threshold

                    if new_state != is_talking and not stop_event.is_set():
                        is_talking = new_state
                        if self.callback:
                            self.callback(is_talking)
                    time.sleep(0.05)  # Check ~20 times per second
        except Exception as e:
            print(f"VoiceDetector error: {e}")
