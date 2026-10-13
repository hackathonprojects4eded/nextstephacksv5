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


def test_move():
    jam = Jam()
    for track in (A, B, C, D):
        jam.add(track, now=0)  # A plays; B, C, D are up next
    key = {t["id"]: t["key"] for t in jam.queue}
    up_next = lambda: ids(jam.state(0)["queue"])
    jam.move(key["d"], 0)
    assert up_next() == ["d", "b", "c"]  # to the front: plays next
    jam.move(key["d"], 2)
    assert up_next() == ["b", "c", "d"]  # to the back
    jam.move(key["b"], 99)
    assert up_next() == ["c", "d", "b"]  # past the end: last
    jam.move(key["b"], "-5")  # from the wire: anything int() takes
    assert up_next() == ["b", "c", "d"]  # before the front: first
    jam.move(key["a"], 2)
    assert jam.track["id"] == "a" and up_next() == ["b", "c", "d"]  # playing: stays put
    jam.next(1)
    jam.move(key["a"], 0)
    assert ids(jam.state(1)["history"]) == ["a"] and up_next() == ["c", "d"]  # past: stays put
    for bad_key, bad_index in ((99, 0), (key["c"], "soon")):  # unknown song, junk index
        try:
            jam.move(bad_key, bad_index)
            raise AssertionError("expected ValueError")
        except ValueError:
            pass
    assert jam.track["id"] == "b" and up_next() == ["c", "d"]


def test_history():
    jam = Jam()
    for track in (A, B, C, D):
        jam.add(track, now=0)
    history = lambda now: ids(jam.state(now)["history"])
    assert history(0) == []
    jam.next(1)
    assert history(1) == ["a"]
    jam.seek(10_000, now=1)
    assert jam.tick(1) and history(1) == ["a", "b"]  # B ended
    jam.previous(2)
    assert history(2) == ["a"] and jam.track["id"] == "b"
    jam.jump(jam.state(2)["queue"][-1]["key"], now=3)
    assert history(3) == ["a", "b", "c"] and jam.track["id"] == "d"  # skipped C counts as past
    jam.jump(jam.state(3)["history"][0]["key"], now=4)  # replay a past song
    assert history(4) == [] and ids(jam.state(4)["queue"]) == ["b", "c", "d"]
    jam.jump(jam.state(4)["queue"][-1]["key"], now=5)
    jam.next(6)
    assert history(6) == ["a", "b", "c", "d"] and jam.track is None  # idle: all played
    assert all("key" in t for t in jam.state(6)["history"])


if __name__ == "__main__":
    test_playback()
    test_queue_edits()
    test_move()
    test_history()
    print("ok")
