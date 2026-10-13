"""Run: uv run python -m jams.test_server (offline: fetching songs is mocked)"""

import contextlib
import io
from unittest import mock

import eventlet

from jams.jam import Jam
from jams.server import JamServer

ROOM = "1HGEED4"


def fetch(text):
    """Stands in for music.fetch: a song named after the text, or a song that can't be found."""
    if text == "nope":
        raise ValueError("Couldn't find that song")
    return {"id": text, "duration_ms": 10_000}


def ids(tracks):
    return [t["id"] for t in tracks]


def test_add_many():
    server, jam = JamServer(), Jam()
    server.rooms[ROOM] = {"users": [], "host": "sid", "jam": jam}
    cmd = server.sio.handlers["/"]["jam_cmd"]
    add_many = lambda texts: cmd("sid", {"room_code": ROOM, "action": "add_many", "texts": texts})
    for junk in (None, "a b", [], ["a"] * 101, ["a", 3], {"0": "a"}):
        assert isinstance(add_many(junk), str), junk
    with (
        mock.patch.object(server.sio, "emit") as emit,
        mock.patch("jams.music.fetch", fetch),
        contextlib.redirect_stdout(io.StringIO()) as out,
    ):
        assert add_many(["a", "nope", "b", "c"]) is None  # answers right away
        assert jam.queue == []
        for _ in range(100):  # let the import run on the hub
            if len(jam.queue) == 3:
                break
            eventlet.sleep(0.05)
        assert ids(jam.queue) == ["a", "b", "c"] and "nope" in out.getvalue()
        states = [c.args[1] for c in emit.call_args_list if c.args[0] == "jam_state"]
        assert [ids(s["queue"]) for s in states] == [[], ["b"], ["b", "c"]]  # one per song

        # The room closes and its code comes back for a new room: the import stops
        new_jam = Jam()
        server.rooms[ROOM] = {"users": [], "host": "sid2", "jam": new_jam}
        server.add_many(ROOM, jam, ["d", "e"])
        del server.rooms[ROOM]
        server.add_many(ROOM, jam, ["f"])
    assert ids(jam.queue) == ["a", "b", "c"] and new_jam.queue == []


def test_move_and_playlist():
    server, jam = JamServer(), Jam()
    server.rooms[ROOM] = {"users": [], "host": "sid", "jam": jam}
    for track in map(fetch, "abc"):
        jam.add(track, now=0)
    cmd, playlist = server.sio.handlers["/"]["jam_cmd"], server.sio.handlers["/"]["playlist"]
    key = jam.queue[2]["key"]  # C
    move = lambda index: cmd("sid", {"room_code": ROOM, "action": "move", "key": key, "index": index})
    with mock.patch.object(server.sio, "emit"):
        assert move("soon") and move(None) and move([1])  # junk index: an error for the sender
        assert move(0) is None and ids(jam.queue) == ["a", "c", "b"]
        assert playlist("sid", {"room_code": "NOPE", "text": "x"}) == {"error": "Room not found"}
        assert playlist("sid", {"room_code": ROOM, "text": "lofi beats"}) == {
            "error": "Paste a YouTube or Spotify playlist link"
        }


if __name__ == "__main__":
    test_add_many()
    test_move_and_playlist()
    print("ok")
