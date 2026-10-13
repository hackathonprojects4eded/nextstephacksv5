import time
import tkinter as tk
from PIL import Image, ImageTk
from utils.song import cover_photo
from .queue_screen import FireSideRadioQueueUI
from .constants import WOOD_ENGRAVING_COLOR
from utils.voice_detector import VoiceDetector, dB_to_amplitude
from utils.tkinter_compat import set_window_transparency
import threading
from pydub import AudioSegment
import pyaudio


class AudioPlayerScreen:
    def __init__(self, root, client=None):
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

        # Playback state, mirrored from the server (see render_state)
        self.state = {}
        self.queue_ui = None
        self.is_playing = False
        self.stream_start_time = None
        self.paused_position = 0
        self.current_duration = 0
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

        self.build_ui()
        self.root.bind("<KeyPress-space>", lambda event: self.toggle_play())
        self.update_progress()
        # Start fire sound loop in background thread
        self.start_fire_sound()

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

        self.album_img = cover_photo(None, 50)  # gray until something plays
        self.album_label = tk.Label(
            top_frame, image=self.album_img, bg=bg_color, highlightthickness=0, bd=0
        )
        self.album_label.pack(side=tk.LEFT)
        self.album_label.bind("<Button-1>", self.start_move)
        self.album_label.bind("<B1-Motion>", self.do_move)
        text_frame = tk.Frame(top_frame, bg=bg_color, highlightthickness=0, bd=0)
        text_frame.pack(side=tk.LEFT, padx=10)
        self.title_label = tk.Label(
            text_frame,
            text="",
            fg="white",
            bg=bg_color,
            font=("Helvetica", 10, "bold"),
            anchor="w",
            justify="left",
            wraplength=height,
        )
        self.title_label.pack(anchor="w")
        self.artist_label = tk.Label(
            text_frame,
            text="",
            fg="gray",
            bg=bg_color,
            font=("Helvetica", 9),
            anchor="w",
            justify="left",
            wraplength=height,
        )
        self.artist_label.pack(anchor="w")
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
            command=lambda v: self.time_label_start.config(
                text=self.format_time(float(v))
            ),
            highlightthickness=0,
        )
        self.progress_bar.pack(side=tk.LEFT, padx=5)
        # Seek once the slider is let go, not on every tick of a drag
        self.progress_bar.bind(
            "<ButtonPress-1>", lambda e: setattr(self, "is_user_seeking", True)
        )
        self.progress_bar.bind("<ButtonRelease-1>", self.seek)
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
            self.state.get("queue", []),
            master=self.root,
            on_thumbnail_click=lambda key: self.client.send_jam("jump", key=key),
            on_add_url=self.handle_url_add,
            on_shuffle_queue=lambda: self.client.send_jam("shuffle"),
            on_remove=lambda key: self.client.send_jam("remove", key=key),
        )
        self.queue_ui.show()

    def handle_url_add(self, text):
        """Add a song; the button shows ⏬ until the server has it ready."""
        self.queue_ui.set_downloading_state()
        self.client.send_jam("add", text=text)

    def reset_add_button_state(self):
        """Reset the add button state in the queue UI."""
        if self.queue_ui and self.queue_ui.win.winfo_exists():
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
        """Play/pause the jam. Flips right away; the server's next update confirms it."""
        self.paused_position = self.get_current_pos()
        self.stream_start_time = time.time() - self.paused_position
        self.is_playing = not self.is_playing
        self.play_btn.config(text="⏸️" if self.is_playing else "▶")
        self.client.send_jam("play" if self.is_playing else "pause")

    def get_current_pos(self):
        """Get current playback position, ticking forward between server updates."""
        if self.is_playing and self.stream_start_time is not None:
            return time.time() - self.stream_start_time
        return self.paused_position

    def update_progress(self):
        """Update progress bar between server updates."""
        # Don't update progress if user is actively seeking
        if not self.is_user_seeking:
            current_pos = min(self.get_current_pos(), self.current_duration)
            self.progress.set(current_pos)
            self.time_label_start.config(text=self.format_time(current_pos))
        self.root.after(200, self.update_progress)

    def render_state(self, state, received_at):
        """Show the jam's playback (see Jam.state in jams/jam.py) as of now."""
        track = state.get("track") or {}
        if track.get("cover_url") != (self.state.get("track") or {}).get("cover_url"):
            self.album_img = cover_photo(track.get("cover_url"), 50)
            self.album_label.config(image=self.album_img)
        self.state = state

        max_title_chars = 10
        title = track.get("title", "")
        if len(title) > max_title_chars:
            title = title[: max_title_chars - 3] + "..."
        self.title_label.config(text=title)
        self.artist_label.config(text=track.get("artist", ""))

        self.is_playing = state.get("is_playing", False)
        elapsed = time.time() - received_at if self.is_playing else 0  # e.g. song loading
        self.paused_position = state.get("progress_ms", 0) / 1000 + elapsed
        self.stream_start_time = time.time() - self.paused_position
        self.current_duration = track.get("duration_ms", 0) / 1000
        self.progress_bar.config(to=max(self.current_duration, 1))
        self.time_label_end.config(text=self.format_time(self.current_duration))
        self.play_btn.config(text="⏸️" if self.is_playing else "▶")

        if self.queue_ui and self.queue_ui.win.winfo_exists():
            self.queue_ui.display_queue(state.get("queue", []))

    def prev_song(self):
        self.client.send_jam("previous")

    def next_song(self):
        self.client.send_jam("next")

    def seek(self, event=None):
        """Jump the jam to wherever the slider was let go."""
        self.is_user_seeking = False
        position = self.progress.get()
        self.paused_position = position
        self.stream_start_time = time.time() - position
        self.client.send_jam("seek", position_ms=int(position * 1000))

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

        import random

        sample = random.sample(["H", "A"], k=1)

        # {emotion H/A}{side L/R}{mouth O/C}{color 1-7}; players/ only has happy (H) art
        image_name = f"H{image_type}{mouth}{color.color_index + 1}"
        image_path = (
            f"assets/players/{color.color_name}/{image_name}-removebg-preview.png"
        )

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

    def start_fire_sound(self):
        """Start looping fire sound in a background thread."""
        self._fire_sound_stop_event = threading.Event()
        self._fire_sound_thread = threading.Thread(
            target=self._play_fire_sound_loop, daemon=True
        )
        self._fire_sound_thread.start()

    def _play_fire_sound_loop(self):
        try:
            fire_sound = AudioSegment.from_mp3("assets/fire-sound.mp3")
            p = pyaudio.PyAudio()
            stream = p.open(
                format=p.get_format_from_width(fire_sound.sample_width),
                channels=fire_sound.channels,
                rate=fire_sound.frame_rate,
                output=True,
            )
            raw_data = fire_sound.raw_data
            while not self._fire_sound_stop_event.is_set():
                stream.write(raw_data)
            stream.stop_stream()
            stream.close()
            p.terminate()
        except Exception as e:
            print(f"Error playing fire sound: {e}")

    def stop_fire_sound(self):
        """Stop the fire sound loop."""
        if hasattr(self, "_fire_sound_stop_event"):
            self._fire_sound_stop_event.set()

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
        # Stop fire sound loop
        self.stop_fire_sound()
        self.root.destroy()
