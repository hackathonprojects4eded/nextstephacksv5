import re
import tkinter as tk
from utils.song import cover_photo
from .constants import *

# ponytail: only the latest 50 past songs (fetch_cover caches 256 covers); page them if
# anyone wants to scroll further back
MAX_PAST_SONGS = 50
TITLES = {
    "queue": "FJ Radio - Next in Queue",
    "past": "FJ Radio - Past Songs",
    "playlist": "FJ Radio - Playlist",
}
PLAYLIST_LINK = re.compile(
    r"(?:https?://)?(?:(?:www|m|music)\.)?youtube\.com/\S*[?&]list="
    r"|(?:https?://)?open\.spotify\.com/(?:intl-[a-z-]+/)?(?:playlist|album)/",
    re.I,
)


def is_playlist_link(text):
    """A YouTube playlist link (list=, no v=) or a Spotify playlist or album link.
    A song in a playlist (watch?v=…&list=…, youtu.be/…?list=…) stays one song."""
    text = text.strip()
    return bool(PLAYLIST_LINK.match(text)) and not re.search(r"[?&]v=", text)


def shorten(text, chars):
    return text if len(text) <= chars else text[: chars - 3] + "..."


class FireSideRadioQueueUI:
    """
    What's up next in the jam, what played before, and playlists to pick songs from.
    Callbacks get a song's `key`, the add box text, or playlist songs' texts.
    """

    def __init__(
        self,
        queue,
        master=None,
        on_thumbnail_click=None,
        on_add_url=None,
        on_shuffle_queue=None,
        on_remove=None,
        history=(),
        on_move=None,
        on_playlist=None,
        on_add_many=None,
        on_error=None,
    ):
        self.on_thumbnail_click = on_thumbnail_click
        self.on_add_url = on_add_url
        self.on_shuffle_queue = on_shuffle_queue
        self.on_remove = on_remove
        self.on_move = on_move  # (key, index into the upcoming songs)
        self.on_playlist = on_playlist  # (link, callback): looks a playlist up
        self.on_add_many = on_add_many  # (texts)
        self.on_error = on_error  # (message)
        self.view = "queue"  # or "past" or "playlist"
        self.drag = None  # the queued song being dragged
        self.playlist = None  # what the playlist view shows; None when it's closed
        self.win = tk.Toplevel(master)
        self.win.geometry("200x300")
        self.win.configure(bg=WOOD_COLOR)
        self.win.overrideredirect(True)  # Remove OS top bar
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
            text=TITLES["queue"],
            bg="#5A2B1A",
            fg="white",
            font=("Helvetica", 9, "bold"),
        )
        self.title_label.pack(side=tk.LEFT, padx=(8, 0))
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
        self.past_btn = tk.Button(  # switches between up next and past songs
            self.top_bar,
            text="🕘",
            command=self.toggle_past,
            bg="#5A2B1A",
            fg="white",
            bd=0,
            font=("Helvetica", 10),
            activebackground="#7C3F30",
            activeforeground="white",
            highlightthickness=0,
            takefocus=0,
        )
        self.past_btn.pack(side=tk.RIGHT)
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
        self.shown_keys = None
        self.display_queue(queue, history)
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
        if url and is_playlist_link(url) and self.on_playlist:
            self.url_var.set("")
            self.open_playlist(url)
        elif url and hasattr(self, "on_add_url") and self.on_add_url:
            self.on_add_url(url)
            print("url added to queue")
            self.url_var.set("")

    def handle_shuffle_queue(self):
        """Handle shuffle queue button click."""
        if hasattr(self, "on_shuffle_queue") and self.on_shuffle_queue:
            self.on_shuffle_queue()

    def display_queue(self, queue, history=()):
        """The jam's upcoming and played songs. Redraws only the view showing, if it changed."""
        self.queue = list(queue)  # our own copy: a drop reorders it
        self.history = list(history)[::-1][:MAX_PAST_SONGS]  # newest first
        if self.view != "playlist":
            self.show_list()

    def show_list(self):
        """Draw the upcoming or the past songs, whichever view is on."""
        past = self.view == "past"
        items = self.history if past else self.queue
        keys = [item["key"] for item in items]
        if keys == self.shown_keys:
            return  # unchanged: skip the redraw and keep the scroll position
        self.shown_keys = keys
        self.clear_list()
        self.rows = [self.create_list_tile(item["key"], item, past) for item in items]

    def clear_list(self):
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        self.thumbnail_images = []
        self.rows = []
        self.drag = None  # its row is gone
        self.marker = tk.Frame(self.scrollable_frame, bg="white", height=2)  # drop spot

    def set_view(self, view):
        """Show "queue" (up next), "past" (played, newest first) or "playlist"."""
        self.view = view
        self.title_label.config(text=TITLES[view])
        if view != "playlist":
            self.playlist = None  # closing it drops a lookup still on its way
            self.shown_keys = None
            self.show_list()
        self.canvas.yview_moveto(0)

    def toggle_past(self):
        self.set_view("queue" if self.view == "past" else "past")

    def create_list_tile(self, key, item, past=False):
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
        thumb_img = cover_photo(item.get("cover_url"), 40)
        thumb_label.config(image=thumb_img)
        self.thumbnail_images.append(thumb_img)
        title = item.get("title", "")
        author = item.get("artist", "")
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
        play_icon.bind("<Button-1>", lambda e, k=key: self.handle_thumbnail_click(k))
        overlay.bind("<Button-1>", lambda e, k=key: self.handle_thumbnail_click(k))
        if past:
            return row  # played already: no reordering or removing
        # Drag the row (not its thumbnail or ⋮) to move the song
        for widget in (row, info_frame, title_label, author_label):
            widget.bind("<ButtonPress-1>", lambda e, k=key: self.drag_start(e, k))
            widget.bind("<B1-Motion>", self.drag_motion)
            widget.bind("<ButtonRelease-1>", self.drag_end)
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
            "<Button-1>", lambda e, k=key, b=menu_btn: self.show_context_menu(e, k, b)
        )
        return row

    def drag_start(self, event, key):
        self.drag = {"key": key, "y": event.y_root, "moved": False}

    def drag_motion(self, event):
        """Past a few pixels, a press becomes a drag: mark where the song would land."""
        if not self.drag:
            return
        if not self.drag["moved"] and abs(event.y_root - self.drag["y"]) < 5:
            return
        self.drag["moved"] = True
        gap = self.drop_gap(event.y_root)
        if gap < len(self.rows):
            y = self.rows[gap].winfo_y() - 3
        else:
            y = self.rows[-1].winfo_y() + self.rows[-1].winfo_height() + 1
        self.marker.place(x=0, y=max(y, 0), relwidth=1, height=2)
        self.marker.lift()

    def drag_end(self, event):
        """Drop: the song moves there now, and the server's next state confirms it."""
        drag, self.drag = self.drag, None
        if not drag or not drag["moved"]:
            return  # a plain click
        self.marker.place_forget()
        keys = [item["key"] for item in self.queue]
        old = keys.index(drag["key"])
        gap = self.drop_gap(event.y_root)
        new = gap - 1 if gap > old else gap
        if new == old:
            return  # dropped where it started
        self.queue.insert(new, self.queue.pop(old))
        self.show_list()  # shown_keys now match the order the server will send
        if self.on_move:
            self.on_move(drag["key"], new)

    def drop_gap(self, y_root):
        """Which gap between rows a drop at screen height y_root lands in (0 = top).
        Screen coordinates, so it works however far the list is scrolled."""
        return sum(r.winfo_rooty() + r.winfo_height() / 2 < y_root for r in self.rows)

    def open_playlist(self, link):
        """The add box got a playlist link: show its songs to pick from."""
        self.playlist = request = {"title": "Loading…", "tracks": []}
        self.added = set()  # indexes of the songs already sent
        self.set_view("playlist")
        self.show_playlist()
        self.on_playlist(link, lambda result: self.playlist_loaded(request, result))

    def playlist_loaded(self, request, result):
        """The server's answer: {"title", "tracks"}, or {"error"} (then back to the queue)."""
        if self.playlist is not request or not self.win.winfo_exists():
            return  # closed, or another link was looked up since
        if result.get("error") or not isinstance(result.get("tracks"), list):
            if self.on_error:
                self.on_error(result.get("error") or "Couldn't read that playlist")
            self.set_view("queue")
            return
        self.playlist = result
        self.show_playlist()

    def show_playlist(self):
        """← back, the playlist's name and Add all, then each song with its own +."""
        self.clear_list()
        tracks = self.playlist["tracks"]
        header = tk.Frame(self.scrollable_frame, bg=WOOD_COLOR)
        header.pack(fill=tk.X, pady=2, padx=4)
        style = dict(
            bg=WOOD_COLOR,
            fg="white",
            bd=0,
            font=("Helvetica", 10),
            activebackground="#5A2B1A",
            activeforeground="white",
            highlightthickness=0,
            takefocus=0,
            cursor="hand2",
        )
        tk.Button(
            header, text="←", command=lambda: self.set_view("queue"), **style
        ).pack(side=tk.LEFT)
        self.add_all_btn = tk.Button(
            header,
            text="Add all",
            font=("Helvetica", 7),
            command=lambda: self.add_tracks(range(len(tracks))),
            bg="white",
            fg="black",
            activebackground="#f0f0f0",
            activeforeground="black",
            bd=0,
            highlightthickness=0,
            relief="flat",
        )
        self.add_all_btn.pack(side=tk.RIGHT, ipadx=4)
        tk.Label(
            header,
            text=shorten(str(self.playlist.get("title", "")), 14),
            width=14,
            anchor="w",
            fg="white",
            bg=WOOD_COLOR,
            font=("Helvetica", 9, "bold"),
        ).pack(side=tk.LEFT, padx=4)
        self.plus_buttons = []
        for i, track in enumerate(tracks):
            row = tk.Frame(self.scrollable_frame, bg=WOOD_COLOR)
            row.pack(fill=tk.X, pady=1, padx=4)
            name = f"{track.get('title', '')} — {track.get('artist', '')}"
            tk.Label(
                row,
                text=shorten(name, 24),
                width=24,
                anchor="w",
                fg="white",
                bg=WOOD_COLOR,
                font=("Helvetica", 9),
            ).pack(side=tk.LEFT)
            plus = tk.Button(row, text="+", command=lambda i=i: self.add_tracks([i]), **style)
            plus.pack(side=tk.RIGHT)
            self.plus_buttons.append(plus)
        self.mark_added()

    def add_tracks(self, indexes):
        """Queue playlist songs (one +, or Add all), each at most once."""
        new = [i for i in indexes if i not in self.added]
        if new and self.on_add_many:
            self.added.update(new)
            self.on_add_many([self.playlist["tracks"][i]["text"] for i in new])
            self.mark_added()

    def mark_added(self):
        """✓ the songs already sent; Add all greys out once they all are."""
        for i in self.added:
            self.plus_buttons[i].config(text="✓", state="disabled")
        if len(self.added) == len(self.plus_buttons):
            self.add_all_btn.config(state="disabled")

    def show_context_menu(self, event, key, btn):
        menu = tk.Menu(self.win, tearoff=0)
        menu.add_command(
            label="Remove from queue", command=lambda: self.remove_from_queue(key)
        )
        menu.tk_popup(event.x_root, event.y_root)

    def remove_from_queue(self, key):
        if self.on_remove:
            self.on_remove(key)

    def handle_thumbnail_click(self, key):
        if self.on_thumbnail_click:
            self.on_thumbnail_click(key)

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

    def show(self):
        self.win.deiconify()
