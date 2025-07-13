import tkinter as tk
import socketio
import threading
import time
import pyaudio
import wave
import os
import io
import base64
from pydub import AudioSegment
from pydub.playback import play


class Client:
    """
    Client that handles sync events and audio streaming for the jam session.
    Focuses on: pause/play, skip, add to queue, play from queue, audio streaming
    """

    def __init__(self, root):
        self.root = root
        self.sio = socketio.Client()
        self.connected = False
        self.room_code = None
        self.username = None
        self.color = None
        self.is_host = False

        # Audio streaming state
        self.is_playing = False
        self.current_song_index = -1
        self.queue = []
        self.audio_stream = None
        self.audio_thread = None
        self.audio_stop_event = threading.Event()
        self.current_position = 0
        self.song_duration = 0
        self.current_song_path = None

        # Thread safety
        self.socket_lock = threading.Lock()
        self.audio_lock = threading.Lock()

        # UI component references
        self.queue_ui = None
        self.audio_player = None

        # Set up socket event handlers
        self.setup_socket_handlers()

    def setup_socket_handlers(self):
        """Set up socket.io event handlers for real-time communication."""

        @self.sio.event
        def connect():
            print("[CLIENT] Connected to server")
            self.connected = True

        @self.sio.event
        def disconnect():
            print("[CLIENT] Disconnected from server")
            self.connected = False

        @self.sio.event
        def room_created(data):
            """Called when a room is successfully created."""
            self.room_code = data.get("room_code")
            print(f"Room created with code: {self.room_code}")

        @self.sio.event
        def room_joined(data):
            """Called when successfully joining a room."""
            print(f"Joined room: {data.get('room_code')}")

            # Get initial state
            players_data = data.get("players", [])
            if players_data:
                self.root.after(100, lambda: self.update_players(players_data))

        @self.sio.event
        def user_joined(data):
            """Called when a new user joins the room."""
            username = data.get("username")
            color_idx = data.get("color_idx")
            position_idx = data.get("position_idx")
            print(
                f"User {username} joined with color {color_idx} at position {position_idx}"
            )
            self.add_player(username, color_idx, position_idx)

        @self.sio.event
        def user_left(data):
            """Called when a user leaves the room."""
            username = data.get("username")
            print(f"User {username} left the room")
            self.remove_player(username)

        @self.sio.event
        def players_updated(data):
            """Called when the player list is updated."""
            players_data = data.get("players", [])
            self.root.after(100, lambda: self.update_players(players_data))

        @self.sio.event
        def url_processing(data):
            """Called when a URL is being processed by the server."""
            message = data.get("message", "Processing URL...")
            print(f"URL processing: {message}")
            self.set_downloading_state()

        @self.sio.event
        def url_processed(data):
            """Called when a URL has been processed by the server."""
            status = data.get("status")
            message = data.get("message", "")
            print(f"URL processed - Status: {status}, Message: {message}")
            self.reset_add_button_state()

        @self.sio.event
        def sync_event(data):
            """Main sync event - handles all sync operations."""
            event_type = data.get("type")
            event_data = data.get("data", {})
            updated_by = data.get("updated_by")

            print(f"[CLIENT] Received sync event: {event_type} from {updated_by}")

            if event_type == "queue_updated":
                self.queue = event_data.get("queue", [])
                self.update_queue_ui()

                # Auto-play first song if queue was empty and now has songs
                if len(self.queue) > 0 and self.current_song_index < 0:
                    self.play_song(0)

            elif event_type == "play_state_changed":
                new_playing_state = event_data.get("is_playing", False)
                new_song_index = event_data.get("song_index", -1)

                # Handle play state change
                if new_playing_state != self.is_playing:
                    if new_playing_state:
                        self.resume_audio()
                    else:
                        self.pause_audio()

                # Handle song change
                if new_song_index != self.current_song_index:
                    self.current_song_index = new_song_index
                    if new_song_index >= 0 and new_song_index < len(self.queue):
                        self.load_and_play_song(self.queue[new_song_index])

                self.is_playing = new_playing_state
                self.update_play_state_ui()

            elif event_type == "song_changed":
                new_song_index = event_data.get("song_index", -1)
                if new_song_index != self.current_song_index:
                    self.current_song_index = new_song_index
                    if new_song_index >= 0 and new_song_index < len(self.queue):
                        self.load_and_play_song(self.queue[new_song_index])
                    self.update_song_ui()

    def create_room(self, username, color):
        """Create a new jam room as host."""
        with self.socket_lock:
            if not self.connected:
                print("Not connected to server")
                return False

            self.username = username
            self.color = color
            self.is_host = True

            print(
                f"Creating room with username: {username}, color_idx: {color.color_index}"
            )
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

    def connect_to_server(self, server_url="http://localhost:5000"):
        """Connect to the socket server."""
        try:
            self.sio.connect(server_url, wait_timeout=10)
            return True
        except Exception as e:
            print(f"Failed to connect to server: {e}")
            return False

    # Audio Streaming Methods
    def load_and_play_song(self, song_metadata):
        """Load a song and start playing it."""
        with self.audio_lock:
            # Stop current audio
            self.stop_audio()

            # Get song filepath
            song_path = song_metadata.get("filepath")
            if not song_path or not os.path.exists(song_path):
                print(f"Song file not found: {song_path}")
                return

            self.current_song_path = song_path

            # Get song duration
            try:
                audio = AudioSegment.from_mp3(song_path)
                self.song_duration = len(audio) / 1000.0  # Convert to seconds
            except Exception as e:
                print(f"Error loading audio: {e}")
                self.song_duration = 0

            # Start playing
            self.start_audio_stream(song_path)

            # Update UI
            self.update_song_ui()

    def start_audio_stream(self, song_path):
        """Start audio streaming in a separate thread."""
        if self.audio_thread and self.audio_thread.is_alive():
            self.audio_stop_event.set()
            self.audio_thread.join()

        self.audio_stop_event.clear()
        self.audio_stream = None  # Will be set in the worker thread
        self.audio_thread = threading.Thread(
            target=self._audio_stream_worker, args=(song_path,)
        )
        self.audio_thread.daemon = True
        self.audio_thread.start()

    def _audio_stream_worker(self, song_path):
        """Worker thread for audio streaming."""
        try:
            # Load audio using pydub
            audio = AudioSegment.from_mp3(song_path)

            # Initialize PyAudio
            p = pyaudio.PyAudio()

            # Open stream
            stream = p.open(
                format=pyaudio.paInt16,
                channels=audio.channels,
                rate=audio.frame_rate,
                output=True,
            )
            self.audio_stream = stream

            # Convert audio to raw data
            raw_data = audio.raw_data

            # Play audio in chunks
            chunk_size = 1024 * 4  # Larger chunks for better performance
            self.current_position = 0

            for i in range(0, len(raw_data), chunk_size):
                if self.audio_stop_event.is_set():
                    break

                chunk = raw_data[i : i + chunk_size]
                if chunk:
                    stream.write(chunk)
                    self.current_position += len(chunk) / (
                        audio.frame_rate * audio.channels * 2
                    )  # 2 bytes per sample

                    # Update progress bar periodically
                    if i % (chunk_size * 10) == 0:  # Update every 10 chunks
                        if self.audio_player:
                            try:
                                self.root.after(0, self.audio_player.update_progress)
                            except AttributeError:
                                pass  # audio_player doesn't have update_progress method

            stream.close()
            p.terminate()

        except Exception as e:
            print(f"Audio streaming error: {e}")

    def pause_audio(self):
        """Pause the current audio stream."""
        with self.audio_lock:
            self.audio_stop_event.set()
            if self.audio_stream:
                self.audio_stream.stop_stream()
                self.audio_stream.close()
                self.audio_stream = None

    def resume_audio(self):
        """Resume the current audio stream."""
        with self.audio_lock:
            if self.current_song_path and os.path.exists(self.current_song_path):
                self.audio_stop_event.clear()
                self.start_audio_stream(self.current_song_path)

    def stop_audio(self):
        """Stop the current audio stream."""
        with self.audio_lock:
            self.audio_stop_event.set()
            if self.audio_stream:
                self.audio_stream.stop_stream()
                self.audio_stream.close()
                self.audio_stream = None
            if self.audio_thread and self.audio_thread.is_alive():
                self.audio_thread.join()

    def seek_audio(self, position):
        """Seek to a specific position in the current song."""
        # This is a simplified seek - in a real implementation you'd need to
        # handle seeking within the audio stream more carefully
        self.current_position = position
        if self.is_playing and self.current_song_path:
            self.stop_audio()
            self.start_audio_stream(self.current_song_path)

    # Sync Event Methods - These are the main actions users can take
    def add_url_to_queue(self, url):
        """Add a URL to the queue."""
        if self.connected and self.room_code:
            self.sio.emit("add_url_to_queue", {"room_code": self.room_code, "url": url})

    def toggle_play(self):
        """Toggle play/pause state."""
        if self.connected and self.room_code:
            new_state = not self.is_playing
            self.sio.emit(
                "sync_event",
                {
                    "room_code": self.room_code,
                    "type": "play_state_changed",
                    "data": {
                        "is_playing": new_state,
                        "song_index": self.current_song_index,
                    },
                },
            )

    def play_song(self, song_index):
        """Play a specific song from the queue."""
        if self.connected and self.room_code and 0 <= song_index < len(self.queue):
            self.sio.emit(
                "sync_event",
                {
                    "room_code": self.room_code,
                    "type": "song_changed",
                    "data": {"song_index": song_index},
                },
            )

    def next_song(self):
        """Play the next song in the queue."""
        if self.current_song_index + 1 < len(self.queue):
            self.play_song(self.current_song_index + 1)

    def prev_song(self):
        """Play the previous song in the queue."""
        if self.current_song_index - 1 >= 0:
            self.play_song(self.current_song_index - 1)

    def remove_song_from_queue(self, index):
        """Remove a song from the queue."""
        if self.connected and self.room_code and 0 <= index < len(self.queue):
            new_queue = self.queue.copy()
            del new_queue[index]
            self.sio.emit(
                "sync_event",
                {
                    "room_code": self.room_code,
                    "type": "queue_updated",
                    "data": {"queue": new_queue},
                },
            )

    def shuffle_queue(self):
        """Shuffle the queue."""
        if self.connected and self.room_code and len(self.queue) > 1:
            import random

            new_queue = self.queue.copy()
            # Keep current song at the front
            if self.current_song_index >= 0:
                current_song = new_queue[self.current_song_index]
                remaining_songs = [
                    s for i, s in enumerate(new_queue) if i != self.current_song_index
                ]
                random.shuffle(remaining_songs)
                new_queue = [current_song] + remaining_songs
            else:
                random.shuffle(new_queue)

            self.sio.emit(
                "sync_event",
                {
                    "room_code": self.room_code,
                    "type": "queue_updated",
                    "data": {"queue": new_queue},
                },
            )

    # UI Component Registration Methods
    def register_queue_ui(self, queue_ui):
        """Register the queue UI component with the client."""
        self.queue_ui = queue_ui

    def register_audio_player(self, audio_player):
        """Register the audio player component with the client."""
        self.audio_player = audio_player

    # UI Update Methods - These will be called by the UI components
    def update_queue_ui(self):
        """Update the queue UI."""
        if self.queue_ui:
            self.queue_ui.display_queue()

    def update_play_state_ui(self):
        """Update the play/pause button UI."""
        if self.audio_player and hasattr(self.audio_player, "play_btn"):
            self.audio_player.play_btn.config(text="⏸️" if self.is_playing else "▶")

    def update_song_ui(self):
        """Update the current song display."""
        if self.audio_player and 0 <= self.current_song_index < len(self.queue):
            song = self.queue[self.current_song_index]
            self.audio_player.load_song_metadata(song)

    def set_downloading_state(self):
        """Set the add button to downloading state."""
        if self.queue_ui:
            self.queue_ui.set_downloading_state()

    def reset_add_button_state(self):
        """Reset the add button to normal state."""
        if self.queue_ui:
            self.queue_ui.reset_add_button_state()

    # Player Management Methods
    def add_player(self, username, color_idx, position_idx):
        """Add a player to the room."""
        if self.audio_player:
            self.audio_player.add_player(username, color_idx, position_idx)

    def remove_player(self, username):
        """Remove a player from the room."""
        if self.audio_player:
            self.audio_player.remove_player(username)

    def update_players(self, players_data):
        """Update all players based on server data."""
        if self.audio_player:
            self.audio_player.update_players(players_data)

    def is_connected(self):
        """Check if connected to server."""
        return self.connected

    def get_current_position(self):
        """Get current playback position."""
        return self.current_position

    def get_song_duration(self):
        """Get current song duration."""
        return self.song_duration
