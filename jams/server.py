import socketio
import eventlet
from eventlet import wsgi
import itertools
import os
import re
import threading
import time
from concurrent.futures import Future
from typing import Dict
import sys

sys.path.append(".")
from jams import music
from jams.jam import Jam
from jams.room_code import code_for, lan_ip
from screens.constants import DOWNLOADS_FOLDER, LOCAL_PORT

AUDIO_RE = re.compile(r"/audio/([A-Za-z0-9_-]{11}\.[a-z0-9]{2,5})")  # never a path


def off_loop(fn, *args):
    """Run a slow call on its own thread while the event loop keeps serving everyone else."""
    future = Future()

    def work():
        try:
            future.set_result(fn(*args))
        except Exception as e:
            future.set_exception(e)

    threading.Thread(target=work, daemon=True).start()
    while not future.done():
        eventlet.sleep(0.1)
    return future.result()


class JamServer:
    """
    Server class that manages the state of jam sessions/parties.
    Handles room creation and user management, and owns each room's playback
    (jams/jam.py): anyone in a room sends commands, everyone gets the new state.
    """

    def __init__(self):
        self.sio = socketio.Server(cors_allowed_origins="*")
        self.app = socketio.WSGIApp(self.sio, wsgi_app=self.serve_audio)

        # Store room data: {room_code: {users: [], host: sid, jam: Jam}}
        self.rooms: Dict[str, Dict] = {}
        self.seq = itertools.count(1)  # orders broadcasts: clients drop late, older ones

        # Set up socket event handlers
        self.setup_socket_handlers()

    def setup_socket_handlers(self):
        """Set up socket.io event handlers for the server."""

        @self.sio.event
        def connect(sid, environ):
            print(f"Client connected: {sid}")

        @self.sio.event
        def disconnect(sid):
            print(f"Client disconnected: {sid}")
            # Remove user from their room
            self.remove_user_from_room(sid)

        @self.sio.event
        def create_room(sid, data):
            """Create a new jam room."""
            username = data.get("username")
            color_idx = data.get("color_idx")

            # Generate unique room code
            room_code = self.generate_room_code()

            # Create room with host at position 0
            self.rooms[room_code] = {
                "users": [
                    {
                        "sid": sid,
                        "username": username,
                        "color_idx": color_idx,
                        "position": 0,
                    }
                ],
                "host": sid,
                "jam": Jam(),
            }

            # Join the room
            self.sio.enter_room(sid, room_code)

            print(f"Room created: {room_code} by {username}")

            # Send room code back to host
            self.sio.emit("room_created", {"room_code": room_code}, to=sid)

            # Send initial players list to host
            self.broadcast_players_update(room_code)

        @self.sio.event
        def join_room(sid, data):
            """Join an existing jam room."""
            room_code = data.get("room_code")
            username = data.get("username")
            color_idx = data.get("color_idx")

            if room_code not in self.rooms:
                self.sio.emit("error", {"message": "Room not found"}, room=sid)
                return

            # Find next available position
            existing_positions = [
                user.get("position", 0) for user in self.rooms[room_code]["users"]
            ]
            available_positions = [0, 1, 2, 3]  # 4 positions available
            for pos in existing_positions:
                if pos in available_positions:
                    available_positions.remove(pos)

            new_position = available_positions[0] if available_positions else 0

            # Add user to room with position
            self.rooms[room_code]["users"].append(
                {
                    "sid": sid,
                    "username": username,
                    "color_idx": color_idx,
                    "position": new_position,
                }
            )

            # Join the room
            self.sio.enter_room(sid, room_code)

            print(f"User {username} joined room {room_code} at position {new_position}")

            # Notify all users in the room
            self.sio.emit(
                "user_joined",
                {
                    "username": username,
                    "color_idx": color_idx,
                    "position_idx": new_position,
                },
                room=room_code,
            )

            # Send players and what's playing to the new user
            self.sio.emit(
                "room_joined",
                {"room_code": room_code, "players": self.players_data(room_code)},
                room=sid,
            )
            self.broadcast_jam(room_code, to=sid)

        @self.sio.event
        def jam_cmd(sid, data):
            """Change a room's playback, then show everyone. Returns an error for the sender, if any."""
            room_code = data.get("room_code")
            if room_code not in self.rooms:
                return "Room not found"
            jam = self.rooms[room_code]["jam"]
            action = data.get("action")
            try:
                if action == "add":
                    # Finding and fetching a song takes seconds: keep it off the event loop
                    track = off_loop(music.fetch, str(data.get("text", "")))
                    jam.add(track, time.time())
                elif action == "add_many":
                    texts = data.get("texts")
                    if not (
                        isinstance(texts, list)
                        and 1 <= len(texts) <= 100
                        and all(isinstance(text, str) for text in texts)
                    ):
                        return "Add 1 to 100 songs at a time"
                    eventlet.spawn(self.add_many, room_code, jam, texts)
                    return  # each song is broadcast as it lands
                elif action in ("play", "pause", "next", "previous"):
                    getattr(jam, action)(time.time())
                elif action == "seek":
                    jam.seek(data["position_ms"], time.time())
                elif action == "jump":
                    jam.jump(data["key"], time.time())
                elif action == "remove":
                    jam.remove(data["key"])
                elif action == "move":
                    jam.move(data["key"], data["index"])
                elif action == "shuffle":
                    jam.shuffle()
                else:
                    return f"Unknown command: {action}"
            except Exception as e:
                return str(e)
            self.broadcast_jam(room_code)

        @self.sio.event
        def playlist(sid, data):
            """A playlist link's songs, for the sender to pick from: {title, tracks} or {error}."""
            if data.get("room_code") not in self.rooms:
                return {"error": "Room not found"}
            try:
                return off_loop(music.playlist, str(data.get("text", "")))
            except Exception as e:
                return {"error": str(e)}

        @self.sio.event
        def user_talking_state(sid, data):
            """Handle user talking state updates and broadcast to room."""
            room_code = data.get("room_code")
            username = data.get("username")
            is_talking = bool(data.get("is_talking", 0))
            if not room_code or not username:
                return
            # Broadcast to all users in the room
            self.sio.emit(
                "user_talking_update",
                {"username": username, "is_talking": is_talking},
                room=room_code,
            )

    def broadcast_jam(self, room_code: str, to=None):
        """Send a room's playback to everyone in it (or just `to`)."""
        if room_code in self.rooms:
            state = self.rooms[room_code]["jam"].state(time.time())
            state["seq"] = next(self.seq)
            self.sio.emit("jam_state", state, room=to or room_code)

    def add_many(self, room_code: str, jam: Jam, texts):
        """Fetch songs one at a time, in order, showing the room each one as it lands."""
        # ponytail: imports run side by side and aren't limited, like spammed adds;
        # queue them per room if friends' imports start hogging the host
        for text in texts:
            try:
                track = off_loop(music.fetch, text)
            except Exception as e:
                track = None
                print(f"Skipped {text[:100]!a}: {e!a}")  # ascii: any console can print it
            if self.rooms.get(room_code, {}).get("jam") is not jam:
                return  # the room closed (its code may be a new room's by now)
            if track:
                jam.add(track, time.time())
                self.broadcast_jam(room_code)

    def serve_audio(self, environ, start_response):
        """Hand friends' apps the song files this host fetched (see jams/music.py)."""
        match = AUDIO_RE.fullmatch(environ.get("PATH_INFO", ""))
        path = match and os.path.join(DOWNLOADS_FOLDER, match.group(1))
        if not path or not os.path.isfile(path):
            start_response("404 Not Found", [("Content-Type", "text/plain")])
            return [b"Not Found"]
        start_response("200 OK", [("Content-Type", "application/octet-stream")])
        with open(path, "rb") as f:
            return [f.read()]

    def tick_rooms(self):
        """Start each room's next song when the current one ends."""
        while True:
            eventlet.sleep(0.5)
            for room_code in list(self.rooms):
                room = self.rooms.get(room_code)
                if room and room["jam"].tick(time.time()):
                    self.broadcast_jam(room_code)

    def generate_room_code(self) -> str:
        """The host's join code: this computer's address, so friends' apps can find it."""
        return code_for(lan_ip())  # one room per host: each host runs its own server

    def remove_user_from_room(self, sid: str):
        """Remove a user from their room when they disconnect."""
        for room_code, room_data in self.rooms.items():
            for user in room_data["users"]:
                if user["sid"] == sid:
                    username = user["username"]
                    room_data["users"].remove(user)

                    # If no users left, delete the room
                    if not room_data["users"]:
                        del self.rooms[room_code]
                        print(f"Room {room_code} deleted (no users left)")
                    else:
                        # If host left, assign new host
                        if room_data["host"] == sid:
                            room_data["host"] = room_data["users"][0]["sid"]

                        # Notify remaining users
                        self.sio.emit(
                            "user_left", {"username": username}, room=room_code
                        )

                        # Broadcast updated players list
                        self.broadcast_players_update(room_code)

                    print(f"User {username} removed from room {room_code}")
                    return

    def players_data(self, room_code: str):
        """Who sits where around the fire."""
        return [
            {
                "username": user["username"],
                "color_idx": user["color_idx"],
                "position": user.get("position", 0),
            }
            for user in self.rooms[room_code]["users"]
        ]

    def broadcast_players_update(self, room_code: str):
        """Broadcast the current players list to all users in a room."""
        if room_code in self.rooms:
            players_data = self.players_data(room_code)
            self.sio.emit("players_updated", {"players": players_data}, room=room_code)
            print(f"Broadcasted players update for room {room_code}: {players_data}")

    def run(self, host="0.0.0.0", port=None):
        """Start the server."""
        if port is None:
            port = LOCAL_PORT
        ip = lan_ip()

        print(f"Starting Jam Server on {host}:{port}")
        print(f"[INFO] Friends on this network join with code {code_for(ip)} ({ip}:{port})")

        # Start Socket.IO server
        eventlet.spawn(self.tick_rooms)
        wsgi.server(eventlet.listen((host, port)), self.app, log_output=False)


if __name__ == "__main__":
    server = JamServer()
    server.run()
