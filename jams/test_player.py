"""Run: uv run python -m jams.test_player"""

import contextlib
import io
import os
import shutil
import tempfile
import time
import wave
from pathlib import Path
from unittest import mock

import numpy as np

from jams.player import RATE, Player, decode

FIRE = {"id": "aaaaaaaaaaa", "file": "aaaaaaaaaaa.mp3", "duration_ms": 8098}
HUM = {"id": "bbbbbbbbbbb", "file": "bbbbbbbbbbb.wav", "duration_ms": 1000}
NEXT = {"id": "ccccccccccc", "file": "ccccccccccc.mp3", "duration_ms": 8098}


def state(track, playing=True, ms=0, queue=()):
    return dict(track=track, is_playing=playing, progress_ms=ms, queue=list(queue))


def write_hum(path):
    """1 s of a steady 1000 in both channels, at half the player's rate."""
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(RATE // 2)
        w.writeframes(np.full((RATE // 2, 2), 1000, np.int16).tobytes())


def pull(player, frames=1024):
    """The next block the speakers would get."""
    out = np.ones((frames, 2), np.int16)  # junk the callback has to overwrite
    player._callback(out, frames, None, None)
    return out


def test_decode():
    fire = decode("assets/fire-sound.mp3")
    assert fire.dtype == np.int16 and fire.shape[1] == 2
    assert abs(len(fire) / RATE - 8.1) < 0.05  # the clip's 8.1 s at 44100 Hz
    with tempfile.TemporaryDirectory() as folder:
        write_hum(os.path.join(folder, HUM["file"]))
        hum = decode(os.path.join(folder, HUM["file"]))
    assert hum.shape == (RATE, 2) and (hum == 1000).all()  # 22050 Hz became 44100


def test_sync():
    with tempfile.TemporaryDirectory() as folder:
        shutil.copy("assets/fire-sound.mp3", os.path.join(folder, FIRE["file"]))
        write_hum(os.path.join(folder, HUM["file"]))
        player = Player("http://unused", folder, speakers=False)  # both cached

        player.sync(state(FIRE, ms=1000), received_at=time.time() - 0.5)
        assert player.file == FIRE["file"] and abs(player.pos / RATE - 1.5) < 0.05
        start = player.pos
        assert pull(player).any() and player.pos == start + 1024  # playing moves on

        player.sync(state(FIRE, False, round(player.pos / RATE * 1000)), time.time())
        here = player.pos
        assert here == start + 1024 and not pull(player).any() and player.pos == here

        player.sync(state(FIRE, False, round(here / RATE * 1000) + 100), time.time())
        assert player.pos == here  # 0.1 s off isn't worth a skip
        player.sync(state(FIRE, False, 5000), time.time())
        assert player.pos == 5 * RATE  # far off: seek

        player.sync(state(HUM, True, 500), time.time())
        assert player.file == HUM["file"] and (pull(player) == 1000).all()  # new song

        player.sync(state(None, False), time.time())
        assert player.file is None and not pull(player).any()  # nothing to play


def test_next_song():
    with tempfile.TemporaryDirectory() as host, tempfile.TemporaryDirectory() as folder:
        os.mkdir(os.path.join(host, "audio"))
        shutil.copy("assets/fire-sound.mp3", os.path.join(host, "audio", NEXT["file"]))
        shutil.copy("assets/fire-sound.mp3", os.path.join(folder, FIRE["file"]))
        player = Player(Path(host).as_uri(), folder, speakers=False)  # file:// as host

        with mock.patch("jams.player.decode", wraps=decode) as spy:
            for playing in (True, False, True):  # pause, play: same queue each time
                player.sync(state(FIRE, playing, queue=[NEXT]), time.time())
            deadline = time.time() + 5
            while player.ahead[1] is None:  # downloaded and decoded in the background
                assert time.time() < deadline, "the next song never got ready"
                time.sleep(0.01)
            ready = player.ahead[1]
            player.sync(state(FIRE, queue=[NEXT]), time.time())
            player.sync(state(NEXT), time.time())  # FIRE ended
            decoded = [os.path.basename(c.args[0]) for c in spy.call_args_list]
        assert decoded == [FIRE["file"], NEXT["file"]]  # NEXT just once, ahead of time
        assert player.file == NEXT["file"] and player.audio is ready  # swapped in
        assert sorted(os.listdir(folder)) == [FIRE["file"], NEXT["file"]]  # no .part

        with contextlib.redirect_stdout(io.StringIO()) as out:
            player.sync(state({**NEXT, "file": "ddddddddddd.mp3"}), time.time())
        assert "Can't play" in out.getvalue() and not pull(player).any()  # not on host

        try:
            player.fetch("../evil.mp3")  # file names come from the host
            raise AssertionError("expected ValueError")
        except ValueError:
            pass


if __name__ == "__main__":
    test_decode()
    test_sync()
    test_next_song()
    print("ok")
