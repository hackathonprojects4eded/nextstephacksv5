"""Run: uv run python -m jams.test_jam"""

from jams.jam import Jam

A, B, C, D = ({"id": x, "duration_ms": 10_000} for x in "abcd")


def ids(tracks):
    return [t["id"] for t in tracks]


def test_playback():
    jam = Jam()
    jam.add(A, now=0)  # an idle jam starts the first song
    jam.add(B, now=1)
    assert jam.state(5)["track"]["id"] == "a" and jam.state(5)["progress_ms"] == 5000
    jam.pause(5)
    assert jam.state(100)["progress_ms"] == 5000
    jam.play(100)
    jam.seek(9_000, now=100)
    assert jam.tick(100.5) is False
    assert jam.tick(101) is True and jam.track["id"] == "b"  # A ended, B plays
    jam.next(102)
    assert jam.track is None and not jam.is_playing  # ran out of songs
    jam.add(C, now=103)
    assert jam.track["id"] == "c" and jam.is_playing  # adding wakes it up
    jam.previous(104)
    assert jam.track["id"] == "b" and jam.state(104)["progress_ms"] == 0


def test_queue_edits():
    jam = Jam()
    for track in (A, B, C, D):
        jam.add(track, now=0)
    up_next = jam.state(0)["queue"]
    assert ids(up_next) == ["b", "c", "d"]
    jam.remove(up_next[0]["key"])
    assert ids(jam.state(0)["queue"]) == ["c", "d"]
    jam.jump(up_next[2]["key"], now=1)
    assert jam.track["id"] == "d" and jam.state(1)["queue"] == []
    try:
        jam.remove(up_next[0]["key"])  # already gone
        raise AssertionError("expected ValueError")
    except ValueError:
        pass
    jam.previous(2)
    jam.shuffle()
    assert jam.track["id"] == "c" and ids(jam.state(2)["queue"]) == ["d"]


if __name__ == "__main__":
    test_playback()
    test_queue_edits()
    print("ok")
