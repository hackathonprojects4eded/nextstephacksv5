import time
import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageTk
from utils.song import get_random_song_metadata, get_song_metadata, base64_to_image
from .queue_screen import FireSideRadioQueueUI
from .constants import WOOD_ENGRAVING_COLOR


class AudioPlayerScreen:
    def __init__(self, root, client):
        self.root = root
        self.client = client
        self.transparent_color = "black"
        self.root.geometry("550x400")
        self.root.overrideredirect(True)
        self.root.wm_attributes("-transparentcolor", self.transparent_color)
        self.root.wm_attributes("-topmost", True)
        self.root.configure(bg=self.transparent_color)

        self.client.register_audio_player(self)

        # Simple state tracking
        self.is_playing = False
        self.current_song_index = -1
        self.metadata = {}

        # Progress bar state
        self.progress_var = tk.DoubleVar()
        self.is_seeking = False

        # Load fire animation images
        self.fire_images = []
        try:
            for i in range(1, 4):
                fire_img = Image.open(f"assets/fire/Fire_{i}.png")
                fire_img = fire_img.resize((157, 210))
                fire_tk = ImageTk.PhotoImage(fire_img)
                self.fire_images.append(fire_tk)
        except Exception as e:
            print(f"Could not load fire images: {e}")
            self.fire_images = []

        # Player management
        self.players = []
        self.player_positions = [92, 230, 366, 230, 6, 230, 449, 230]
        self.position_mapping = {0: -1, 1: 1, 2: -2, 3: 2}
        self.player_images = {}

        self.build_ui()
        self.root.bind("<KeyPress-space>", lambda event: self.toggle_play())
        self.animate_fire()

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

        # Handle album image
        if self.metadata and self.metadata.get("cover_image"):
            cover_image = self.metadata["cover_image"]
            if isinstance(cover_image, str):
                img = base64_to_image(cover_image)
                if img is None:
                    img = Image.new("RGB", (50, 50), "gray")
            else:
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
            command=self.root.destroy,
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

        # Progress bar and time display
        progress_frame = tk.Frame(frame, bg=bg_color, highlightthickness=0, bd=0)
        progress_frame.pack(fill=tk.X, padx=10, pady=5)

        # Time labels
        self.current_time_label = tk.Label(
            progress_frame,
            text="0:00",
            fg="white",
            bg=bg_color,
            font=("Helvetica", 8),
        )
        self.current_time_label.pack(side=tk.LEFT)

        self.total_time_label = tk.Label(
            progress_frame,
            text="0:00",
            fg="white",
            bg=bg_color,
            font=("Helvetica", 8),
        )
        self.total_time_label.pack(side=tk.RIGHT)

        # Progress bar
        self.progress_bar = tk.Scale(
            progress_frame,
            from_=0,
            to=100,
            orient=tk.HORIZONTAL,
            variable=self.progress_var,
            bg=bg_color,
            fg="white",
            highlightthickness=0,
            bd=0,
            sliderrelief="flat",
            troughcolor="#5A2B1A",
            activebackground="#8B4513",
            command=self.on_progress_change,
        )
        self.progress_bar.pack(fill=tk.X, padx=(30, 30), pady=2)

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

        return frame

    def on_progress_change(self, value):
        """Handle progress bar changes (seeking)."""
        if not self.is_seeking and self.client:
            # Convert percentage to seconds
            duration = self.client.get_song_duration()
            if duration > 0:
                new_position = (float(value) / 100.0) * duration
                self.client.seek_audio(new_position)

    def update_progress(self):
        """Update the progress bar and time display."""
        if not self.client:
            return

        current_pos = self.client.get_current_position()
        duration = self.client.get_song_duration()

        if duration > 0:
            # Update progress bar
            progress_percent = (current_pos / duration) * 100.0
            self.progress_var.set(progress_percent)

            # Update time labels
            current_min = int(current_pos // 60)
            current_sec = int(current_pos % 60)
            self.current_time_label.config(text=f"{current_min}:{current_sec:02d}")

            total_min = int(duration // 60)
            total_sec = int(duration % 60)
            self.total_time_label.config(text=f"{total_min}:{total_sec:02d}")

    def build_fire_radio_button(self):
        points = [306, 347, 334, 351, 339, 374, 303, 371]
        self.trapezoid_id = self.canvas.create_polygon(
            points, fill="#B2B2B2", width=2, tags="fire_radio_btn"
        )
        self.canvas.tag_bind(
            self.trapezoid_id, "<Button-1>", self.open_fire_radio_window
        )

        center_x = sum(points[::2]) / 4 - 2
        center_y = sum(points[1::2]) / 4 - 1

        self.queue_text_id = self.canvas.create_text(
            center_x,
            center_y,
            text="Queue",
            fill=WOOD_ENGRAVING_COLOR,
            font=("Helvetica", 8, "bold"),
            tags="fire_radio_btn",
        )
        self.canvas.tag_bind(
            self.queue_text_id, "<Button-1>", self.open_fire_radio_window
        )

    def open_fire_radio_window(self, event=None):
        self.queue_ui = FireSideRadioQueueUI(
            self.client,
            master=self.root,
            on_thumbnail_click=self.play_song_from_queue,
            on_add_url=lambda url: self.client.add_url_to_queue(url),
            on_shuffle_queue=lambda: self.client.shuffle_queue(),
        )
        # Register the queue UI with the client
        self.client.register_queue_ui(self.queue_ui)
        self.queue_ui.show()

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

        if self.fire_images:
            self.fire_image_id = self.canvas.create_image(
                fire_x, fire_y, anchor="nw", image=self.fire_images[0]
            )
        else:
            self.fire_image_id = None

        # Load and position the box image
        try:
            box_img = Image.open("assets/other/Box.png")
            box_img = box_img.resize((60, 67))
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
        """Toggle play/pause state."""
        if self.client:
            self.client.toggle_play()

    def next_song(self):
        """Play next song."""
        if self.client:
            self.client.next_song()

    def prev_song(self):
        """Play previous song."""
        if self.client:
            self.client.prev_song()

    def play_song_from_queue(self, idx):
        """Play song from queue."""
        if self.client:
            self.client.play_song(idx)

    def load_song_metadata(self, song):
        """Load song metadata and update UI."""
        self.metadata = song
        self.current_song_index = self.client.current_song_index if self.client else -1

        # Rebuild the player controller UI with new metadata
        self.player_controller.destroy()
        self.player_controller = self.build_player_controller_ui(
            self.canvas, x=160, y=29, width=230, height=140
        )
        self.canvas.create_window(
            160, 29, anchor="nw", window=self.player_controller, width=220, height=140
        )

    def animate_fire(self, frame=0):
        """Animate the fire by cycling through the fire images."""
        if self.fire_images and self.fire_image_id:
            current_frame = frame % len(self.fire_images)
            self.canvas.itemconfig(
                self.fire_image_id, image=self.fire_images[current_frame]
            )
            self.root.update()

        self.root.after(200, lambda: self.animate_fire(frame + 1))

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

        self.players.append(player)
        self.render_player(player)
        print(f"Added player {username} at position {position_idx}")

    def remove_player(self, username):
        """Remove a player from the room."""
        for i, player in enumerate(self.players):
            if player["username"] == username:
                if player["canvas_id"]:
                    self.canvas.delete(player["canvas_id"])
                if player["text_id"]:
                    self.canvas.delete(player["text_id"])
                self.players.pop(i)
                print(f"Removed player {username}")
                break

    def render_player(self, player):
        """Render a player on the canvas."""
        position_idx = player["position_idx"]
        color = player["color"]

        if position_idx * 2 + 1 < len(self.player_positions):
            x = self.player_positions[position_idx * 2]
            y = self.player_positions[position_idx * 2 + 1]
        else:
            print(f"Position {position_idx} out of range")
            return

        rel_pos = self.position_mapping.get(position_idx, 0)
        if rel_pos < 0:
            image_type = "L"
        else:
            image_type = "R"

        image_name = f"H{image_type}C{color.color_index + 1}"
        image_path = (
            f"assets/players/{color.color_name}/{image_name}-removebg-preview.png"
        )

        try:
            if image_path not in self.player_images:
                img = Image.open(image_path)
                self.player_images[image_path] = ImageTk.PhotoImage(img)

            player["canvas_id"] = self.canvas.create_image(
                x, y, anchor="nw", image=self.player_images[image_path]
            )

            if image_type == "L":
                text_x = x + 40
            else:
                text_x = x + 50
            text_y = y - 10
            player["text_id"] = self.canvas.create_text(
                text_x,
                text_y,
                text=player["username"],
                fill="#D3D3D3",
                font=("Helvetica", 10, "bold"),
                anchor="s",
            )

            print(
                f"Rendered {player['username']} at ({x}, {y}) with image {image_name}"
            )

        except Exception as e:
            print(f"Error rendering player {player['username']}: {e}")

    def update_players(self, players_data):
        """Update all players based on server data."""
        print(f"AudioPlayerScreen: Updating players with data: {players_data}")

        # Clear existing players
        for player in self.players:
            if player["canvas_id"]:
                self.canvas.delete(player["canvas_id"])
            if player["text_id"]:
                self.canvas.delete(player["text_id"])
        self.players.clear()

        # Add new players using their actual positions from server
        for player_data in players_data:
            position = player_data.get("position", 0)
            print(
                f"AudioPlayerScreen: Adding player {player_data['username']} at position {position}"
            )
            self.add_player(player_data["username"], player_data["color_idx"], position)

        print(f"AudioPlayerScreen: Final players count: {len(self.players)}")
