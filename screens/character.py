import tkinter as tk

from .constants import (
    WOOD_COLOR,
    WOOD_ENGRAVING_COLOR,
    COLOR_HEXS,
    WOOD_ENTER_USERNAME_COLOR,
    nouns,
    adjectives,
)
from custom_classes.custom_color import Color
from .joinhostcode import JoinHostCodeScreen

import random


# Function to generate a random username
def generate_username():
    adj = random.choice(adjectives)
    noun = random.choice(nouns)
    return f"{adj}{noun}"


class CharacterScreen:
    """
    Character selection logic. Handles username and color selection, and navigation to next screen.
    """

    def __init__(self, app, client, is_host, x, y):
        self.app = app
        self.client = client
        self.color = None  # Will be a Color instance
        self.is_host = is_host  # either True (host) or False (join)
        self.transparent_color = "black"
        self.max_char_length = 6
        x = x + 100

        geometry_str = f"250x300+{x}+{y}"
        self.root = tk.Toplevel(app.root) if hasattr(app, "root") else tk.Tk()
        self.root.geometry(geometry_str)
        self.root.configure(bg=self.transparent_color)
        self.root.overrideredirect(True)
        self.root.wm_attributes("-transparentcolor", self.transparent_color)
        self.root.wm_attributes("-topmost", True)

        self._drag_start_pointer_x = 0
        self._drag_start_pointer_y = 0
        self._drag_start_win_x = 0
        self._drag_start_win_y = 0
        self._dragging = False

        self.build_ui()

    def build_ui(self):
        self.canvas = tk.Canvas(
            self.root,
            width=300,
            height=250,
            bg=self.transparent_color,
            highlightthickness=0,
        )
        self.canvas.place(x=0, y=0, relwidth=1, relheight=1)

        # Display the correct background image
        try:
            from PIL import Image, ImageTk
            import os

            if self.is_host:
                bg_path = os.path.join(
                    "assets", "signs", "character_selection_host.png"
                )
            else:
                bg_path = os.path.join("assets", "signs", "character_join_thing.png")

            if os.path.exists(bg_path):
                bg_img = Image.open(bg_path)
                self.bg_img_tk = ImageTk.PhotoImage(bg_img)
                self.canvas.create_image(0, 0, anchor="nw", image=self.bg_img_tk)
            else:
                print(f"Image file not found: {bg_path}")
        except Exception as e:
            print(f"Could not load character screen image: {e}")

        # Close button (top right, inside canvas)
        self.close_btn = tk.Button(
            self.canvas,
            text="❎",
            command=self.root.destroy,
            bg=WOOD_ENGRAVING_COLOR,
            fg="white",
            bd=0,
            font=("Helvetica", 10),
            takefocus=0,
        )
        self.close_btn_window = self.canvas.create_window(
            220, 10, anchor="nw", window=self.close_btn, width=20, height=20
        )

        self.canvas.bind("<Button-1>", self.start_move)
        self.canvas.bind("<B1-Motion>", self.do_move)

        # Username entry box (inside polygon/rectangle)
        # Polygon: [66, 80, 181, 78, 180, 96, 67, 97]
        entry_x = (66 + 181) // 2
        entry_y = (80 + 96) // 2
        self.username_var = tk.StringVar()
        self.username_entry = tk.Entry(
            self.canvas,
            textvariable=self.username_var,
            font=("Helvetica", 12),
            width=10,
            justify="center",
            bg=WOOD_ENTER_USERNAME_COLOR,
            fg="#D3D3D3",
            relief="flat",
            bd=0,
            highlightthickness=0,
        )
        self.username_entry_window = self.canvas.create_window(
            entry_x,
            entry_y,
            anchor="center",
            window=self.username_entry,
            width=110,
            height=22,
        )
        # Note about max char length
        self.canvas.create_text(
            entry_x + 8,
            entry_y + 15,
            text=f"(max {self.max_char_length} chars)",
            fill="gray",
            font=("Helvetica", 7),
            anchor="n",
        )

        # Color selection circles
        color_points = [
            49,
            133,
            78,
            132,
            103,
            133,
            128,
            132,
            150,
            132,
            177,
            132,
            199,
            133,
        ]
        self.color_circles = []
        for i in range(0, len(color_points), 2):
            cx, cy = color_points[i], color_points[i + 1]
            color_hex = COLOR_HEXS[i // 2]
            circle = self.canvas.create_oval(
                cx - 10,
                cy - 10,
                cx + 10,
                cy + 10,
                fill=color_hex,
                outline="#333",
                width=2,
                tags=(f"color_circle_{i//2}",),
            )
            self.canvas.tag_bind(
                circle, "<Button-1>", lambda e, idx=i // 2: self.set_color(idx)
            )
            self.color_circles.append(circle)

        # Draw the correct polygon for host/join
        if self.is_host:
            host_points = [68, 178, 18, 176, 15, 173, 9, 182, 16, 189, 16, 187, 68, 187]
            self.host_arrow = self.canvas.create_polygon(
                host_points, fill=WOOD_COLOR, width=2, tags="host_arrow"
            )
            self.canvas.create_text(
                45,
                183,
                text="Host",
                fill=WOOD_ENGRAVING_COLOR,
                font=("Helvetica", 12, "bold"),
                tags="host_text",
            )
            self.canvas.tag_bind("host_arrow", "<Button-1>", self.on_host)
            self.canvas.tag_bind("host_text", "<Button-1>", self.on_host)
        else:
            join_points = [
                164,
                176,
                226,
                176,
                228,
                173,
                235,
                182,
                226,
                192,
                226,
                187,
                166,
                189,
            ]
            self.join_arrow = self.canvas.create_polygon(
                join_points, fill=WOOD_COLOR, width=2, tags="join_arrow"
            )
            self.canvas.create_text(
                195,
                183,
                text="Join",
                fill=WOOD_ENGRAVING_COLOR,
                font=("Helvetica", 13, "bold"),
                tags="join_text",
            )
            self.canvas.tag_bind("join_arrow", "<Button-1>", self.on_join)
            self.canvas.tag_bind("join_text", "<Button-1>", self.on_join)

    def start_move(self, event):
        self._drag_start_pointer_x = self.root.winfo_pointerx()
        self._drag_start_pointer_y = self.root.winfo_pointery()
        self._drag_start_win_x = self.root.winfo_x()
        self._drag_start_win_y = self.root.winfo_y()
        self._dragging = True

    def do_move(self, event):
        if getattr(self, "_dragging", False):
            dx = self.root.winfo_pointerx() - self._drag_start_pointer_x
            dy = self.root.winfo_pointery() - self._drag_start_pointer_y
            new_x = self._drag_start_win_x + dx
            new_y = self._drag_start_win_y + dy
            self.root.geometry(f"+{new_x}+{new_y}")

    def set_color(self, idx):
        self.color = Color(idx)
        # Optionally, highlight the selected circle
        for i, circle in enumerate(self.color_circles):
            if i == idx:
                self.canvas.itemconfig(circle, width=4, outline="#000")
            else:
                self.canvas.itemconfig(circle, width=2, outline="#333")

    def go_to_joinhostcode_screen(self):
        pass

    def on_join(self, event=None):
        username = self.username_var.get()[: self.max_char_length]
        if len(username) == 0:
            username = generate_username()[: self.max_char_length]
        if not self.color:
            self.color = Color(random.choice(range(0, len(COLOR_HEXS))))

        print(
            f"Join pressed. Username: {username}, Color idx: {self.color.color_index if self.color else None}"
        )
        # Navigate to joinhostcode screen
        x, y = self.root.winfo_x(), self.root.winfo_y()
        self.root.destroy()
        JoinHostCodeScreen(
            self.app,
            self.client,
            is_host=False,
            username=username,
            color=self.color,
            x=x,
            y=y,
        )

    def on_host(self, event=None):
        username = self.username_var.get()[: self.max_char_length]
        if len(username) == 0:
            username = generate_username()[: self.max_char_length]
        if not self.color:
            self.color = Color(random.choice(range(0, len(COLOR_HEXS))))

        print(
            f"Host pressed. Username: {username}, Color idx: {self.color.color_index if self.color else None}"
        )
        # Navigate to loading screen
        x, y = self.root.winfo_x(), self.root.winfo_y()
        self.root.destroy()
        from .loading import LoadingScreen

        LoadingScreen(self.app, self.client, username, self.color, x, y)
