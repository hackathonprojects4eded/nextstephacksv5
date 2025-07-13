import sys
import threading
import time
import numpy as np
from pydub import AudioSegment
import os
import scipy.io.wavfile as wav  # Corrected import for saving WAV files
import sounddevice as sd  # Corrected import for recording audio


def dB_to_amplitude(dB):
    """Convert decibels to amplitude"""
    return 10 ** (dB / 20)


class AudioRecorder:
    def __init__(
        self,
        threshold,
        filename="conversations/temp.wav",
        sample_rate=44100,
        timeThres=5,
        stop_callback=None,  # Function to call when recording stops
    ):
        self.filename = filename
        self.threshold = threshold
        self.sample_rate = sample_rate
        self.audio_data = []
        self.recording = False
        self.current_chunk = np.zeros((1, 1))
        self.start_time = None
        self.elapsedTime = timeThres
        self.stop_event = threading.Event()
        self.update_callback = None  # Function to update the sound meter
        self.stop_callback = stop_callback  # Callback for when recording stops
        self.globalTime = time.time()
        self.isAiTalking = False

    def start_recording(self):
        """Start recording audio based on volume threshold"""
        print("Starting audio recording...")

        with sd.InputStream(
            callback=self.audio_callback, channels=1, samplerate=self.sample_rate
        ):
            while not self.stop_event.is_set():
                if not self.isAiTalking:
                    if time.time() - self.globalTime > 2:
                        if self.recording:
                            if np.max(np.abs(self.current_chunk)) < self.threshold:
                                elapsed_time = time.time() - self.start_time
                                if elapsed_time > self.elapsedTime:
                                    self.recording = False
                                    print(
                                        f"Recording stopped due to silence after {self.elapsedTime}s."
                                    )
                                    self.save_wav()
                                    if self.stop_callback:
                                        self.stop_callback()  # Call the stop callback

                                    print("Checking for new recording/peak")
                        else:
                            if np.max(np.abs(self.current_chunk)) >= self.threshold:
                                self.recording = True
                                self.start_time = time.time()
                                print("Recording started due to detected sound.")
                                self.audio_data = [self.current_chunk.copy()]
                        time.sleep(0.1)  # Small delay to reduce CPU usage

    def audio_callback(self, indata, frames, time, status):
        """Callback function to handle audio data"""
        if status:
            print(status, file=sys.stderr)
        self.current_chunk = indata.copy()
        if self.recording:
            self.audio_data.append(indata.copy())
        # Update the sound meter if a callback is provided
        if self.update_callback:
            level = np.max(np.abs(indata))
            self.update_callback(level)

    def save_wav(self):
        """Save recorded audio data to WAV file"""
        audio_data = np.concatenate(self.audio_data, axis=0)
        wav.write(self.filename, self.sample_rate, audio_data.astype(np.float32))
        self.process_audio()

    def process_audio(self):
        """Process the WAV file and save as MP3"""
        audio = AudioSegment.from_wav(self.filename)
        mp3_filename = "conversations/user_input.mp3"
        os.makedirs(os.path.dirname(mp3_filename), exist_ok=True)
        audio.export(mp3_filename, format="mp3")
        print(f"Audio saved as {mp3_filename}")

    def stop_recording(self):
        """Stop the recording"""
        self.stop_event.set()
        print("Recording stopped.")
