import time
import tkinter as tk
from PIL import Image, ImageTk
import threading
from pydub import AudioSegment
import pyaudio
from queue_song import QueueSong


class FireRadioScreen:
    def __init__(self, root):
        self.root = root
        self.transparent_color = "black"
        self.root.geometry("250x250")
        self.root.overrideredirect(True)
        self.root.wm_attributes("-topmost", True)

        self.root.configure(bg=self.transparent_color)
        self.root.wm_attributes("-transparentcolor", self.transparent_color)

        # Initialize queue
        self.queue_manager = QueueSong()

        # Load fire animation images
        self.fire_images = []
        try:
            for i in range(1, 4):
                fire_img = Image.open(f"../assets/fire/Fire_{i}.png")
                fire_tk = ImageTk.PhotoImage(fire_img)
                self.fire_images.append(fire_tk)
        except Exception as e:
            print(f"Could not load fire images: {e}")
            self.fire_images = []

        # Load notes animation images
        self.notes_images = []
        try:
            for i in range(1, 4):
                notes_img = Image.open(f"../assets/notes/crop/Notes_{i}.png")
                notes_tk = ImageTk.PhotoImage(notes_img)
                self.notes_images.append(notes_tk)
        except Exception as e:
            print(f"Could not load notes images: {e}")
            self.notes_images = []

        self.box_img = None
        try:
            self.box_img = Image.open("../assets/other/Box.png")
            self.box_img = self.box_img.resize((60, 67))
        except Exception as e:
            print(f"Could not load box image: {e}")

        self.build_ui()

        # Start fire sound loop in background thread
        self.start_fire_sound()

        # Start animations
        self.animate_fire()
        self.animate_notes()

    def build_ui(self):
        self.canvas = tk.Canvas(
            self.root,
            width=250,
            height=250,
            highlightthickness=0,
            bg=self.transparent_color,
        )
        self.canvas.place(x=0, y=0, relwidth=1, relheight=1)

        # Position fire at center-left
        fire_x = 40
        fire_y = 25

        # Create fire image on canvas
        if self.fire_images:
            self.fire_image_id = self.canvas.create_image(
                fire_x, fire_y, anchor="nw", image=self.fire_images[0]
            )
        else:
            self.fire_image_id = None

        radio_x = fire_x + 110
        radio_y = fire_y + 130

        if self.box_img:
            self.box_img_tk = ImageTk.PhotoImage(self.box_img)
            self.canvas.create_image(
                radio_x, radio_y, anchor="nw", image=self.box_img_tk
            )

        self.build_radio_button()

        notes_x = 150
        notes_y = 110

        # Create notes image at top-right
        if self.notes_images:
            self.notes_image_id = self.canvas.create_image(
                notes_x, notes_y, anchor="nw", image=self.notes_images[0]
            )
        else:
            self.notes_image_id = None

        close_btn = tk.Button(
            self.canvas,
            text="❎",
            command=self.on_close,
            bg="#7C3F30",
            fg="white",
            bd=0,
            font=("Helvetica", 7),
            activebackground="#ff5555",
            activeforeground="white",
            highlightthickness=0,
            takefocus=0,
        )
        self.canvas.create_window(
            radio_x + 40, radio_y + 58, anchor="nw", window=close_btn
        )

        # Add drag functionality to the canvas
        self.canvas.bind("<Button-1>", self.start_move)
        self.canvas.bind("<B1-Motion>", self.do_move)

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

    def build_radio_button(self):

        dx = -148
        dy = -158
        points = [(306, 347), (334, 351), (339, 374), (303, 371)]
        for i in range(len(points)):
            points[i] = (points[i][0] + dx, points[i][1] + dy)

        actual_points = []
        for point in points:
            actual_points.append(point[0])
            actual_points.append(point[1])

        self.radio_polygon_id = self.canvas.create_polygon(
            actual_points, fill="#B2B2B2", width=2, tags="radio_btn"
        )
        self.canvas.tag_bind(
            self.radio_polygon_id, "<Button-1>", self.open_queue_window
        )

        # Calculate center of trapezoid for text positioning
        center_x = sum(actual_points[::2]) / 4
        center_y = sum(actual_points[1::2]) / 4

        # Add "Queue" text in the center of the trapezoid
        self.queue_text_id = self.canvas.create_text(
            center_x,
            center_y,
            text="Queue",
            fill="#8B4513",  # Brown color
            font=("Helvetica", 8, "bold"),
            tags="radio_btn",
        )
        # Bind the text to the same click event
        self.canvas.tag_bind(self.queue_text_id, "<Button-1>", self.open_queue_window)

    def open_queue_window(self, event=None):
        """Open the queue window when radio button is clicked."""
        # Only open if not already open
        if hasattr(self, "queue_ui") and self.queue_ui is not None:
            try:
                if self.queue_ui.win.winfo_exists():
                    self.queue_ui.win.deiconify()
                    self.queue_ui.win.lift()
                    self.queue_ui.win.focus_force()
                    return
            except Exception:
                pass
        self.queue_ui = QueueSongUI(
            self.queue_manager,
            master=self.root,
            on_thumbnail_click=self.play_song_from_queue,
            on_add_url=lambda url: self.handle_url_add(url),
        )
        self.queue_ui.show()
        # When the window is closed, set self.queue_ui to None
        self.queue_ui.win.protocol("WM_DELETE_WINDOW", self._on_queue_ui_close)

    def _on_queue_ui_close(self):
        if hasattr(self, "queue_ui") and self.queue_ui is not None:
            try:
                self.queue_ui.win.destroy()
            except Exception:
                pass
            self.queue_ui = None

    def handle_url_add(self, url):
        """Handle URL addition to queue."""
        if self.queue_ui:
            self.queue_ui.set_downloading_state()
            self.queue_manager.add_url_to_queue(url)
            self.queue_ui.reset_add_button_state()

    def play_song_from_queue(self, idx):
        """Play song from queue at given index."""
        print(f"Playing song from queue at index {idx}")
        # Here you would implement actual song playing logic
        # For now, just print the song info
        if 0 <= idx < len(self.queue_manager.queue):
            song = self.queue_manager.queue[idx]
            print(f"Playing: {song.get('title', 'Unknown')}")

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

    def start_fire_sound(self):
        """Start looping fire sound in a background thread."""
        self._fire_sound_stop_event = threading.Event()
        self._fire_sound_thread = threading.Thread(
            target=self._play_fire_sound_loop, daemon=True
        )
        self._fire_sound_thread.start()

    def _play_fire_sound_loop(self):
        try:
            fire_sound = AudioSegment.from_mp3("../assets/fire-sound.mp3")
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
        """Handle window close event."""
        self.stop_fire_sound()
        self.root.destroy()


class QueueSongUI:
    def __init__(
        self, queue_manager, master=None, on_thumbnail_click=None, on_add_url=None
    ):
        self.queue_manager = queue_manager
        self.on_thumbnail_click = on_thumbnail_click
        self.on_add_url = on_add_url
        self.win = tk.Toplevel(master)
        self.win.geometry("200x300")
        self.win.configure(bg="#8B4513")  # Brown background
        self.win.overrideredirect(True)
        self.win.wm_attributes("-topmost", True)

        # Center the window over the master
        if master is not None:
            master.update_idletasks()
            master_x = master.winfo_rootx()
            master_y = master.winfo_rooty()
            master_w = master.winfo_width()
            master_h = master.winfo_height()
            win_w, win_h = 200, 300
            x = master_x + (master_w - win_w) // 2
            y = master_y + (master_h - win_h) // 2
            self.win.geometry(f"{win_w}x{win_h}+{x}+{y}")

        # Custom top bar
        self.top_bar = tk.Frame(self.win, bg="#5A2B1A", height=28)
        self.top_bar.pack(fill=tk.X, side=tk.TOP)
        self.top_bar.pack_propagate(False)

        self.title_label = tk.Label(
            self.top_bar,
            text="Fire Radio - Queue",
            bg="#5A2B1A",
            fg="white",
            font=("Helvetica", 9, "bold"),
        )
        self.title_label.pack(side=tk.LEFT, padx=8)

        self.close_btn = tk.Button(
            self.top_bar,
            text="❎",
            command=self.win.destroy,
            bg="#5A2B1A",
            fg="white",
            bd=0,
            font=("Helvetica", 10),
            activebackground="#a94442",
            activeforeground="white",
            highlightthickness=0,
            takefocus=0,
        )
        self.close_btn.pack(side=tk.RIGHT, padx=4)

        # Add drag functionality to the top bar and title label
        self.top_bar.bind("<Button-1>", self.start_move)
        self.top_bar.bind("<B1-Motion>", self.do_move)
        self.title_label.bind("<Button-1>", self.start_move)
        self.title_label.bind("<B1-Motion>", self.do_move)

        # Add URL bar
        self.build_add_bar()

        # Queue display
        self.canvas = tk.Canvas(self.win, bg="#8B4513", highlightthickness=0)
        self.scrollable_frame = tk.Frame(self.canvas, bg="#8B4513")
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.display_queue()

    def start_move(self, event):
        self._drag_start_pointer_x = self.win.winfo_pointerx()
        self._drag_start_pointer_y = self.win.winfo_pointery()
        self._drag_start_win_x = self.win.winfo_x()
        self._drag_start_win_y = self.win.winfo_y()

    def do_move(self, event):
        dx = self.win.winfo_pointerx() - self._drag_start_pointer_x
        dy = self.win.winfo_pointery() - self._drag_start_pointer_y
        new_x = self._drag_start_win_x + dx
        new_y = self._drag_start_win_y + dy
        self.win.geometry(f"+{new_x}+{new_y}")

    def build_add_bar(self):
        self.add_bar = tk.Frame(self.win, bg="#8B4513")
        self.add_bar.pack(side=tk.BOTTOM, fill=tk.X, padx=8, pady=8)

        # URL entry
        self.url_var = tk.StringVar()
        self.url_entry = tk.Entry(
            self.add_bar, textvariable=self.url_var, font=("Helvetica", 10), width=15
        )
        self.url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))

        # Add URL button
        self.add_btn = tk.Button(
            self.add_bar,
            text="Add",
            font=("Helvetica", 7),
            width=6,
            height=1,
            command=self.handle_add_url,
            bg="white",
            fg="black",
            activebackground="#f0f0f0",
            activeforeground="black",
            bd=0,
            highlightthickness=0,
            relief="flat",
        )
        self.add_btn.pack(side=tk.LEFT, ipadx=8, ipady=2, padx=(0, 0), pady=0)

    def set_downloading_state(self):
        """Set the add button to downloading state."""
        if hasattr(self, "add_btn"):
            self.add_btn.config(text="⏬", state="disabled")

    def reset_add_button_state(self):
        """Reset the add button to normal state."""
        if hasattr(self, "add_btn"):
            self.add_btn.config(text="Add", state="normal")

    def handle_add_url(self):
        url = self.url_var.get().strip()
        if url and hasattr(self, "on_add_url") and self.on_add_url:
            self.on_add_url(url)
            self.url_var.set("")
            self.display_queue()

    def display_queue(self):
        # Clear previous widgets
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()

        for idx, item in enumerate(self.queue_manager.queue):
            self.create_list_item(idx, item)

    def create_list_item(self, idx, item):
        row = tk.Frame(self.scrollable_frame, bg="#8B4513", cursor="hand2")
        row.pack(fill=tk.X, pady=2, padx=4)

        # Title
        title = item.get("title", item.get("name", "Unknown"))
        if len(title) > 20:
            title = title[:17] + "..."

        title_label = tk.Label(
            row,
            text=title,
            bg="#8B4513",
            fg="white",
            font=("Helvetica", 10, "bold"),
            anchor="w",
        )
        title_label.pack(fill=tk.X, padx=5)

        # Artist
        artist = item.get("artist", "Unknown Artist")
        if len(artist) > 20:
            artist = artist[:17] + "..."

        artist_label = tk.Label(
            row,
            text=artist,
            bg="#8B4513",
            fg="#D3D3D3",
            font=("Helvetica", 9),
            anchor="w",
        )
        artist_label.pack(fill=tk.X, padx=5)

        # Bind click event
        row.bind("<Button-1>", lambda e, idx=idx: self.handle_item_click(idx))
        title_label.bind("<Button-1>", lambda e, idx=idx: self.handle_item_click(idx))
        artist_label.bind("<Button-1>", lambda e, idx=idx: self.handle_item_click(idx))

    def handle_item_click(self, idx):
        """Handle click on queue item."""
        if self.on_thumbnail_click:
            self.on_thumbnail_click(idx)

    def show(self):
        """Show the queue window."""
        self.win.deiconify()
        self.win.focus_force()
