import socketio
import eventlet
from eventlet import wsgi
import random
import string
from typing import Dict, Optional
import os
import json
import subprocess
import base64
from pydub import AudioSegment
import sys
import numpy as np

sys.path.append(".")
from utils.song import get_song_metadata
from screens.constants import LOCAL_IP, LOCAL_PORT


class JamServer:
    """
    Server class that manages the state of jam sessions/parties.
    Handles room creation, user management, and queue synchronization.
    """

    def __init__(self):
        self.sio = socketio.Server(cors_allowed_origins="*")
        self.app = socketio.WSGIApp(self.sio)

        # Store room data: {room_code: {users: [], queue: [], host: str, current_idx: int}}
        self.rooms: Dict[str, Dict] = {}

        # Music download settings
        self.downloads_folder = "downloads"
        self.music_data_file = "music_data.json"
        self.ensure_downloads_folder()
        self.load_music_library()

        # Audio streaming settings
        self.chunk_size = 4096
        self.sample_rate = 44100
        self.current_audio_data = {}  # {room_code: audio_data}
        self.current_positions = {}  # {room_code: current_position}
        self.paused_rooms = set()  # Track which rooms are paused

        # Set up socket event handlers
        self.setup_socket_handlers()

    def extract_song_id_from_url(self, url: str) -> str:
        """Extract Spotify song ID from various URL formats."""
        import re

        # Spotify URL patterns
        patterns = [
            r"spotify\.com/track/([a-zA-Z0-9]+)",  # Standard track URL
            r"spotify\.com/track/([a-zA-Z0-9]+)\?",  # With query params
            r"open\.spotify\.com/track/([a-zA-Z0-9]+)",  # Open.spotify.com
            r"open\.spotify\.com/track/([a-zA-Z0-9]+)\?",  # With query params
        ]

        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                song_id = match.group(1)
                print(f"Extracted song ID: {song_id} from URL: {url}")
                return song_id

        # If no pattern matches, return the URL as fallback
        print(f"Could not extract song ID from URL: {url}")
        return url

    def is_valid_spotify_url(self, url: str) -> bool:
        """Check if URL is a valid Spotify track URL."""
        import re

        # Check if it's a Spotify track URL
        patterns = [
            r"spotify\.com/track/",
            r"open\.spotify\.com/track/",
        ]

        for pattern in patterns:
            if re.search(pattern, url):
                return True

        return False

    def ensure_downloads_folder(self):
        """Ensure the downloads folder exists."""
        if not os.path.exists(self.downloads_folder):
            os.makedirs(self.downloads_folder)
            print(f"Created downloads folder: {self.downloads_folder}")

    def load_music_library(self):
        """Load the music library from file."""
        if not os.path.exists(self.music_data_file):
            with open(self.music_data_file, "w", encoding="utf-8") as file:
                json.dump([], file)
            self.music_library = []
        else:
            with open(self.music_data_file, "r", encoding="utf-8") as file:
                self.music_library = json.load(file)

    def save_music_library(self):
        """Save the music library to file."""
        with open(self.music_data_file, "w", encoding="utf-8") as file:
            json.dump(self.music_library, file, indent=2)

    def download_song(self, url: str) -> Optional[Dict]:
        """Download a song using spotdl and return metadata."""

        # Create a unique filename for this download
        import uuid

        download_id = str(uuid.uuid4())

        # Run spotdl download command
        cmd = [
            "spotdl",
            "--output",
            self.downloads_folder,
            "--format",
            "mp3",
            "--save-file",
            f"{self.downloads_folder}/{download_id}.spotdl",
            url,
        ]

        print(" ".join(cmd))

        print(f"Downloading song: {url}")

        # Use Popen for non-blocking subprocess
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )

        # Wait for process to complete (non-blocking with eventlet)
        stdout, stderr = process.communicate()

        if process.returncode != 0:
            print(f"Download failed: {stderr}")
            return None

        # Read the metadata file
        metadata_file = os.path.join(self.downloads_folder, f"{download_id}.spotdl")
        if os.path.exists(metadata_file):
            with open(metadata_file, "r", encoding="utf-8") as f:
                metadata = json.load(f)[0]

            # Clean up metadata file
            os.remove(metadata_file)

            # Find the downloaded file
            file_path = os.path.join(
                self.downloads_folder, f"{metadata['artist']} - {metadata['name']}.mp3"
            )

            # Check if file exists and extract proper metadata
            if os.path.exists(file_path):
                # Extract full metadata from the downloaded MP3 file
                full_metadata = get_song_metadata(file_path)

                # Merge spotdl metadata with full metadata
                merged_metadata = {
                    **metadata,  # Keep spotdl metadata (name, artist, etc.)
                    **full_metadata,  # Override with full metadata (cover_image, etc.)
                    "filepath": file_path,
                    "url": url,
                    "song_id": self.extract_song_id_from_url(url),
                }

                # Ensure we have both 'name' and 'title' fields for compatibility
                if "name" in merged_metadata and "title" not in merged_metadata:
                    merged_metadata["title"] = merged_metadata["name"]
                elif "title" in merged_metadata and "name" not in merged_metadata:
                    merged_metadata["name"] = merged_metadata["title"]

                # Add to music library
                self.music_library.append(merged_metadata)
                self.save_music_library()

                print(
                    f"Successfully downloaded: {merged_metadata.get('name', 'Unknown')}"
                )
                print(
                    f"Cover image: {'Yes' if merged_metadata.get('cover_image') else 'No'}"
                )
                return merged_metadata
            else:
                print(f"Downloaded file not found: {file_path}")
                return None

        return None

    def setup_socket_handlers(self):
        """Set up socket.io event handlers for the server."""

        @self.sio.event
        def connect(sid, environ):
            print(f"Client connected: {sid}")
            print(f"[SERVER] Connect - Available rooms: {list(self.rooms.keys())}")

        @self.sio.event
        def disconnect(sid):
            print(f"Client disconnected: {sid}")
            print(
                f"[SERVER] Disconnect - Available rooms before cleanup: {list(self.rooms.keys())}"
            )
            # Remove user from their room
            self.remove_user_from_room(sid)
            print(
                f"[SERVER] Disconnect - Available rooms after cleanup: {list(self.rooms.keys())}"
            )

        @self.sio.event
        def test_event(sid, data):
            """Test event to verify server is receiving events."""
            print(f"[SERVER] Received test event from {sid}: {data}")
            self.sio.emit(
                "test_response", {"message": "Server received test event"}, room=sid
            )

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
                "queue": [],
                "host": sid,
                "current_idx": 0,
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

            # Send current queue to new user
            self.sio.emit(
                "queue_updated", {"queue": self.rooms[room_code]["queue"]}, room=sid
            )

            # Send current index to new user
            current_idx = self.rooms[room_code].get("current_idx", 0)
            self.sio.emit(
                "current_index_synced",
                {
                    "room_code": room_code,
                    "current_idx": current_idx,
                    "updated_by": "server",
                },
                room=sid,
            )

            # Send initial players list to new user
            players_data = []
            for user in self.rooms[room_code]["users"]:
                players_data.append(
                    {
                        "username": user["username"],
                        "color_idx": user["color_idx"],
                        "position": user.get("position", 0),
                    }
                )

            print(players_data)

            self.sio.emit(
                "room_joined",
                {"room_code": room_code, "players": players_data},
                room=sid,
            )

        @self.sio.event
        def update_queue(sid, data):
            """Update the queue for a room."""
            room_code = data.get("room_code")
            new_queue = data.get("queue", [])

            if room_code in self.rooms:
                self.rooms[room_code]["queue"] = new_queue

                # Broadcast updated queue to all users in room
                self.sio.emit("queue_updated", {"queue": new_queue}, room=room_code)

        @self.sio.event
        def add_url_to_queue(sid, data):
            """Add a URL to the queue by downloading it first."""
            room_code = data.get("room_code")
            url = data.get("url")

            if not room_code or not url:
                self.sio.emit(
                    "error", {"message": "Missing room_code or url"}, room=sid
                )
                return

            if room_code not in self.rooms:
                self.sio.emit("error", {"message": "Room not found"}, room=sid)
                return

            print(f"Processing URL for room {room_code}: {url}")

            # Validate Spotify URL
            if not self.is_valid_spotify_url(url):
                self.sio.emit(
                    "url_processed",
                    {
                        "status": "error",
                        "message": "Invalid Spotify URL. Please provide a valid Spotify track URL.",
                    },
                    room=sid,
                )
                return

            # Extract song ID from URL
            song_id = self.extract_song_id_from_url(url)

            # Check if song already exists in library using song_id
            existing_song = None
            for song in self.music_library:
                if song.get("song_id") == song_id:
                    existing_song = song
                    break

            if existing_song:
                # Song already downloaded, add to queue
                print(
                    f"Song already exists in library: {existing_song.get('name', 'Unknown')}"
                )
                print(
                    f"Cover image: {'Yes' if existing_song.get('cover_image') else 'No'}"
                )
                self.add_song_to_room_queue(sid, room_code, existing_song)
                self.sio.emit(
                    "url_processed",
                    {
                        "status": "success",
                        "message": "Song already in library",
                        "song": existing_song,
                    },
                    room=sid,
                )
            else:
                # Download the song asynchronously using eventlet
                def download_and_notify():
                    try:
                        print(f"Starting download for: {url}")

                        # Use eventlet's non-blocking subprocess
                        import subprocess

                        # Create a unique filename for this download
                        import uuid

                        download_id = str(uuid.uuid4())

                        # Run spotdl download command
                        cmd = [
                            "spotdl",
                            "--output",
                            self.downloads_folder,
                            "--format",
                            "mp3",
                            "--save-file",
                            f"{self.downloads_folder}/{download_id}.spotdl",
                            url,
                        ]

                        print(" ".join(cmd))

                        # Use eventlet's non-blocking subprocess
                        process = subprocess.Popen(
                            cmd,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            text=True,
                            encoding="utf-8",
                        )

                        # Non-blocking wait for process completion
                        while process.poll() is None:
                            eventlet.sleep(0)  # Yield control to eventlet

                        stdout, stderr = process.communicate()

                        if process.returncode != 0:
                            print(f"Download failed: {stderr}")
                            eventlet.spawn_after(
                                0,
                                lambda: self.sio.emit(
                                    "url_processed",
                                    {
                                        "status": "error",
                                        "message": "Failed to download song",
                                    },
                                    room=sid,
                                ),
                            )
                            return

                        # Read the metadata file
                        metadata_file = os.path.join(
                            self.downloads_folder, f"{download_id}.spotdl"
                        )
                        if os.path.exists(metadata_file):
                            with open(metadata_file, "r", encoding="utf-8") as f:
                                metadata = json.load(f)[0]

                            # Clean up metadata file
                            os.remove(metadata_file)

                            # Find the downloaded file by searching for files with the song name
                            downloaded_file = None
                            for filename in os.listdir(self.downloads_folder):
                                if filename.endswith(".mp3"):
                                    # Split by "-" and get the second part (song name)
                                    parts = filename.replace(".mp3", "").split(" - ")
                                    if len(parts) >= 2:
                                        song_name = parts[1].strip()
                                        if song_name == metadata["name"]:
                                            downloaded_file = os.path.join(
                                                self.downloads_folder, filename
                                            )
                                            break

                            # Check if file was found
                            if downloaded_file and os.path.exists(downloaded_file):
                                # Extract full metadata from the downloaded MP3 file
                                full_metadata = get_song_metadata(downloaded_file)

                                # Merge spotdl metadata with full metadata
                                merged_metadata = {
                                    **metadata,  # Keep spotdl metadata (name, artist, etc.)
                                    **full_metadata,  # Override with full metadata (cover_image, etc.)
                                    "filepath": downloaded_file,
                                    "url": url,
                                    "song_id": self.extract_song_id_from_url(url),
                                }

                                # Ensure we have both 'name' and 'title' fields for compatibility
                                if (
                                    "name" in merged_metadata
                                    and "title" not in merged_metadata
                                ):
                                    merged_metadata["title"] = merged_metadata["name"]
                                elif (
                                    "title" in merged_metadata
                                    and "name" not in merged_metadata
                                ):
                                    merged_metadata["name"] = merged_metadata["title"]

                                # Add to music library
                                self.music_library.append(merged_metadata)
                                self.save_music_library()

                                print(
                                    f"Successfully downloaded: {merged_metadata.get('name', 'Unknown')}"
                                )
                                print(
                                    f"Cover image: {'Yes' if merged_metadata.get('cover_image') else 'No'}"
                                )

                                # Add to queue and notify
                                self.add_song_to_room_queue(
                                    sid, room_code, merged_metadata
                                )
                                eventlet.spawn_after(
                                    0,
                                    lambda: self.sio.emit(
                                        "url_processed",
                                        {
                                            "status": "success",
                                            "message": "Song downloaded and added to queue",
                                            "song": merged_metadata,
                                        },
                                        room=sid,
                                    ),
                                )
                            else:
                                print(
                                    f"Downloaded file not found for song: {metadata['name']}"
                                )
                                eventlet.spawn_after(
                                    0,
                                    lambda: self.sio.emit(
                                        "url_processed",
                                        {
                                            "status": "error",
                                            "message": "Downloaded file not found",
                                        },
                                        room=sid,
                                    ),
                                )
                        else:
                            eventlet.spawn_after(
                                0,
                                lambda: self.sio.emit(
                                    "url_processed",
                                    {
                                        "status": "error",
                                        "message": "Metadata file not found",
                                    },
                                    room=sid,
                                ),
                            )

                    except Exception as e:
                        print(f"Error processing URL: {e}")
                        eventlet.spawn_after(
                            0,
                            lambda: self.sio.emit(
                                "url_processed",
                                {
                                    "status": "error",
                                    "message": f"Error processing URL",
                                },
                                room=sid,
                            ),
                        )

                # Start download in eventlet thread (non-blocking)
                eventlet.spawn(download_and_notify)

                # Notify client that download started
                self.sio.emit(
                    "url_processing", {"message": "Downloading song..."}, room=sid
                )

        @self.sio.event
        def sync_queue_with_friends(sid, data):
            """Sync queue changes with all users in the room."""
            # Use eventlet to handle this event asynchronously
            eventlet.spawn(self._handle_sync_queue_with_friends, sid, data)

        @self.sio.event
        def sync_current_index(sid, data):
            """Sync the current song index with all users in the room."""
            room_code = data.get("room_code")
            current_idx = data.get("current_idx", 0)

            if room_code in self.rooms:
                # Update the room's current index
                self.rooms[room_code]["current_idx"] = current_idx

                # Broadcast to all users in the room
                self.sio.emit(
                    "current_index_synced",
                    {
                        "room_code": room_code,
                        "current_idx": current_idx,
                        "updated_by": sid,
                    },
                    room=room_code,
                )

        @self.sio.event
        def request_audio_chunk(sid, data):
            """Client requests an audio chunk."""
            room_code = data.get("room_code")
            chunk_index = data.get("chunk_index", 0)

            # Don't send audio chunks if room is paused
            if room_code in self.paused_rooms:
                print(f"Room {room_code} is paused, ignoring audio chunk request")
                return

            if room_code in self.current_audio_data:
                print(f"Sending audio chunk {chunk_index} for room {room_code}")
                audio_chunk = self.stream_audio_chunk(room_code, chunk_index)
                if audio_chunk:
                    # Send audio chunk as base64
                    chunk_b64 = base64.b64encode(audio_chunk).decode("utf-8")
                    self.sio.emit(
                        "audio_chunk",
                        {
                            "room_code": room_code,
                            "chunk_index": chunk_index,
                            "audio_data": chunk_b64,
                        },
                        room=sid,
                    )
                else:
                    print(f"No audio chunk available for chunk_index {chunk_index}")
            else:
                print(f"No audio data available for room {room_code}")

        @self.sio.event
        def play_song(sid, data):
            """Start playing a song in a room."""
            # Use eventlet to handle this event asynchronously
            eventlet.spawn(self._handle_play_song, sid, data)

        @self.sio.event
        def pause_stream(sid, data):
            """Pause audio streaming for a room."""
            room_code = data.get("room_code")
            song_index = data.get("song_index", 0)
            position = data.get("position", 0)

            if room_code in self.rooms:
                # Add room to paused set
                self.paused_rooms.add(room_code)
                print(f"Room {room_code} added to paused rooms")

                # Broadcast pause event to all clients in room
                self.sio.emit(
                    "stream_paused",
                    {
                        "room_code": room_code,
                        "song_index": song_index,
                        "position": position,
                    },
                    room=room_code,
                )
                print(f"Stream paused for room {room_code} at position {position}")

        @self.sio.event
        def resume_stream(sid, data):
            """Resume audio streaming for a room."""
            room_code = data.get("room_code")
            song_index = data.get("song_index", 0)
            position = data.get("position", 0)

            if room_code in self.rooms:
                # Remove room from paused set
                if room_code in self.paused_rooms:
                    self.paused_rooms.remove(room_code)
                    print(f"Room {room_code} removed from paused rooms")

                # Broadcast resume event to all clients in room
                self.sio.emit(
                    "stream_resumed",
                    {
                        "room_code": room_code,
                        "song_index": song_index,
                        "position": position,
                    },
                    room=room_code,
                )
                print(f"Stream resumed for room {room_code} at position {position}")

        @self.sio.event
        def seek_stream(sid, data):
            """Seek to position in streaming audio."""
            room_code = data.get("room_code")
            song_index = data.get("song_index", 0)
            seek_position = data.get("position", 0)

            if room_code in self.rooms:
                # Convert seconds to chunk index
                # Each sample is 2 bytes (16-bit), so we need to account for that
                samples_per_chunk = self.chunk_size // 2  # 2 bytes per sample
                chunk_index = int(seek_position * self.sample_rate / samples_per_chunk)

                # Debug: Calculate the actual time this chunk represents
                actual_time = chunk_index * samples_per_chunk / self.sample_rate
                print(
                    f"Seek request: {seek_position}s -> chunk {chunk_index} -> actual time: {actual_time:.2f}s"
                )

                # Update the current position for the room
                if room_code in self.current_positions:
                    self.current_positions[room_code] = chunk_index
                    print(
                        f"Updated server position for room {room_code}: chunk {chunk_index} (time: {seek_position}s)"
                    )
                else:
                    print(f"Warning: room {room_code} not found in current_positions")

                # Broadcast seek event to all clients in room
                self.sio.emit(
                    "stream_seeked",
                    {
                        "room_code": room_code,
                        "song_index": song_index,
                        "position": seek_position,
                    },
                    room=room_code,
                )
                print(f"Stream seeked to {seek_position}s for room {room_code}")

                # Don't send audio chunk here - let clients request it when ready

        @self.sio.event
        def user_talking_state(sid, data):
            """Handle user talking state updates and broadcast to room."""
            room_code = data.get("room_code")
            username = data.get("username")
            is_talking = bool(data.get("is_talking", 0))
            if not room_code or not username:
                return
            # Optionally: update server-side state if you want to track who is talking
            # Broadcast to all users in the room
            self.sio.emit(
                "user_talking_update",
                {"username": username, "is_talking": is_talking},
                room=room_code,
            )

    def add_song_to_room_queue(self, sid, room_code: str, song_metadata: Dict):
        """Add a song to a room's queue and broadcast the update."""
        if room_code in self.rooms:

            self.rooms[room_code]["queue"].append(song_metadata)
            self._handle_sync_queue_with_friends(
                sid, {"queue": self.rooms[room_code]["queue"], "room_code": room_code}
            )

    def _handle_sync_queue_with_friends(self, sid, data):
        """Handle sync queue with friends in eventlet thread."""
        room_code = data.get("room_code")
        queue_data = data.get("queue", [])

        print(
            f"[SERVER] Received queue sync request from {sid} for room {room_code}: {len(queue_data)} songs"
        )
        print(f"[SERVER] Available rooms: {list(self.rooms.keys())}")

        if room_code in self.rooms:
            # Restore cover images from music library if needed
            restored_queue = self._restore_cover_images_from_library(queue_data)

            # Update the room's queue
            self.rooms[room_code]["queue"] = restored_queue
            print(
                f"[SERVER] Updated room {room_code} queue with {len(restored_queue)} songs"
            )

            # Broadcast to all users in the room
            self.sio.emit(
                "queue_synced",
                {"queue": restored_queue, "updated_by": sid},
                room=room_code,
            )
            print(
                f"[SERVER] Broadcasted queue_synced event to room {room_code}: {len(restored_queue)} songs"
            )
        else:
            print(f"[SERVER] Room {room_code} not found for sync request")
            print(f"[SERVER] Available rooms: {list(self.rooms.keys())}")

    def _restore_cover_images_from_library(self, queue_data):
        """Restore cover images from music library for songs in queue."""
        restored_queue = []
        for song in queue_data:
            # Create a copy of the song
            restored_song = song.copy()

            # If song has a song_id and needs cover image restoration
            if song.get("song_id") and song.get("has_cover_image", False):
                # Find the song in the music library
                for library_song in self.music_library:
                    if library_song.get("song_id") == song["song_id"]:
                        # Restore the cover image
                        if library_song.get("cover_image"):
                            restored_song["cover_image"] = library_song["cover_image"]
                        break

            # Remove the flag since we've handled it
            if "has_cover_image" in restored_song:
                del restored_song["has_cover_image"]

            restored_queue.append(restored_song)

        return restored_queue

    def _handle_play_song(self, sid, data):
        """Handle play song in eventlet thread."""
        room_code = data.get("room_code")
        song_index = data.get("song_index", 0)

        print(f"[SERVER] Received play_song event from {sid}")
        print(f"[SERVER] Room code: {room_code}, Song index: {song_index}")
        print(f"[SERVER] Available rooms: {list(self.rooms.keys())}")

        if room_code in self.rooms and song_index < len(self.rooms[room_code]["queue"]):
            song = self.rooms[room_code]["queue"][song_index]
            print(
                f"[SERVER] Starting audio stream for song: {song.get('name', 'Unknown')}"
            )

            # Update the room's current index
            self.rooms[room_code]["current_idx"] = song_index

            self.start_audio_stream(room_code, song)

            # Broadcast play event to all clients in room
            self.sio.emit(
                "song_started",
                {"room_code": room_code, "song_index": song_index, "song": song},
                room=room_code,
            )
            print(f"[SERVER] Broadcasted song_started event to room {room_code}")
        else:
            print(
                f"[SERVER] Invalid room or song index - room: {room_code}, song_index: {song_index}"
            )
            if room_code in self.rooms:
                print(f"[SERVER] Queue length: {len(self.rooms[room_code]['queue'])}")
            else:
                print(f"[SERVER] Room not found")

    def load_audio_data(self, filepath: str) -> bytes:
        """Load audio data from MP3 file and convert to PCM."""
        try:
            # Load audio file using pydub
            audio = AudioSegment.from_mp3(filepath)

            # Convert to mono and set sample rate
            audio = audio.set_channels(1).set_frame_rate(self.sample_rate)

            # Export as signed 16-bit PCM data for PyAudio
            # Convert to numpy array first, then to bytes

            # Get the raw audio data as numpy array
            samples = np.array(audio.get_array_of_samples())

            # Ensure it's 16-bit signed integers
            samples = samples.astype(np.int16)

            # Convert to bytes
            audio_bytes = samples.tobytes()

            # Debug: Print audio info
            samples_per_chunk = self.chunk_size // 2  # 2 bytes per sample
            print(f"Loaded audio: {len(samples)} samples, {len(audio_bytes)} bytes")
            print(f"Duration: {len(samples) / self.sample_rate:.2f}s")
            print(
                f"Chunk size: {self.chunk_size} bytes ({samples_per_chunk} samples), Sample rate: {self.sample_rate}"
            )
            print(f"Total chunks: {len(audio_bytes) // self.chunk_size}")

            return audio_bytes
        except Exception as e:
            print(f"Error loading audio data: {e}")
            return b""

    def stream_audio_chunk(self, room_code: str, position: int) -> Optional[bytes]:
        """Get audio chunk at specific position for streaming."""
        if room_code not in self.current_audio_data:
            return None

        audio_data = self.current_audio_data[room_code]
        start_pos = position * self.chunk_size
        end_pos = start_pos + self.chunk_size

        # Debug: Calculate the time this chunk represents
        samples_per_chunk = self.chunk_size // 2  # 2 bytes per sample
        chunk_time = position * samples_per_chunk / self.sample_rate
        # print(
        #     f"Streaming chunk {position}: start_pos={start_pos}, end_pos={end_pos}, time={chunk_time:.2f}s"
        # )

        if start_pos < len(audio_data):
            return audio_data[start_pos:end_pos]
        return None

    def start_audio_stream(self, room_code: str, song_metadata: Dict):
        """Start streaming audio for a room."""
        filepath = song_metadata.get("filepath")
        if not filepath or not os.path.exists(filepath):
            print(f"Audio file not found: {filepath}")
            return

        # Load audio data
        audio_data = self.load_audio_data(filepath)
        if audio_data:
            self.current_audio_data[room_code] = audio_data
            self.current_positions[room_code] = 0

            # Notify clients that audio stream is ready
            # Each sample is 2 bytes (16-bit), so we need to account for that
            samples_per_chunk = self.chunk_size // 2  # 2 bytes per sample
            total_chunks = len(audio_data) // self.chunk_size

            self.sio.emit(
                "audio_stream_ready",
                {
                    "room_code": room_code,
                    "song": song_metadata,
                    "total_chunks": total_chunks,
                },
                room=room_code,
            )
            print(f"Audio stream ready for room {room_code}")

    def generate_room_code(self) -> str:
        """Generate a unique 6-character room code."""
        while True:
            code = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
            if code not in self.rooms:
                return code

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

    def broadcast_players_update(self, room_code: str):
        """Broadcast the current players list to all users in a room."""
        if room_code in self.rooms:
            players_data = []
            for user in self.rooms[room_code]["users"]:
                players_data.append(
                    {
                        "username": user["username"],
                        "color_idx": user["color_idx"],
                        "position": user.get("position", 0),
                    }
                )

            self.sio.emit("players_updated", {"players": players_data}, room=room_code)
            print(f"Broadcasted players update for room {room_code}: {players_data}")

    def get_room_info(self, room_code: str) -> Optional[Dict]:
        """Get information about a specific room."""
        return self.rooms.get(room_code)

    def get_all_rooms(self) -> Dict[str, Dict]:
        """Get information about all rooms."""
        return self.rooms

    def run(self, host="0.0.0.0", port=None):
        """Start the server."""
        # Try to get the local IPv4 address for LAN access
        import socket

        if port is None:
            port = LOCAL_PORT
        local_ip = LOCAL_IP

        print(f"Starting Jam Server on {host}:{port}")
        if host == "0.0.0.0":
            print("[INFO] To connect from another device on your network, use:")
            if local_ip and not local_ip.startswith("127."):
                print(f"  http://{local_ip}:{port}")
            else:
                print("  [Replace with your LAN IPv4 address]")
        else:
            print(f"[INFO] Server accessible at http://{host}:{port}")

        # Start Socket.IO server
        wsgi.server(eventlet.listen((host, port)), self.app, log_output=False)


if __name__ == "__main__":
    server = JamServer()
    server.run()
