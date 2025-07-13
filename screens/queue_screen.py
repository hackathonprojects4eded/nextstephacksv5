import tkinter as tk
from PIL import Image, ImageTk
import os
from utils.song import get_song_metadata, base64_to_image
from .constants import *
from jams.shared.song_queue import SongQueue
import sys


class FireSideRadioQueueUI:
    def __init__(
        self,
        queue_manager,
        master=None,
        on_thumbnail_click=None,
        on_add_url=None,
        on_shuffle_queue=None,
    ):
        self.queue_manager = queue_manager
        self.on_thumbnail_click = on_thumbnail_click
        self.on_add_url = on_add_url
        self.on_shuffle_queue = on_shuffle_queue
        self.win = tk.Toplevel(master)
        self.win.geometry("200x300")
        self.win.configure(bg=WOOD_COLOR)
        plat = sys.platform
        if plat != "darwin":
            self.win.overrideredirect(True)
        else:
            self.win.title("Queue")
        self.win.wm_attributes("-topmost", True)
        # Center the window over the master (main window)
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
            text="FJ Radio - Next in Queue",
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
        # Dragging support on the top bar
        self.top_bar.bind("<Button-1>", self.start_move)
        self.top_bar.bind("<B1-Motion>", self.do_move)
        self.title_label.bind("<Button-1>", self.start_move)
        self.title_label.bind("<B1-Motion>", self.do_move)
        self._drag_start_pointer_x = 0
        self._drag_start_pointer_y = 0
        self._drag_start_win_x = 0
        self._drag_start_win_y = 0

        # Search bar
        self.build_add_bar()

        # Scrollable content frame for queue
        self.canvas = tk.Canvas(self.win, bg=WOOD_COLOR, highlightthickness=0)
        self.scrollable_frame = tk.Frame(self.canvas, bg=WOOD_COLOR)
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.thumbnail_images = []  # Keep references to avoid garbage collection
        self.display_queue()
        # Bind mouse wheel to scroll
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def set_downloading_state(self):
        """Set the add button to downloading state."""
        if hasattr(self, "add_btn"):
            self.add_btn.config(text="⏬", state="disabled")

    def reset_add_button_state(self):
        """Reset the add button to normal state."""
        if hasattr(self, "add_btn"):
            self.add_btn.config(text="Add", state="normal")

    def _on_mousewheel(self, event):
        # For Windows and MacOS
        if event.delta:
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        # For Linux (event.num == 4/5)
        elif event.num == 4:
            self.canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            self.canvas.yview_scroll(1, "units")

    def build_add_bar(self):
        self.add_bar = tk.Frame(self.win, bg=WOOD_COLOR)
        self.add_bar.pack(side=tk.BOTTOM, fill=tk.X, padx=8, pady=8)

        # Shuffle queue button (left side)
        self.shuffle_btn = tk.Button(
            self.add_bar,
            text="🔀",
            font=("Helvetica", 7),
            width=3,
            height=1,
            command=self.handle_shuffle_queue,
            bg="white",
            fg="black",
            activebackground="#f0f0f0",
            activeforeground="black",
            bd=0,
            highlightthickness=0,
            relief="flat",
        )
        self.shuffle_btn.pack(side=tk.LEFT, ipadx=4, ipady=2, padx=(0, 6), pady=0)

        # URL entry (center)
        self.url_var = tk.StringVar()
        self.url_entry = tk.Entry(
            self.add_bar, textvariable=self.url_var, font=("Helvetica", 10), width=15
        )
        self.url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))

        # Add URL button (right side)
        self.add_btn = tk.Button(
            self.add_bar,
            text="Add",
            font=("Helvetica", 7),  # Slightly smaller font
            width=6,
            height=1,  # Smaller height
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

    def handle_add_url(self):
        url = self.url_var.get().strip()
        print(url)
        if url and hasattr(self, "on_add_url") and self.on_add_url:
            self.on_add_url(url)
            print("url added to queue")
            self.url_var.set("")

    def handle_shuffle_queue(self):
        """Handle shuffle queue button click."""
        if hasattr(self, "on_shuffle_queue") and self.on_shuffle_queue:
            self.on_shuffle_queue()

    def display_queue(self):
        # Clear previous widgets
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()

        start_idx = (
            self.queue_manager.current_idx + 1
            if hasattr(self.queue_manager, "current_idx")
            else 0
        )

        for pp in range(start_idx, len(self.queue_manager.queue)):
            item = self.queue_manager.queue[pp]
            self.create_list_tile(pp, item)

    def create_list_tile(self, idx, item):
        max_title_chars = 13
        max_author_chars = 13
        row = tk.Frame(self.scrollable_frame, bg=WOOD_COLOR, cursor="hand2")
        row.pack(fill=tk.X, pady=2, padx=4)
        # --- Spotify-style thumbnail with overlay and play icon ---
        thumb_container = tk.Frame(row, width=40, height=40, bg=WOOD_COLOR)
        thumb_container.pack_propagate(False)
        thumb_container.pack(side=tk.LEFT, padx=(0, 6))
        thumb_label = tk.Label(thumb_container, bg=WOOD_COLOR)
        thumb_label.place(x=0, y=0, width=40, height=40)
        overlay = tk.Label(thumb_container, bg="#FFFFFF", width=40, height=40)
        overlay.place(x=0, y=0, width=40, height=40)
        overlay.lower()  # Hide overlay by default
        overlay.place_forget()
        play_icon = tk.Label(
            overlay,
            text="     ▶️",
            bg="#FFFFFF",
            fg="black",
            font=("Helvetica", 16),
            bd=0,
        )
        play_icon.place(relx=0.5, rely=0.5, anchor="center", width=40, height=40)
        play_icon.lower()
        play_icon.place_forget()

        def show_overlay(event=None):
            overlay.place(x=0, y=0, width=40, height=40)
            overlay.lift()
            play_icon.place(relx=0.5, rely=0.5, anchor="center", width=40, height=40)
            play_icon.lift()

        def hide_overlay(event=None):
            overlay.place_forget()
            play_icon.place_forget()

        thumb_container.bind("<Enter>", show_overlay)
        thumb_container.bind("<Leave>", hide_overlay)
        thumb_label.bind("<Enter>", show_overlay)
        thumb_label.bind("<Leave>", hide_overlay)
        overlay.bind("<Enter>", show_overlay)
        overlay.bind("<Leave>", hide_overlay)
        play_icon.bind("<Enter>", show_overlay)
        play_icon.bind("<Leave>", hide_overlay)

        # Thumbnail image logic
        title = ""
        author = ""

        # Use metadata from the queue item (from server)
        if item.get("cover_image"):
            # Cover image is base64 string from server, convert back to PIL Image
            try:
                img = base64_to_image(item["cover_image"])
                if img:
                    img = img.resize((40, 40))
                    thumb_img = ImageTk.PhotoImage(img)
                    thumb_label.config(image=thumb_img)
                    self.thumbnail_images.append(thumb_img)
                title = item.get("title", item.get("name", ""))
                author = item.get("artist", "")
            except Exception as e:
                print(f"Error converting base64 image: {e}")
                title = item.get("title", item.get("name", ""))
                author = item.get("artist", "")
        elif "filepath" in item and os.path.exists(item["filepath"]):
            # Fallback: extract from local file
            try:
                meta = get_song_metadata(item["filepath"])
                if meta.get("cover_image"):
                    # Convert base64 back to image
                    img = base64_to_image(meta["cover_image"])
                    if img:
                        img = img.resize((40, 40))
                        thumb_img = ImageTk.PhotoImage(img)
                        thumb_label.config(image=thumb_img)
                        self.thumbnail_images.append(thumb_img)
                title = meta.get("title", "")
                author = meta.get("artist", "")
            except Exception:
                title = os.path.basename(item["filepath"])
                author = "Unknown Artist"
        elif "url" in item:
            thumb_label.config(text="🌐", font=("Helvetica", 7))
            title = "Online Stream"
            author = "DJ Web"
        # Info (title, author)
        info_frame = tk.Frame(row, bg=WOOD_COLOR)
        info_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
        if len(title) > max_title_chars:
            title = title[: max_title_chars - 3] + "..."
        title_label = tk.Label(
            info_frame,
            text=title,
            fg="white",
            bg=WOOD_COLOR,
            font=("Helvetica", 11, "bold"),
            anchor="w",
            justify="left",
        )
        title_label.pack(anchor="w", pady=0, fill="x")
        if len(author) > max_author_chars:
            author = author[: max_author_chars - 3] + "..."
        author_label = tk.Label(
            info_frame,
            text=author,
            fg="gray",
            bg=WOOD_COLOR,
            font=("Helvetica", 9),
            anchor="w",
            justify="left",
        )
        author_label.pack(anchor="w", pady=0, fill="x")
        # Thumbnail click: play and remove
        play_icon.bind("<Button-1>", lambda e, i=idx: self.handle_thumbnail_click(i))
        overlay.bind("<Button-1>", lambda e, i=idx: self.handle_thumbnail_click(i))
        # Three-dot menu button (anchor right)
        menu_btn = tk.Button(
            row,
            text="⋮",
            bg=WOOD_COLOR,
            fg="white",
            bd=0,
            font=("Helvetica", 12),
            activebackground="#5A2B1A",
            activeforeground="white",
            highlightthickness=0,
            takefocus=0,
            cursor="hand2",
        )
        menu_btn.pack(side=tk.RIGHT, padx=(30, 0), anchor="e")
        menu_btn.bind(
            "<Button-1>", lambda e, i=idx, b=menu_btn: self.show_context_menu(e, i, b)
        )

    def show_context_menu(self, event, idx, btn):
        menu = tk.Menu(self.win, tearoff=0)
        menu.add_command(
            label="Remove from queue", command=lambda: self.remove_from_queue(idx)
        )
        menu.tk_popup(event.x_root, event.y_root)

    def remove_from_queue(self, idx):
        self.queue_manager.remove_from_queue(idx)
        # Sync with server if possible
        app = getattr(self, "app", None)
        client = getattr(app, "client", None) if app else None
        if client and hasattr(client, "sync_queue_with_server"):
            client.sync_queue_with_server(self.queue_manager.queue)
        self.display_queue()

    def handle_thumbnail_click(self, idx):
        if self.on_thumbnail_click:
            self.on_thumbnail_click(idx)

        print(f"List thumbnail clicked: {idx}")

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
