"""
Each app plays the jam on its own speakers. sync() follows every state the server
broadcasts (see Jam.state in jams/jam.py): it loads each song, decoding the next one
ahead of time, and seeks or pauses to stay with everyone; a sounddevice callback does
the playing.
"""

import os
import re
import shutil
import threading
import time
import urllib.request

import av
import numpy as np
import sounddevice as sd

from screens.constants import DOWNLOADS_FOLDER

RATE = 44100
SILENCE = np.zeros((0, 2), np.int16)
SONG_FILE = re.compile(r"[A-Za-z0-9_-]{11}\.[a-z0-9]{2,5}")  # what /audio/ serves


def decode(path, rate=RATE):
    """A song's audio as (frames, 2) int16 samples."""
    rs = av.AudioResampler(format="s16", layout="stereo", rate=rate)
    with av.open(path) as c:
        chunks = [f.to_ndarray() for fr in c.decode(audio=0) for f in rs.resample(fr)]
    chunks += [f.to_ndarray() for f in rs.resample(None)]  # flush
    return np.concatenate(chunks, axis=1).reshape(-1, 2)


class Player:
    """Plays the jam's current song on this computer, in step with everyone else."""

    def __init__(self, server_url, folder=DOWNLOADS_FOLDER, speakers=True):
        self.server_url = server_url
        self.folder = folder
        self.file = None  # the song in self.audio
        self.audio = SILENCE
        self.pos = 0  # next frame for the speakers
        self.playing = False
        self.lock = threading.Lock()  # guards audio/pos/playing for the audio thread
        self.ahead = [None, None]  # [file, audio] of the next song, audio once decoded
        self.fetching = {}  # file -> lock, so a song never downloads twice at once
        self.stream = None
        if speakers:  # tests leave this off and pull samples from _callback themselves
            try:
                self.stream = sd.OutputStream(
                    RATE, channels=2, dtype="int16", callback=self._callback
                )
                self.stream.start()
            except Exception as e:
                print(f"[PLAYER] No speakers, so the jam stays silent here: {e}")

    def sync(self, state, received_at):
        """Play what the jam says. Blocks while a new song downloads and decodes."""
        track, playing = state["track"], state["is_playing"]
        file = track["file"] if track else None
        changed = file != self.file
        if changed:
            with self.lock:
                self.playing = False  # the old song stops while the new one loads
            ahead_file, audio = self.ahead
            if file != ahead_file or audio is None:  # not decoded ahead (yet)
                try:
                    audio = decode(self.fetch(file)) if file else SILENCE
                except Exception as e:
                    print(f"[PLAYER] Can't play {file}: {e}")
                    return  # silence until a later state tries again
            self.file = file
        elapsed = time.time() - received_at if playing else 0  # including any load time
        frame = max(0, int((state["progress_ms"] / 1000 + elapsed) * RATE))
        with self.lock:
            if changed:
                self.audio = audio
            if changed or abs(self.pos - frame) > RATE / 4:  # ignore small drift
                self.pos = frame
            self.playing = playing
        up_next = state["queue"][0]["file"] if state["queue"] else None
        if up_next and up_next != self.ahead[0]:  # once per song, however many states
            self.ahead = [up_next, None]  # claimed before the thread starts
            threading.Thread(
                target=self._decode_ahead, args=[self.ahead], daemon=True
            ).start()

    def fetch(self, file):
        """A song's local path, downloaded from the jam's server unless it's cached."""
        if not SONG_FILE.fullmatch(file):  # names come from the host: never a path
            raise ValueError(f"Not a song file: {file!r}")
        path = os.path.join(self.folder, file)
        with self.fetching.setdefault(file, threading.Lock()):
            if not os.path.exists(path):
                os.makedirs(self.folder, exist_ok=True)
                url = f"{self.server_url}/audio/{file}"
                with urllib.request.urlopen(url, timeout=10) as resp:
                    with open(path + ".part", "wb") as f:
                        shutil.copyfileobj(resp, f)
                os.replace(path + ".part", path)  # no half songs in the cache
        return path

    def _decode_ahead(self, ahead):
        """Fill in one claim's audio; a newer claim is a new list, so no clobbering."""
        try:
            ahead[1] = decode(self.fetch(ahead[0]))
        except Exception:
            pass  # sync tries again when the song comes up

    def _callback(self, out, frames, time_info, status):
        """Audio thread: the next `frames` samples of the song, or zeros."""
        with self.lock:
            n = frames if self.playing else 0
            chunk = self.audio[self.pos : self.pos + n]
            self.pos += len(chunk)
        out[: len(chunk)] = chunk
        out[len(chunk) :] = 0
