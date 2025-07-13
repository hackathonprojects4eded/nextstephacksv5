import tkinter as tk
from screens.audio_player_screen import AudioPlayerScreen
from jams.shared.song_queue import SongQueue
import socketio
import threading
import pyaudio
import base64
import io
import wave
import time


class Client:
    """
    Client class that manages the audio player screen, queue, and socket connection.
    Handles real-time communication with the server for jam sessions.
    """

    def __init__(self, root, metadata=None):
        self.root = root
        self.metadata = metadata
        self.sio = socketio.Client()
        self.connected = False
        self.room_code = None
        self.username = None
        self.color = None
        self.is_host = False
        self.position = 0  # e.g., -2, -1, 0, 1, 2 (relative to campfire) can't be 0
        self.current_screen = None  # Reference to current screen for navigation
        self._room_joined_processed = (
            False  # Track if room_joined event has been processed
        )

        # Thread safety
        self.socket_lock = threading.Lock()

        # Queue tracking
        self.previous_queue_length = (
            0  # Track previous queue length for auto-play detection
        )

        # Audio streaming settings
        self.audio_stream = None
        self.pyaudio_player = None
        self.current_audio_chunks = {}
        self.is_streaming = False
        self.sample_rate = 44100
        self.chunk_size = 4096
        self.current_song_index = -1  # Track currently playing song index
        self.starting_new_stream = (
            False  # Flag to prevent stopping stream during startup
        )

        self.rel_position = "L"
        if self.position < 0:
            self.rel_position = "L"
        elif self.position > 0:
            self.rel_position = "R"

        # Initialize audio player screen
        self.audio_player = AudioPlayerScreen(root, metadata=metadata, client=self)

        # Initialize queue manager
        self.queue_manager = self.audio_player.queue_manager

        # Set up socket event handlers
        self.setup_socket_handlers()

    def setup_socket_handlers(self):
        """Set up socket.io event handlers for real-time communication."""

        @self.sio.event
        def connect():
            print("[CLIENT] Connected to server")
            self.connected = True

        @self.sio.event
        def disconnect(sid=None):
            print("[CLIENT] Disconnected from server")
            print(
                f"[CLIENT] Disconnect - connected: {self.connected}, room_code: {self.room_code}"
            )
            print(f"[CLIENT] Disconnect - sio.connected: {self.sio.connected}")
            self.connected = False

        @self.sio.event
        def test_response(data):
            """Test response from server."""
            print(f"[CLIENT] Received test response: {data}")

        @self.sio.event
        def room_created(data):
            """Called when a room is successfully created."""
            try:
                self.room_code = data.get("room_code")
                print(f"Room created with code: {self.room_code}")
                print(f"Room created data: {data}")
                # Trigger the room_created event for any UI listeners
                if hasattr(self, "sio"):
                    self.sio.emit("room_created", data)
            except Exception as e:
                print(f"[CLIENT] Error in room_created: {e}")
                import traceback

                traceback.print_exc()

        @self.sio.event
        def room_joined(data):
            """Called when successfully joining a room."""
            try:
                print(f"Joined room: {data.get('room_code')}")
                print(f"Room joined data: {data}")

                # Get initial players list
                players_data = data.get("players", [])
                print(f"Initial players data: {players_data}")
                if players_data:
                    print(f"Updating players with {len(players_data)} players")
                    # Use after to ensure UI is ready
                    self.root.after(
                        100, lambda: self.audio_player.update_players(players_data)
                    )
                else:
                    print("No players data received")
            except Exception as e:
                print(f"[CLIENT] Error in room_joined: {e}")
                import traceback

                traceback.print_exc()

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
            self.audio_player.add_player(username, color_idx, position_idx)

        @self.sio.event
        def user_left(data):
            """Called when a user leaves the room."""
            username = data.get("username")
            print(f"User {username} left the room")

            # Remove player from audio player screen
            self.audio_player.remove_player(username)

        @self.sio.event
        def players_updated(data):
            """Called when the player list is updated."""
            players_data = data.get("players", [])
            print(f"Players updated: {players_data}")

            self.root.after(100, lambda: self.audio_player.update_players(players_data))

        @self.sio.event
        def url_processing(data):
            """Called when a URL is being processed by the server."""
            message = data.get("message", "Processing URL...")
            print(f"URL processing: {message}")
            # Set downloading state in the queue UI
            if hasattr(self.audio_player, "queue_ui") and self.audio_player.queue_ui:
                self.audio_player.queue_ui.set_downloading_state()

        @self.sio.event
        def url_processed(data):
            """Called when a URL has been processed by the server."""
            status = data.get("status")
            message = data.get("message", "")
            # song = data.get("song", {})
            # print(f"Song's Metadata: \n" + str(song))

            print(f"URL processed - Status: {status}, Message: {message}")

            # Reset the add button state regardless of success/failure
            if hasattr(self.audio_player, "queue_ui") and self.audio_player.queue_ui:
                self.audio_player.queue_ui.reset_add_button_state()

        @self.sio.event
        def queue_synced(data):
            """Called when the queue has been synced by another client."""
            new_queue = data.get("queue", [])
            updated_by = data.get("updated_by")

            print(
                f"[CLIENT] Received queue_synced event from {updated_by}: {len(new_queue)} songs (was {self.previous_queue_length})"
            )

            # Update local queue
            self.queue_manager.queue = new_queue
            if hasattr(self.audio_player, "queue_ui") and self.audio_player.queue_ui:
                self.audio_player.queue_ui.display_queue()
                print("Updated UI for synced queue")
            else:
                print("Queue UI not open, queue updated in background")

            # Always auto-play the first song if not already playing
            should_autoplay = False
            if len(new_queue) > 0:
                # If nothing is playing or current_song_index is out of range, auto-play
                if (
                    not self.audio_player.is_playing
                    or self.audio_player.current_song_index < 0
                    or self.audio_player.current_song_index >= len(new_queue)
                ):
                    should_autoplay = True
            if should_autoplay:
                print("[CLIENT] Auto-playing first song from synced queue (force)")
                self.audio_player.play_song_from_queue(0)
            else:
                print(
                    f"[CLIENT] Not auto-playing: is_playing={self.audio_player.is_playing}, current_song_index={self.audio_player.current_song_index}, queue_len={len(new_queue)}"
                )

            self.previous_queue_length = len(new_queue)

        @self.sio.event
        def current_index_synced(data):
            """Called when the current index has been synced by another client."""
            current_idx = data.get("current_idx", 0)
            updated_by = data.get("updated_by")

            print(
                f"[CLIENT] Received current_index_synced event from {updated_by}: index {current_idx}"
            )

            # Update local current index
            if hasattr(self.audio_player, "queue_manager"):
                self.audio_player.queue_manager.current_idx = current_idx
                self.audio_player.current_song_index = current_idx

            # Update UI to show current song
            if hasattr(self.audio_player, "queue_ui") and self.audio_player.queue_ui:
                self.audio_player.queue_ui.display_queue()

        @self.sio.event
        def audio_stream_ready(data):
            """Called when audio stream is ready to start."""
            room_code = data.get("room_code")
            song = data.get("song", {})
            total_chunks = data.get("total_chunks", 0)

            print(f"Audio stream ready for song: {song.get('name', 'Unknown')}")

            # Set flag to prevent stopping stream during startup
            self.starting_new_stream = True

            # Stop any existing audio stream before starting new one
            if self.is_streaming:
                print("Stopping existing audio stream")
                self.stop_audio_stream()

            self.start_audio_stream(room_code, total_chunks)

        @self.sio.event
        def audio_chunk(data):
            """Called when receiving an audio chunk from server."""
            room_code = data.get("room_code")
            chunk_index = data.get("chunk_index")
            audio_data_b64 = data.get("audio_data")

            if audio_data_b64:
                # Decode audio chunk
                audio_chunk = base64.b64decode(audio_data_b64)
                print(
                    f"Received audio chunk {chunk_index}, size: {len(audio_chunk)} bytes"
                )

                # Play the audio chunk immediately
                self.play_audio_chunk(audio_chunk)

                # Store chunk for potential future use
                self.current_audio_chunks[chunk_index] = audio_chunk

                # Request next chunk if streaming
                if self.is_streaming:
                    self.request_next_chunk(room_code, chunk_index + 1)

        @self.sio.event
        def song_started(data):
            """Called when a song starts playing."""
            room_code = data.get("room_code")
            song_index = data.get("song_index")
            song = data.get("song", {})

            print(f"Song started: {song.get('name', 'Unknown')} at index {song_index}")
            print(
                f"Debug - is_streaming: {self.is_streaming}, song_index: {song_index}, current_song_index: {getattr(self, 'current_song_index', -1)}, starting_new_stream: {self.starting_new_stream}"
            )

            # Only stop existing stream if it's a different song and we're already streaming
            # Don't stop if this is the same song that was just started
            current_song_idx = getattr(self, "current_song_index", -1)
            if (
                self.is_streaming
                and song_index != current_song_idx
                and not self.starting_new_stream
            ):
                print("Stopping existing audio stream for new song")
                self.stop_audio_stream()
            elif self.starting_new_stream:
                print("Skipping stream stop - new stream is starting")

            # Update current song index
            self.current_song_index = song_index

            # Also update the audio player's current song index
            if hasattr(self.audio_player, "queue_manager"):
                self.audio_player.queue_manager.current_idx = song_index
                self.audio_player.current_song_index = song_index
                self.audio_player._load_and_play_song(song_index)

            if hasattr(self, "queue_ui") and self.audio_player.queue_ui:
                self.audio_player.queue_ui.display_queue()

            # Clear the starting flag after a short delay to ensure stream is fully established
            self.root.after(2000, lambda: setattr(self, "starting_new_stream", False))

        @self.sio.event
        def stream_paused(data):
            """Called when audio stream is paused."""
            room_code = data.get("room_code")
            song_index = data.get("song_index")
            position = data.get("position", 0)
            print(f"Stream paused for song index: {song_index} at position: {position}")

            # Update audio player state
            if hasattr(self.audio_player, "is_playing"):
                self.audio_player.is_playing = False
                if hasattr(self.audio_player, "play_btn"):
                    self.audio_player.play_btn.config(text="▶")
            if hasattr(self.audio_player, "paused_position"):
                self.audio_player.paused_position = position
            if hasattr(self.audio_player, "stream_start_time"):
                self.audio_player.stream_start_time = None
            if hasattr(self.audio_player, "progress"):
                self.audio_player.progress.set(position)
                if hasattr(self.audio_player, "time_label_start"):
                    self.audio_player.time_label_start.config(
                        text=self.audio_player.format_time(position)
                    )

            # Stop requesting audio chunks when paused
            self.is_streaming = False
            print(f"Stopped requesting audio chunks for room {room_code}")

        @self.sio.event
        def stream_resumed(data):
            """Called when audio stream is resumed."""
            room_code = data.get("room_code")
            song_index = data.get("song_index")
            position = data.get("position", 0)
            print(
                f"Stream resumed for song index: {song_index} at position: {position}"
            )

            # Update audio player state
            if hasattr(self.audio_player, "is_playing"):
                self.audio_player.is_playing = True
                if hasattr(self.audio_player, "play_btn"):
                    self.audio_player.play_btn.config(text="⏸️")
            if hasattr(self.audio_player, "paused_position"):
                self.audio_player.paused_position = position
            if hasattr(self.audio_player, "stream_start_time"):
                self.audio_player.stream_start_time = time.time() - position
            if hasattr(self.audio_player, "progress"):
                self.audio_player.progress.set(position)
                if hasattr(self.audio_player, "time_label_start"):
                    self.audio_player.time_label_start.config(
                        text=self.audio_player.format_time(position)
                    )

            # Check if audio stream is closed and reopen if necessary
            if not self.audio_stream or not self.audio_stream.is_active():
                print("Audio stream is closed, reopening...")
                try:
                    # Initialize PyAudio if needed
                    if not self.pyaudio_player:
                        self.pyaudio_player = pyaudio.PyAudio()

                    # Open new audio stream
                    self.audio_stream = self.pyaudio_player.open(
                        format=pyaudio.paInt16,
                        channels=1,
                        rate=self.sample_rate,
                        output=True,
                        frames_per_buffer=self.chunk_size,
                    )
                    print("Audio stream reopened successfully")
                except Exception as e:
                    print(f"Error reopening audio stream: {e}")
                    import traceback

                    traceback.print_exc()

            # Resume requesting audio chunks
            self.is_streaming = True

            # Calculate the chunk index for the current paused position
            samples_per_chunk = self.chunk_size // 2  # 2 bytes per sample
            chunk_index = int(position * self.sample_rate / samples_per_chunk)
            print(f"Resuming from chunk {chunk_index} (position: {position}s)")
            self.request_next_chunk(room_code, chunk_index)

        @self.sio.event
        def stream_seeked(data):
            """Called when audio stream is seeked to a new position."""
            room_code = data.get("room_code")
            song_index = data.get("song_index")
            position = data.get("position", 0)
            print(f"Stream seeked to {position}s for song index: {song_index}")

            # Stop streaming temporarily to clear all pending requests
            self.is_streaming = False
            print(f"Stopped streaming temporarily for seek")

            # Clear the audio buffer to prevent old audio from playing
            self.current_audio_chunks = {}
            print(f"Cleared audio buffer for seek to {position}s")

            # Update audio player state
            if hasattr(self.audio_player, "stream_start_time"):
                # Adjust the stream start time to reflect the new position
                self.audio_player.stream_start_time = time.time() - position
                self.audio_player.paused_position = position

            # Update progress bar
            if hasattr(self.audio_player, "progress"):
                self.audio_player.progress.set(position)
                if hasattr(self.audio_player, "time_label_start"):
                    self.audio_player.time_label_start.config(
                        text=self.audio_player.format_time(position)
                    )

            # Restart streaming from new position
            self.is_streaming = True
            # Each sample is 2 bytes (16-bit), so we need to account for that
            samples_per_chunk = self.chunk_size // 2  # 2 bytes per sample
            chunk_index = int(position * self.sample_rate / samples_per_chunk)

            # Debug: Calculate the actual time this chunk represents
            actual_time = chunk_index * samples_per_chunk / self.sample_rate
            print(
                f"Client seek: {position}s -> chunk {chunk_index} -> actual time: {actual_time:.2f}s"
            )

            print(
                f"Restarting streaming from chunk {chunk_index} for seek position {position}s"
            )
            self.request_next_chunk(room_code, chunk_index)

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
                f"Emitting create_room with username: {username}, color_idx: {color.color_index}"
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

    def sync_queue_with_server(self, queue):
        """Sync the local queue with the server."""
        if self.connected and self.room_code:
            with self.socket_lock:
                # Strip base64 data to reduce payload size
                stripped_queue = self._strip_base64_from_queue(queue)
                print(f"[CLIENT] About to emit sync_queue_with_friends event")
                self.sio.emit(
                    "sync_queue_with_friends",
                    {"room_code": self.room_code, "queue": stripped_queue},
                )
                return True

    def sync_current_index_with_server(self, current_idx):
        """Sync the current song index with the server."""
        if self.connected and self.room_code:
            with self.socket_lock:
                print(f"[CLIENT] About to emit sync_current_index event")
                self.sio.emit(
                    "sync_current_index",
                    {"room_code": self.room_code, "current_idx": current_idx},
                )
                return True

    def _strip_base64_from_queue(self, queue):
        """Strip base64 cover_image data from queue to reduce payload size."""
        stripped_queue = []
        original_size = 0
        stripped_size = 0

        for song in queue:
            # Create a copy without the base64 data
            stripped_song = song.copy()
            if "cover_image" in stripped_song:
                # Keep a flag that cover image exists, but remove the actual data
                original_size += len(stripped_song["cover_image"])
                stripped_song["has_cover_image"] = True
                del stripped_song["cover_image"]
            else:
                stripped_song["has_cover_image"] = False
            stripped_queue.append(stripped_song)

        # Calculate sizes for debugging
        import json

        original_payload = json.dumps(queue)
        stripped_payload = json.dumps(stripped_queue)

        print(
            f"[CLIENT] Queue payload size: {len(original_payload)} -> {len(stripped_payload)} bytes"
        )
        print(f"[CLIENT] Base64 data removed: {original_size} bytes")

        return stripped_queue

    def remove_song_from_queue(self, index):
        """Remove a song from the queue and sync with other clients."""
        self.queue_manager.remove_from_queue(index)
        if 0 <= index < len(self.queue_manager.queue):
            self.sync_queue_with_server(self.queue_manager.queue)
            if hasattr(self.audio_player, "queue_ui") and self.audio_player.queue_ui:
                self.audio_player.queue_ui.display_queue()

    def get_queue(self):
        """Get the current queue."""
        return self.queue_manager.queue

    def start_audio_stream(self, room_code: str, total_chunks: int):
        """Start audio streaming for a room."""
        try:
            print(f"Starting audio stream for room {room_code}")
            print(f"Total chunks: " + str(total_chunks))

            # Initialize PyAudio
            self.pyaudio_player = pyaudio.PyAudio()
            print("PyAudio initialized successfully")

            # Open audio stream
            self.audio_stream = self.pyaudio_player.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=self.sample_rate,
                output=True,
                frames_per_buffer=self.chunk_size,
            )
            print("Audio stream opened successfully")

            self.is_streaming = True
            self.current_audio_chunks = {}

            # Request first chunk
            self.request_next_chunk(room_code, 0)
            print(f"Requested first audio chunk for room {room_code}")

            # Don't clear the starting flag here - it will be cleared after song_started is processed

        except Exception as e:
            print(f"Error starting audio stream: {e}")
            import traceback

            traceback.print_exc()

    def request_next_chunk(self, room_code: str, chunk_index: int):
        """Request next audio chunk from server."""
        if self.connected and self.is_streaming:
            self.sio.emit(
                "request_audio_chunk",
                {"room_code": room_code, "chunk_index": chunk_index},
            )

    def play_audio_chunk(self, audio_chunk: bytes):
        """Play an audio chunk."""
        if self.audio_stream:
            try:
                # Check if stream is active before writing
                if self.audio_stream.is_active():
                    # print(f"Playing audio chunk, size: {len(audio_chunk)} bytes")
                    self.audio_stream.write(audio_chunk)
                    # print("Audio chunk played successfully")
                else:
                    print("Audio stream is not active, skipping chunk")
            except Exception as e:
                print(f"Error playing audio chunk: {e}")
                # If stream is closed, try to reopen it
                if "Stream closed" in str(e) or "Stream not active" in str(e):
                    print("Stream appears to be closed, will reopen on next resume")
                    # Mark stream as None so it gets recreated
                    self.audio_stream = None
        else:
            print(
                f"Cannot play audio chunk - audio_stream: {self.audio_stream is not None}"
            )

    def stop_audio_stream(self):
        """Stop audio streaming."""
        self.is_streaming = False
        if self.audio_stream:
            self.audio_stream.stop_stream()
            self.audio_stream.close()
        if self.pyaudio_player:
            self.pyaudio_player.terminate()
        self.current_audio_chunks = {}

    def is_connected(self):
        """Check if connected to server."""
        return self.connected
