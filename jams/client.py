import threading
import time
from tkinter import messagebox

import socketio

from jams.player import Player
from screens.audio_player_screen import AudioPlayerScreen
from screens.queue_screen import MAX_PAST_SONGS
from utils.song import fetch_cover


class Client:
    """
    Client class that manages the audio player screen and socket connection.
    The server owns the room's playback (jams/jam.py): this sends it commands
    and plays/renders the state it broadcasts back.
    """

    def __init__(self, root):
        self.root = root
        self.sio = socketio.Client()
        self.connected = False
        self.room_code = None
        self.username = None
        self.color = None
        self.is_host = False
        self.current_screen = None  # Reference to current screen for navigation

        # Thread safety
        self.socket_lock = threading.Lock()

        # Plays the jam on this computer; jam_seq skips updates that arrive late
        self.player = Player(None)  # its server_url is set once we connect
        self.jam_lock = threading.Lock()
        self.jam_seq = 0

        # Initialize audio player screen
        self.audio_player = AudioPlayerScreen(root, client=self)

        # Set up socket event handlers
        self.setup_socket_handlers()

    def setup_socket_handlers(self):
        """Set up socket.io event handlers for real-time communication."""

        @self.sio.event
        def connect():
            print("[CLIENT] Connected to server")
            self.connected = True
            self.jam_seq = 0  # a restarted server counts from 1 again

        @self.sio.event
        def disconnect(sid=None):
            print("[CLIENT] Disconnected from server")
            self.connected = False

        @self.sio.event
        def error(data):
            self.show_error(data.get("message", "Something went wrong"))

        @self.sio.event
        def room_created(data):
            """Called when a room is successfully created."""
            self.room_code = data.get("room_code")
            print(f"Room created with code: {self.room_code}")

        @self.sio.event
        def room_joined(data):
            """Called when successfully joining a room."""
            print(f"Joined room: {data.get('room_code')}")
            players_data = data.get("players", [])
            # Use after to ensure UI is ready
            self.root.after(100, lambda: self.audio_player.update_players(players_data))

        @self.sio.event
        def user_joined(data):
            """Called when a new user joins the room."""
            username = data.get("username")
            color_idx = data.get("color_idx")
            position_idx = data.get("position_idx", len(self.audio_player.players))
            print(
                f"User {username} joined with color {color_idx} at position {position_idx}"
            )

            # Add player to audio player screen
            self.root.after(
                0, lambda: self.audio_player.add_player(username, color_idx, position_idx)
            )

        @self.sio.event
        def user_left(data):
            """Called when a user leaves the room."""
            username = data.get("username")
            print(f"User {username} left the room")

            # Remove player from audio player screen
            self.root.after(0, lambda: self.audio_player.remove_player(username))

        @self.sio.event
        def players_updated(data):
            """Called when the player list is updated."""
            players_data = data.get("players", [])
            self.root.after(100, lambda: self.audio_player.update_players(players_data))

        @self.sio.event
        def jam_state(state):
            """The room's playback changed: what everyone hears and sees."""
            received_at = time.time()
            with self.jam_lock:  # each event runs on its own thread: drop late, older ones
                if state["seq"] <= self.jam_seq:
                    return
                self.jam_seq = state["seq"]
                self.player.sync(state, received_at)  # sound first: it's the part in sync
            for track in filter(None, [state["track"], *state["queue"]]):
                fetch_cover(track["cover_url"])  # download art off the Tk thread
            self.root.after(0, lambda: self.render_if_latest(state, received_at))
            # ponytail: Past Songs opened in the seconds right after joining can still
            # fetch some art on the Tk thread; hand history over only once fetched if it stalls
            for track in state.get("history", [])[-MAX_PAST_SONGS:]:
                fetch_cover(track["cover_url"])  # mostly cached: they were queued once

        @self.sio.event
        def user_talking_update(data):
            """Update a player's talking state in the UI when received from server."""
            username = data.get("username")
            is_talking = bool(data.get("is_talking", 0))
            self.root.after(
                0,
                lambda: self.audio_player.update_remote_talking_state(username, is_talking),
            )

    def create_room(self, username, color):
        """Create a new jam room as host."""
        with self.socket_lock:
            if not self.connected:
                print("Not connected to server")
                return False

            self.username = username
            self.color = color
            self.is_host = True

            self.sio.emit(
                "create_room", {"username": username, "color_idx": color.color_index}
            )
            return True

    def join_room(self, room_code, username, color):
        """Join an existing jam room."""
        with self.socket_lock:
            if not self.connected:
                print("Not connected to server")
                return False

            self.room_code = room_code
            self.username = username
            self.color = color
            self.is_host = False

            self.sio.emit(
                "join_room",
                {
                    "room_code": room_code,
                    "username": username,
                    "color_idx": color.color_index,
                },
            )
            return True

    def connect_to_server(self, server_url):
        """Connect to the socket server."""
        try:
            self.sio.connect(server_url, wait_timeout=10)
            self.player.server_url = server_url  # songs download from the same host
            return True
        except Exception as e:
            print(f"Failed to connect to server: {e}")
            return False

    def render_if_latest(self, state, received_at):
        """Tk thread: show a state unless a newer one has arrived since."""
        if state["seq"] == self.jam_seq:
            self.audio_player.render_state(state, received_at)

    def send_jam(self, action, **data):
        """Ask the server to change the room's playback (see JamServer jam_cmd)."""
        done = lambda error=None: self._jam_cmd_done(error, added=action == "add")
        if self.connected and self.room_code:
            self.sio.emit(
                "jam_cmd",
                {"room_code": self.room_code, "action": action, **data},
                callback=done,
            )
        elif action in ("add", "add_many"):
            done("Host or join a jam first")

    def get_playlist(self, text, callback):
        """Look up a playlist link's songs. callback gets {"title", "tracks"} or {"error"}, on the Tk thread."""

        def done(result=None):
            if not isinstance(result, dict):
                result = {"error": "Couldn't read that playlist"}
            self.root.after(0, lambda: callback(result))

        if self.connected and self.room_code:
            self.sio.emit(
                "playlist", {"room_code": self.room_code, "text": text}, callback=done
            )
        else:
            done({"error": "Host or join a jam first"})

    def _jam_cmd_done(self, error=None, added=False):
        if added:  # the add button shows ⏬ until its own song is in
            self.root.after(0, self.audio_player.reset_add_button_state)
        if error:
            self.show_error(error)

    def show_error(self, message):
        self.root.after(
            0, lambda: messagebox.showwarning("Firejams", message, parent=self.root)
        )

    def is_connected(self):
        """Check if connected to server."""
        return self.connected
