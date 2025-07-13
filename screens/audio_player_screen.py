import time
import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageTk
from utils.song import get_random_song_metadata, get_song_metadata, base64_to_image
from .queue_screen import FireSideRadioQueueUI
from jams.shared.song_queue import SongQueue
from .constants import WOOD_ENGRAVING_COLOR
from utils.voice_detector import VoiceDetector, dB_to_amplitude
from utils.tkinter_compat import set_window_transparency
import threading
import pyaudio
import numpy as np
import queue


class AudioPlayerScreen:
    def __init__(self, root, metadata=None, client=None):
        self.root = root
        self.transparent_color = "black"
        self.root.geometry("550x400")
        self.root.overrideredirect(True)
        set_window_transparency(self.root, color=self.transparent_color, alpha=0.8)
        self.root.wm_attributes("-topmost", True)
        self.root.configure(bg=self.transparent_color)

        # Store client reference for queue synchronization and streaming
        self.client = client
        self.local_username = getattr(client, "username", None)

        self.queue_manager = SongQueue([])

        # Load fire animation images
        self.fire_images = []
        try:
            for i in range(1, 4):
                fire_img = Image.open(f"assets/fire/Fire_{i}.png")
                # Resize fire images to fit better (157x210 original size)
                fire_img = fire_img.resize((157, 210))
                fire_tk = ImageTk.PhotoImage(fire_img)
                self.fire_images.append(fire_tk)
        except Exception as e:
            print(f"Could not load fire images: {e}")
            self.fire_images = []

        # Load notes animation images
        self.notes_images = []
        try:
            for i in range(1, 4):
                notes_img = Image.open(f"assets/notes/Notes_{i}.png")
                notes_tk = ImageTk.PhotoImage(notes_img)
                self.notes_images.append(notes_tk)
        except Exception as e:
            print(f"Could not load notes images: {e}")
            self.notes_images = []

        # Initialize streaming state
        self.is_playing = False
        self.current_song_index = 0
        self.stream_start_time = None
        self.paused_position = 0
        self.current_duration = 0
        self.metadata = metadata or {}
        self.is_loading = False  # Flag to prevent seeking during load

        # Seek debouncing
        self.seek_debounce_timer = None
        self.last_seek_position = 0
        self.is_user_seeking = False  # Flag to prevent progress updates during seeking

        # Player management
        self.players = []  # List of player objects
        self.player_positions = [
            92,
            230,
            366,
            230,
            6,
            230,
            449,
            230,
        ]  # Canvas coordinates
        self.position_mapping = {
            0: -1,
            1: 1,
            2: -2,
            3: 2,
        }  # Array index to relative position
        self.player_images = {}  # Cache for player images

        self.is_talking = False  # Track if local user is talking
        # Voice detection threshold in dB (adjust as needed)
        self.voice_threshold_db = -30  # Typical values: -40 (quiet) to -20 (loud)
        self.voice_threshold = dB_to_amplitude(self.voice_threshold_db)
        self.voice_detector = VoiceDetector(
            threshold=self.voice_threshold, callback=self._on_voice_state_change
        )
        self.voice_detector.start()
        # Ensure detector stops on window close
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.voice_stream_thread = None
        self.voice_streaming = False
        self.pyaudio_instance = None
        self.mic_stream = None

        self.voice_playback_thread = None
        self.voice_playback_queue = queue.Queue()
        self.voice_playback_running = False
        self.voice_output_stream = None

        self.build_ui()
        self.root.bind("<KeyPress-space>", lambda event: self.toggle_play())
        self.update_progress()

    def _get_metadata_from_queue(self, idx):
        if 0 <= idx < len(self.queue_manager.queue):
            item = self.queue_manager.queue[idx]
            return item  # Return the metadata directly from queue
        return None

    def build_player_controller_ui(self, parent, x=None, y=None, width=275, height=180):
        bg_color = "#7C3F30"
        frame = tk.Frame(
            parent, width=width, height=height, bg=bg_color, highlightthickness=0, bd=0
        )
        if x is not None and y is not None:
            frame.place(x=x, y=y, width=width, height=height)
        else:
            frame.place(
                relx=0.5, rely=0.5, anchor=tk.CENTER, width=width, height=height
            )
        top_frame = tk.Frame(frame, bg=bg_color, highlightthickness=0, bd=0)
        top_frame.pack(fill=tk.X, padx=10, pady=(10, 5))

        # Handle album image (could be base64 string or PIL Image)
        if self.metadata and self.metadata.get("cover_image"):
            cover_image = self.metadata["cover_image"]
            if isinstance(cover_image, str):
                # It's a base64 string, convert to PIL Image
                img = base64_to_image(cover_image)
                if img is None:
                    img = Image.new("RGB", (50, 50), "gray")
            else:
                # It's already a PIL Image
                img = cover_image
        else:
            img = Image.new("RGB", (50, 50), "gray")

        img = img.resize((50, 50))
        self.album_img = ImageTk.PhotoImage(img)
        self.album_label = tk.Label(
            top_frame, image=self.album_img, bg=bg_color, highlightthickness=0, bd=0
        )
        self.album_label.pack(side=tk.LEFT)
        self.album_label.bind("<Button-1>", self.start_move)
        self.album_label.bind("<B1-Motion>", self.do_move)
        text_frame = tk.Frame(top_frame, bg=bg_color, highlightthickness=0, bd=0)
        text_frame.pack(side=tk.LEFT, padx=10)
        max_title_chars = 10
        title = (
            self.metadata.get("title", self.metadata.get("name", ""))
            if self.metadata
            else ""
        )
        if len(title) > max_title_chars:
            title = title[: max_title_chars - 3] + "..."
        tk.Label(
            text_frame,
            text=title,
            fg="white",
            bg=bg_color,
            font=("Helvetica", 10, "bold"),
            anchor="w",
            justify="left",
            wraplength=height,
        ).pack(anchor="w")
        tk.Label(
            text_frame,
            text=self.metadata.get("artist", "") if self.metadata else "",
            fg="gray",
            bg=bg_color,
            font=("Helvetica", 9),
            anchor="w",
            justify="left",
            wraplength=height,
        ).pack(anchor="w")
        close_btn = tk.Button(
            top_frame,
            text="❎",
            command=self.on_close,
            bg=bg_color,
            fg="white",
            bd=0,
            font=("Helvetica", 10),
            activebackground="#ff5555",
            activeforeground="white",
            highlightthickness=0,
            takefocus=0,
        )
        close_btn.pack(side=tk.RIGHT)
        control_frame = tk.Frame(frame, bg=bg_color, highlightthickness=0, bd=0)
        control_frame.pack(pady=5)
        tk.Button(
            control_frame,
            text="⏮️",
            command=self.prev_song,
            bg=bg_color,
            fg="white",
            bd=0,
            font=("Helvetica", 14),
            highlightthickness=0,
            takefocus=0,
        ).pack(side=tk.LEFT, padx=10)
        self.play_btn = tk.Button(
            control_frame,
            text="▶",
            command=self.toggle_play,
            bg=bg_color,
            fg="white",
            bd=0,
            font=("Helvetica", 16),
            takefocus=0,
            highlightthickness=0,
        )
        self.play_btn.pack(side=tk.LEFT, padx=10)
        tk.Button(
            control_frame,
            text="⏭️",
            command=self.next_song,
            bg=bg_color,
            fg="white",
            bd=0,
            font=("Helvetica", 14),
            highlightthickness=0,
            takefocus=0,
        ).pack(side=tk.LEFT, padx=10)
        # Add mute/unmute mic button to the right
        self.is_muted = False
        self.mic_btn = tk.Button(
            control_frame,
            text="🎤",  # Unmuted icon
            command=self.toggle_mic,
            bg=bg_color,
            fg="white",
            bd=0,
            font=("Helvetica", 14),
            highlightthickness=0,
            takefocus=0,
        )
        self.mic_btn.pack(side=tk.LEFT, padx=10)
        bottom_frame = tk.Frame(frame, bg=bg_color, highlightthickness=0, bd=0)
        bottom_frame.pack(fill=tk.X, padx=10, pady=(5, 10))
        self.time_label_start = tk.Label(
            bottom_frame,
            text="00:00",
            fg="white",
            bg=bg_color,
            font=("Helvetica", 8),
        )
        self.time_label_start.pack(side=tk.LEFT)
        self.progress = tk.DoubleVar()
        self.progress_bar = tk.Scale(
            bottom_frame,
            from_=0,
            to=max(self.current_duration, 1),  # Ensure minimum value of 1
            variable=self.progress,
            orient=tk.HORIZONTAL,
            length=width * (150 / 275),
            bg=bg_color,
            fg="white",
            troughcolor="gray",
            showvalue=False,
            sliderlength=10,
            command=self.seek,
            highlightthickness=0,
        )
        self.progress_bar.pack(side=tk.LEFT, padx=5)
        self.time_label_end = tk.Label(
            bottom_frame,
            text=self.format_time(self.current_duration),
            fg="white",
            bg=bg_color,
            font=("Helvetica", 8),
        )
        self.time_label_end.pack(side=tk.LEFT)
        return frame

    def build_fire_radio_button(self):
        points = [306, 347, 334, 351, 339, 374, 303, 371]
        self.trapezoid_id = self.canvas.create_polygon(
            points, fill="#B2B2B2", width=2, tags="fire_radio_btn"
        )
        self.canvas.tag_bind(
            self.trapezoid_id, "<Button-1>", self.open_fire_radio_window
        )

        # Calculate center of trapezoid for text positioning
        # Average of x coordinates and y coordinates
        center_x = sum(points[::2]) / 4 - 2  # Every other point is x coordinate
        center_y = (
            sum(points[1::2]) / 4
        ) - 1  # Every other point starting from 1 is y coordinate

        # Add "Queue" text in the center of the trapezoid
        self.queue_text_id = self.canvas.create_text(
            center_x,
            center_y,
            text="Queue",
            fill=WOOD_ENGRAVING_COLOR,
            font=("Helvetica", 8, "bold"),
            tags="fire_radio_btn",
        )
        # Bind the text to the same click event
        self.canvas.tag_bind(
            self.queue_text_id, "<Button-1>", self.open_fire_radio_window
        )

    def open_fire_radio_window(self, event=None):
        self.queue_ui = FireSideRadioQueueUI(
            self.queue_manager,
            master=self.root,
            on_thumbnail_click=self.play_song_from_queue,
            on_add_url=lambda url: self.handle_url_add(url),
            on_shuffle_queue=lambda: self.queue_manager.shuffle_queue(
                self, client=self.client
            ),
        )
        self.queue_ui.show()

    def handle_url_add(self, url):
        """Handle URL addition with download state management."""
        if self.queue_ui:
            # Set downloading state
            self.queue_ui.set_downloading_state()

            # Add URL to queue (this will trigger the download)
            self.queue_manager.add_url_to_queue(self, url)

    def reset_add_button_state(self):
        """Reset the add button state in the queue UI."""
        if hasattr(self, "queue_ui") and self.queue_ui:
            self.queue_ui.reset_add_button_state()

    def build_ui(self):
        self.canvas = tk.Canvas(
            self.root,
            width=550,
            height=400,
            highlightthickness=0,
            bg=self.transparent_color,
        )
        self.canvas.place(x=0, y=0, relwidth=1, relheight=1)
        frame_img = Image.open("assets/stage_clean.png")
        self.frame_img_tk = ImageTk.PhotoImage(frame_img)
        self.canvas.create_image(0, 0, anchor="nw", image=self.frame_img_tk)

        # Position fire at top-left coordinate (188, 199)
        fire_x = 188
        fire_y = 195

        # Create fire image on canvas
        if self.fire_images:
            self.fire_image_id = self.canvas.create_image(
                fire_x, fire_y, anchor="nw", image=self.fire_images[0]
            )
        else:
            self.fire_image_id = None

        # Create notes image at (0,0) anchor nw
        if self.notes_images:
            self.notes_image_id = self.canvas.create_image(
                0, 0, anchor="nw", image=self.notes_images[0]
            )
        else:
            self.notes_image_id = None

        # Load and position the box image
        try:
            box_img = Image.open("assets/other/Box.png")
            # Resize box image if needed
            box_img = box_img.resize((60, 67))  # Adjust size as needed
            self.box_img_tk = ImageTk.PhotoImage(box_img)
            self.canvas.create_image(296, 311, anchor="nw", image=self.box_img_tk)
        except Exception as e:
            print(f"Could not load box image: {e}")

        self.player_controller = self.build_player_controller_ui(
            self.canvas, x=160, y=29, width=230, height=140
        )
        self.canvas.create_window(
            160, 29, anchor="nw", window=self.player_controller, width=220, height=140
        )
        self.build_fire_radio_button()

        # Start fire animation
        self.animate_fire()
        # Start notes animation
        self.animate_notes()

    def start_move(self, event):
        self._drag_start_pointer_x = self.root.winfo_pointerx()
        self._drag_start_pointer_y = self.root.winfo_pointery()
        self._drag_start_win_x = self.root.winfo_x()
        self._drag_start_win_y = self.root.winfo_y()

    def do_move(self, event):
        dx = self.root.winfo_pointerx() - self._drag_start_pointer_x
        dy = self.root.winfo_pointery() - self._drag_start_pointer_y
        new_x = self._drag_start_win_x + dx
        new_y = self._drag_start_win_y + dy
        self.root.geometry(f"+{new_x}+{new_y}")

    def toggle_play(self):
        """Toggle play/pause for streaming audio."""
        current_pos = self.get_current_pos()
        if self.is_playing:
            print("Playing -> Paused")
            print(f"Current position before pause: {current_pos}")

            # Pause streaming
            if self.client and self.client.connected:
                self.client.sio.emit(
                    "pause_stream",
                    {
                        "room_code": self.client.room_code,
                        "song_index": self.current_song_index,
                        "position": current_pos,
                    },
                )
            self.play_btn.config(text="▶")
            self.is_playing = False
            self.paused_position = current_pos
            print(f"Set paused_position to: {self.paused_position}")
        else:
            print("Paused -> Playing")
            print(f"Resuming from paused_position: {self.paused_position}")
            # Resume streaming
            if self.client and self.client.connected:
                self.client.sio.emit(
                    "resume_stream",
                    {
                        "room_code": self.client.room_code,
                        "song_index": self.current_song_index,
                        "position": current_pos,
                    },
                )
            self.play_btn.config(text="⏸️")
            self.is_playing = True
            self.stream_start_time = time.time() - self.paused_position
            print(f"Set stream_start_time to: {self.stream_start_time}")
        self.root.update_idletasks()

    def get_current_pos(self):
        """Get current playback position for streaming."""
        if self.is_playing and self.stream_start_time is not None:
            current_pos = time.time() - self.stream_start_time
            # print(f"Playing - current_pos: {current_pos}")
            return current_pos

        # print(f"Paused - paused_position: {self.paused_position}")
        return self.paused_position

    def update_progress(self):
        """Update progress bar for streaming audio."""
        # Don't update progress if user is actively seeking
        if self.is_user_seeking:
            self.root.after(200, self.update_progress)
            return

        current_pos = self.get_current_pos()

        if self.is_playing and current_pos < self.current_duration:
            # Debug: Check if progress bar exists before updating
            if hasattr(self, "progress") and self.progress:
                self.progress.set(current_pos)
            if hasattr(self, "time_label_start") and self.time_label_start:
                self.time_label_start.config(text=self.format_time(current_pos))
        elif current_pos >= self.current_duration and self.current_duration > 0:
            # Song finished, play next
            self.is_playing = False
            if hasattr(self, "play_btn"):
                self.play_btn.config(text="▶")
            self.auto_play_next_from_queue()

        self.root.after(200, self.update_progress)

    def update_progress_bar(self, duration):
        """Update the progress bar with new duration."""
        self.current_duration = duration
        if hasattr(self, "progress_bar"):
            self.progress_bar.config(to=max(duration, 1))
        if hasattr(self, "time_label_end"):
            self.time_label_end.config(text=self.format_time(duration))

    def stop_current_stream(self):
        """Stop the current audio stream."""
        if self.client and self.client.is_streaming:
            print("Stopping current audio stream")
            self.client.stop_audio_stream()
            self.is_playing = False
            if hasattr(self, "play_btn"):
                self.play_btn.config(text="▶")

    def _load_and_play_song(self, idx):
        print(f"_load_and_play_song called with index {idx}")
        if 0 <= idx < len(self.queue_manager.queue):
            item = self.queue_manager.queue[idx]
            if item:
                print(f"Loading song: {item.get('title', item.get('name', 'Unknown'))}")

                self.is_loading = True

                # Only stop current stream if we're switching to a different song
                if self.current_song_index != idx:
                    self.stop_current_stream()

                self.metadata = item
                self.queue_manager.current_idx = idx
                self.current_song_index = idx

                self.player_controller = self.build_player_controller_ui(
                    self.canvas, x=160, y=29, width=230, height=140
                )
                self.canvas.create_window(
                    160,
                    29,
                    anchor="nw",
                    window=self.player_controller,
                    width=220,
                    height=140,
                )

                # Update progress bar with new duration after UI rebuild
                duration = item.get("length", 0)
                print(f"Updating progress bar with duration: {duration}s")
                self.update_progress_bar(duration)

                self.progress.set(0)
                self.time_label_start.config(text="00:00")
                self.play_btn.config(text="⏸️")
                self.is_playing = True
                self.paused_position = 0
                self.stream_start_time = time.time()

                self.root.after(1000, lambda: setattr(self, "is_loading", False))

                self.root.update_idletasks()

    def play_song_from_queue(self, idx):
        self._load_and_play_song(idx)
        if hasattr(self, "queue_ui") and self.queue_ui:
            self.queue_ui.display_queue()
        print(f"Playing song from queue at index {idx}")
        if self.client:
            self.client.sync_current_index_with_server(idx)
            self.client.sio.emit(
                "play_song",
                {"room_code": self.client.room_code, "song_index": idx},
            )

    def auto_play_next_from_queue(self):
        next_idx = self.queue_manager.current_idx + 1
        if next_idx < len(self.queue_manager.queue):
            self._load_and_play_song(next_idx)

            if hasattr(self, "queue_ui") and self.queue_ui:
                self.queue_ui.display_queue()

            if self.client:
                self.client.sync_current_index_with_server(next_idx)
                self.client.sio.emit(
                    "play_song",
                    {"room_code": self.client.room_code, "song_index": next_idx},
                )

    def prev_song(self):
        prev_idx = self.queue_manager.current_idx - 1
        if prev_idx >= 0:
            self._load_and_play_song(prev_idx)
            if hasattr(self, "queue_ui") and self.queue_ui:
                self.queue_ui.display_queue()

            if self.client:
                self.client.sync_current_index_with_server(prev_idx)
                self.client.sio.emit(
                    "play_song",
                    {"room_code": self.client.room_code, "song_index": prev_idx},
                )

    def next_song(self):
        self.auto_play_next_from_queue()

    def seek(self, val):
        """Debounced seek to position in streaming audio."""
        val = float(val)

        # Don't seek if we're not connected, don't have a current song, or are loading
        if (
            not self.client
            or not self.client.connected
            or self.current_song_index < 0
            or self.is_loading
        ):
            return

        # Set seeking flag to prevent progress updates
        self.is_user_seeking = True

        # Cancel any existing timer
        if self.seek_debounce_timer:
            self.root.after_cancel(self.seek_debounce_timer)

        # Store the current position
        self.last_seek_position = val

        # Set a timer to perform the actual seek after 500ms of no movement
        self.seek_debounce_timer = self.root.after(500, self.perform_seek)

        # Update UI immediately for responsive feel (without sending to server)
        self.update_seek_ui(val)

    def perform_seek(self, toggled=False):
        """Perform the actual seek operation after debounce delay."""
        if not self.client or not self.client.connected or self.current_song_index < 0:
            return

        position = self.last_seek_position
        print(f"Performing debounced seek to {position}s")

        # If we're playing, pause first, then seek, then resume
        was_playing = self.is_playing
        if was_playing:
            self.toggle_play()

        # Send seek event to server
        self.client.sio.emit(
            "seek_stream",
            {
                "room_code": self.client.room_code,
                "song_index": self.current_song_index,
                "position": position,
            },
        )

        # Update local state immediately for responsive UI
        if self.is_playing:
            self.stream_start_time = time.time() - position
        else:
            self.paused_position = position

        # Update progress bar and time label
        self.progress.set(position)
        if hasattr(self, "time_label_start"):
            self.time_label_start.config(text=self.format_time(position))

        # Clear the seeking flag to allow progress updates to resume
        self.is_user_seeking = False

        # If we were playing, resume after a short delay
        if was_playing:
            print("Resuming after seek")
            self.root.after(100, self.toggle_play)

    def update_seek_ui(self, position):
        """Update UI elements during seeking without sending to server."""
        # Update time label immediately for responsive feel
        if hasattr(self, "time_label_start"):
            self.time_label_start.config(text=self.format_time(position))

    def format_time(self, seconds):
        mins = int(seconds) // 60
        secs = int(seconds) % 60
        return f"{mins:02}:{secs:02}"

    def animate_fire(self, frame=0):
        """Animate the fire by cycling through the fire images."""
        if self.fire_images and self.fire_image_id:
            # Cycle through the 3 fire images
            current_frame = frame % len(self.fire_images)
            self.canvas.itemconfig(
                self.fire_image_id, image=self.fire_images[current_frame]
            )
            self.root.update()

        # Continue animation
        self.root.after(200, lambda: self.animate_fire(frame + 1))

    def animate_notes(self, frame=0):
        """Animate the notes by cycling through the notes images."""
        if self.notes_images and self.notes_image_id:
            current_frame = frame % len(self.notes_images)
            self.canvas.itemconfig(
                self.notes_image_id, image=self.notes_images[current_frame]
            )
            self.root.update()
        self.root.after(200, lambda: self.animate_notes(frame + 1))

    def add_player(self, username, color_idx, position_idx):
        """Add a player to the room."""
        from custom_classes.custom_color import Color

        color = Color(color_idx)
        player = {
            "username": username,
            "color": color,
            "position_idx": position_idx,
            "canvas_id": None,
            "text_id": None,
        }

        # Add player to the list
        self.players.append(player)

        self.render_player(player)
        print(f"Added player {username} at position {position_idx}")

    def remove_player(self, username):
        """Remove a player from the room."""
        for i, player in enumerate(self.players):
            if player["username"] == username:
                # Remove from canvas
                if player["canvas_id"]:
                    self.canvas.delete(player["canvas_id"])
                if player["text_id"]:
                    self.canvas.delete(player["text_id"])
                # Remove from list
                self.players.pop(i)
                print(f"Removed player {username}")
                break

    def update_remote_talking_state(self, username, is_talking):
        # Find the player by username
        for player in self.players:
            if player.get("username") == username:
                player["is_talking"] = is_talking
                # Remove old image/text
                if player.get("canvas_id"):
                    self.canvas.delete(player["canvas_id"])
                if player.get("text_id"):
                    self.canvas.delete(player["text_id"])
                # Re-render with new mouth state
                self.render_player(player)
                break

    def render_player(self, player):
        """Render a player on the canvas."""
        position_idx = player["position_idx"]
        color = player["color"]

        # Get canvas coordinates
        if position_idx * 2 + 1 < len(self.player_positions):
            x = self.player_positions[position_idx * 2]
            y = self.player_positions[position_idx * 2 + 1]
        else:
            print(f"Position {position_idx} out of range")
            return

        # Get relative position for image selection
        rel_pos = self.position_mapping.get(position_idx, 0)
        if rel_pos < 0:
            image_type = "L"  # Left
        else:
            image_type = "R"  # Right

        # Determine mouth state for local user or remote
        is_local = player.get("username") == self.local_username
        # For remote, use player['is_talking'] if present
        if is_local:
            mouth = "O" if self.is_talking else "C"
        else:
            mouth = "O" if player.get("is_talking", False) else "C"
        image_name = f"H{image_type}{mouth}{color.color_index + 1}"
        # image_path = (
        #     f"assets/players/{color.color_name}/{image_name}-removebg-preview.png"
        # )
        image_path = f"assets/allplayers/{image_name}.png"

        try:
            # Load and cache image
            if image_path not in self.player_images:
                img = Image.open(image_path)
                self.player_images[image_path] = ImageTk.PhotoImage(img)

            # Create image on canvas
            player["canvas_id"] = self.canvas.create_image(
                x, y, anchor="nw", image=self.player_images[image_path]
            )

            # Create username text above the player
            # Position text above the player image (assuming player images are roughly 100px tall)
            if image_type == "L":
                text_x = x + 40  # Center horizontally on the player
            else:
                text_x = x + 50  # Center horizontally on the player
            text_y = y - 10  # Position above the player
            player["text_id"] = self.canvas.create_text(
                text_x,
                text_y,
                text=player["username"],
                fill="#D3D3D3",  # Light gray color
                font=("Helvetica", 10, "bold"),
                anchor="s",  # Anchor at bottom so text appears above player
            )

            # print(
            #     f"Rendered {player['username']} at ({x}, {y}) with image {image_name}"
            # )

        except Exception as e:
            print(f"Error rendering player {player['username']}: {e}")

    def update_players(self, players_data):
        """Update all players based on server data."""
        print(f"AudioPlayerScreen: Updating players with data: {players_data}")
        print(f"AudioPlayerScreen: Current players count: {len(self.players)}")

        # Clear existing players
        for player in self.players:
            if player["canvas_id"]:
                self.canvas.delete(player["canvas_id"])
            if player["text_id"]:
                self.canvas.delete(player["text_id"])
        self.players.clear()
        print(f"AudioPlayerScreen: Cleared existing players")

        # Add new players using their actual positions from server
        for player_data in players_data:
            position = player_data.get("position", 0)
            print(
                f"AudioPlayerScreen: Adding player {player_data['username']} at position {position}"
            )
            self.add_player(player_data["username"], player_data["color_idx"], position)

        print(f"AudioPlayerScreen: Final players count: {len(self.players)}")

    def get_local_player(self):
        self.local_username = getattr(self.client, "username", None)
        if not self.local_username:
            return None
        for player in self.players:

            if player.get("username") == self.local_username:

                return player
        return None

    def _on_voice_state_change(self, is_talking):
        self.is_talking = is_talking
        # Redraw local player with new mouth state
        self._update_local_player_mouth()
        # Emit talking state to server for relay
        if (
            self.client
            and hasattr(self.client, "sio")
            and self.client.room_code
            and self.local_username
        ):
            self.client.sio.emit(
                "user_talking_state",
                {
                    "room_code": self.client.room_code,
                    "username": self.local_username,
                    "is_talking": int(is_talking),
                },
            )

    def _update_local_player_mouth(self):
        # Find local user by username
        player = self.get_local_player()
        if player:
            if player.get("canvas_id"):
                self.canvas.delete(player["canvas_id"])
            if player.get("text_id"):
                self.canvas.delete(player["text_id"])
            self.render_player(player)

    def toggle_mic(self):
        self.is_muted = not self.is_muted
        if self.is_muted:
            self.mic_btn.config(text="🔇")  # Muted icon
            self.stop_voice_stream()
        else:
            self.mic_btn.config(text="🎤")  # Unmuted icon
            self.start_voice_stream()

    def start_voice_stream(self):
        if self.voice_streaming:
            return
        self.voice_streaming = True
        self.voice_stream_thread = threading.Thread(
            target=self._voice_stream_loop, daemon=True
        )
        self.voice_stream_thread.start()

    def stop_voice_stream(self):
        self.voice_streaming = False
        if self.mic_stream:
            try:
                self.mic_stream.stop_stream()
                self.mic_stream.close()
            except Exception:
                pass
            self.mic_stream = None
        if self.pyaudio_instance:
            try:
                self.pyaudio_instance.terminate()
            except Exception:
                pass
            self.pyaudio_instance = None

    def _voice_stream_loop(self):
        # Basic: capture mic and emit to server
        try:
            self.pyaudio_instance = pyaudio.PyAudio()
            self.mic_stream = self.pyaudio_instance.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=16000,
                input=True,
                frames_per_buffer=1024,
            )
            while self.voice_streaming:
                data = self.mic_stream.read(1024, exception_on_overflow=False)
                if (
                    self.client
                    and hasattr(self.client, "sio")
                    and self.client.sio.connected
                ):
                    # Send as binary (could also base64 encode if needed)
                    self.client.sio.emit("voice_data", {"data": data})
        except Exception as e:
            print(f"Voice stream error: {e}")
        finally:
            if self.mic_stream:
                try:
                    self.mic_stream.stop_stream()
                    self.mic_stream.close()
                except Exception:
                    pass
                self.mic_stream = None
            if self.pyaudio_instance:
                try:
                    self.pyaudio_instance.terminate()
                except Exception:
                    pass
                self.pyaudio_instance = None

    def play_incoming_voice(self, data):
        # Add received audio data to the playback queue
        if data:
            self.voice_playback_queue.put(data)
            if not self.voice_playback_running:
                self.start_voice_playback()

    def start_voice_playback(self):
        if self.voice_playback_running:
            return
        self.voice_playback_running = True
        self.voice_playback_thread = threading.Thread(
            target=self._voice_playback_loop, daemon=True
        )
        self.voice_playback_thread.start()

    def stop_voice_playback(self):
        self.voice_playback_running = False
        if self.voice_output_stream:
            try:
                self.voice_output_stream.stop_stream()
                self.voice_output_stream.close()
            except Exception:
                pass
            self.voice_output_stream = None

    def _voice_playback_loop(self):
        try:
            p = pyaudio.PyAudio()
            self.voice_output_stream = p.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=16000,
                output=True,
                frames_per_buffer=1024,
            )
            while self.voice_playback_running:
                try:
                    data = self.voice_playback_queue.get(timeout=0.5)
                    if data:
                        self.voice_output_stream.write(data)
                except queue.Empty:
                    continue
        except Exception as e:
            print(f"Voice playback error: {e}")
        finally:
            if self.voice_output_stream:
                try:
                    self.voice_output_stream.stop_stream()
                    self.voice_output_stream.close()
                except Exception:
                    pass
                self.voice_output_stream = None
            self.voice_playback_running = False

    def on_close(self):
        # Disconnect client if possible, then destroy window
        try:
            if (
                self.client is not None
                and hasattr(self.client, "sio")
                and self.client.sio.connected
            ):
                self.client.sio.disconnect()
        except Exception as e:
            print(f"Error during disconnect: {e}")
        if hasattr(self, "voice_detector"):
            self.voice_detector.stop()
        self.stop_voice_stream()
        self.stop_voice_playback()
        self.root.destroy()
