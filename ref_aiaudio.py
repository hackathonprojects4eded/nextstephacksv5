import threading
import time
import numpy as np
import pygame
import PIL.Image
import PIL.ImageTk
import tkinter as tk
import os
import math
from openai import OpenAI
from dotenv import load_dotenv
from pydub import AudioSegment
import whisper
import platform

load_dotenv()

OpenAI.api_key = os.getenv("OPENAI_API_KEY")

whisperr = whisper.load_model("base")

if platform.system() != "Darwin":
    import torch
    from TTS.api import TTS

    # Get device
    device = "cuda" if torch.cuda.is_available() else "cpu"
    tts = TTS("tts_models/en/ljspeech/neural_hmm").to(device)
    # print(tts.list_models().list_models())
    # tts_models/en/ljspeech/neural_hmm


class GPTConverter:

    def audio_to_text(self, audio_file):
        """Convert audio file to text using OpenAI's Whisper"""
        # audio_file = open(audio_file, "rb")
        # transcription = client.audio.transcriptions.create(
        #     model="whisper-1", file=audio_file
        # )
        result = whisperr.transcribe(audio_file)
        return result["text"]

    # def text_to_speech(self, text, output_file, voice):
    #     if os.path.exists(output_file):
    #         os.remove(output_file)
    #     tts.tts_to_file(text=text, file_path="conversations/ai.wav")
    #     self.process_audio()
    #     return output_file

    def process_audio(self):
        """Process the WAV file and save as MP3"""
        audio = AudioSegment.from_wav("conversations/ai.wav")
        mp3_filename = "conversations/ai.mp3"
        os.makedirs(os.path.dirname(mp3_filename), exist_ok=True)
        audio.export(mp3_filename, format="mp3")
        print(f"Audio saved as {mp3_filename}")

    def text_to_speech(self, text, output_file, voice: str):
        client = OpenAI()
        response = client.audio.speech.create(model="tts-1", voice=voice, input=text)
        if os.path.exists(output_file):
            os.remove(output_file)
        response.stream_to_file(output_file)
        return output_file


class MyAITalking:
    def __init__(self, avatar_canvas, character_name, threshold):
        self.avatar_canvas = avatar_canvas
        self.character_name = character_name
        self.threshold = threshold
        self.is_playing = False

        # pygame.mixer.init()

        # Thread-related attributes
        self.play_thread = None
        self.update_thread = None
        self.stop_event = threading.Event()  # Event to signal threads to stop

    def play_audio(self, audio_file):
        """Play the given MP3 file using pygame mixer in a background thread"""
        self.is_playing = True
        self.audio_file = audio_file

        # Load the full audio file for segment analysis
        self.audio_segment = AudioSegment.from_mp3(audio_file)
        self.audio_samples = np.array(self.audio_segment.get_array_of_samples())
        self.sample_rate = self.audio_segment.frame_rate

        print("--------- ME-----------")
        if platform.system() == "Darwin":
            pygame.mixer.init(devicename="MacBook Pro Speakers")
        else:
            pygame.mixer.init()
        pygame.mixer.music.load(self.audio_file)
        pygame.mixer.music.play()
        print("--------- ME-----------")

        # Start a separate thread to update avatar based on real-time audio analysis
        update_thread = threading.Thread(target=self._update_avatar)
        update_thread.start()

        print("--------- ME-----------")

    def _update_avatar(self):
        """Continuously update avatar image based on real-time audio levels"""
        # Define segment duration in seconds (0.1 sec = 100 ms)
        segment_duration_sec = 0.2

        # Calculate the number of samples for each segment (100 ms)
        segment_samples = int(self.sample_rate * segment_duration_sec)

        while pygame.mixer.music.get_busy() and self.is_playing:
            # Get the current playback position in milliseconds
            current_position = pygame.mixer.music.get_pos()

            # Convert current position (ms) to the corresponding sample index
            sample_index = int((current_position / 1000.0) * self.sample_rate)

            # Extract a short segment (100 ms) of the current audio sample for analysis
            current_samples = self.audio_samples[
                sample_index : sample_index + segment_samples
            ]

            # Calculate volume level (RMS or peak) of the current chunk
            if len(current_samples) > 0:
                try:
                    volume = np.sqrt(np.mean(current_samples**2))
                except Exception as e:
                    print(f"Sqrt sussy: {e}")
            else:
                volume = 0

            # Debugging output (optional)
            # print(f"Debug: Position {current_position} ms, Sample index {sample_index}")
            # print(f"Debug: Current volume level: {volume}")

            # Update the avatar image based on the analyzed volume
            self.update_avatar(volume)

            time.sleep(0.2)  # Analyze every 100 ms
        self.stop_playing()

    def update_avatar(self, volume):
        """Update the avatar image based on the current volume"""
        if math.isnan(volume):
            state = "idle"
        else:
            if volume < self.threshold:
                state = "idle"
            else:
                state = "active"

        character_images = {
            "idle": f"assets/characters/{self.character_name}/idle.png",
            "active": f"assets/characters/{self.character_name}/active.png",
        }
        # print(character_images)
        # print(f"Debug: {state}")

        image_path = character_images.get(state)
        if os.path.exists(image_path):
            # print("It exists")
            image = PIL.Image.open(image_path)
            photo = PIL.ImageTk.PhotoImage(image)
            self.avatar_canvas.delete("all")
            self.avatar_canvas.create_image(0, 0, image=photo, anchor=tk.NW)
            self.avatar_canvas.image = (
                photo  # Keep a reference to avoid garbage collection
            )

    def stop_playing(self):
        """Stop playing audio and update avatar"""
        if self.is_playing:
            self.is_playing = False
            self.stop_event.set()  # Signal both threads to stop

            # Wait for both threads to finish
            if self.play_thread:
                self.play_thread.join()

            if self.update_thread:
                self.update_thread.join()

            pygame.mixer.music.stop()  # Stop the music
            pygame.mixer.quit()
            print("Stopped audio and threads.")
