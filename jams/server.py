import socketio
import eventlet
from eventlet import wsgi
import random
import string
from typing import Dict, List, Optional
import os
import json
import subprocess
import sys

sys.path.append(".")
from utils.song import get_song_metadata


class JamServer:
    """
    Simple server that manages jam sessions and sync events.
    Focuses on: queue management, play state, user management
    """

    def __init__(self):
        self.sio = socketio.Server(cors_allowed_origins="*")
        self.app = socketio.WSGIApp(self.sio)

        # Store room data: {room_code: {users: [], queue: [], host: str, current_idx: int, is_playing: bool}}
        self.rooms: Dict[str, Dict] = {}

        # Music download settings
        self.downloads_folder = "downloads"
        self.music_data_file = "music_data.json"
        self.ensure_downloads_folder()
        self.load_music_library()

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

        print(f"Could not extract song ID from URL: {url}")
        return url

    def is_valid_spotify_url(self, url: str) -> bool:
        """Check if URL is a valid Spotify track URL."""
        import re

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

    def setup_socket_handlers(self):
        """Set up socket.io event handlers for the server."""

        @self.sio.event
        def connect(sid, environ):
            print(f"Client connected: {sid}")

        @self.sio.event
        def disconnect(sid):
            print(f"Client disconnected: {sid}")
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
                "queue": [],
                "host": sid,
                "current_idx": -1,
                "is_playing": False,
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

            # Send current state to new user
            room_data = self.rooms[room_code]
            self.sio.emit(
                "sync_event",
                {
                    "type": "queue_updated",
                    "data": {"queue": room_data["queue"]},
                    "updated_by": "server",
                },
                room=sid,
            )

            self.sio.emit(
                "sync_event",
                {
                    "type": "play_state_changed",
                    "data": {
                        "is_playing": room_data["is_playing"],
                        "song_index": room_data["current_idx"],
                    },
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

            self.sio.emit(
                "room_joined",
                {"room_code": room_code, "players": players_data},
                room=sid,
            )

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
                # Download the song asynchronously
                def download_and_notify():
                    try:
                        print(f"Starting download for: {url}")

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

                            # Find the downloaded file
                            downloaded_file = None
                            for filename in os.listdir(self.downloads_folder):
                                if filename.endswith(".mp3"):
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
        def sync_event(sid, data):
            """Handle all sync events from clients."""
            room_code = data.get("room_code")
            event_type = data.get("type")
            event_data = data.get("data", {})

            if room_code not in self.rooms:
                return

            print(f"[SERVER] Received sync event: {event_type} from {sid}")

            if event_type == "queue_updated":
                # Update queue
                self.rooms[room_code]["queue"] = event_data.get("queue", [])

                # Broadcast to all users in room
                self.sio.emit(
                    "sync_event",
                    {
                        "type": "queue_updated",
                        "data": {"queue": self.rooms[room_code]["queue"]},
                        "updated_by": sid,
                    },
                    room=room_code,
                )

            elif event_type == "play_state_changed":
                # Update play state
                self.rooms[room_code]["is_playing"] = event_data.get(
                    "is_playing", False
                )
                self.rooms[room_code]["current_idx"] = event_data.get("song_index", -1)

                # Broadcast to all users in room
                self.sio.emit(
                    "sync_event",
                    {
                        "type": "play_state_changed",
                        "data": {
                            "is_playing": self.rooms[room_code]["is_playing"],
                            "song_index": self.rooms[room_code]["current_idx"],
                        },
                        "updated_by": sid,
                    },
                    room=room_code,
                )

            elif event_type == "song_changed":
                # Update current song
                self.rooms[room_code]["current_idx"] = event_data.get("song_index", -1)

                # Broadcast to all users in room
                self.sio.emit(
                    "sync_event",
                    {
                        "type": "song_changed",
                        "data": {"song_index": self.rooms[room_code]["current_idx"]},
                        "updated_by": sid,
                    },
                    room=room_code,
                )

    def add_song_to_room_queue(self, sid, room_code: str, song_metadata: Dict):
        """Add a song to a room's queue and broadcast the update."""
        if room_code in self.rooms:
            self.rooms[room_code]["queue"].append(song_metadata)

            # Broadcast updated queue to all users in room
            self.sio.emit(
                "sync_event",
                {
                    "type": "queue_updated",
                    "data": {"queue": self.rooms[room_code]["queue"]},
                    "updated_by": sid,
                },
                room=room_code,
            )

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

    def run(self, host="0.0.0.0", port=5000):
        """Start the server."""
        print(f"Starting Jam Server on {host}:{port}")
        wsgi.server(eventlet.listen((host, port)), self.app)


if __name__ == "__main__":
    server = JamServer()
    server.run()
