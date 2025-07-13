import tkinter as tk
from .constants import WOOD_COLOR, WOOD_ENGRAVING_COLOR
from .character import CharacterScreen
from utils.tkinter_compat import set_window_transparency


class LandingScreen:
    """
    Landing page logic for the app. Handles navigation to join/host and next screen.
    """

    def __init__(self, app):
        self.app = app  # Reference to main app or navigation controller

        self.transparent_color = "black"

        # Calculate position: 320px to the right and 50px down from center of app.root
        if hasattr(app, "root"):
            app_root = app.root
            app_root.update_idletasks()
            app_x = app_root.winfo_x()
            app_y = app_root.winfo_y()
            app_w = app_root.winfo_width()
            app_h = app_root.winfo_height()
            landing_w, landing_h = 250, 300
            center_x = app_x + app_w // 2
            center_y = app_y + app_h // 2
            landing_x = center_x - landing_w // 2 + 320
            landing_y = center_y - landing_h // 2 + 50
            geometry_str = f"{landing_w}x{landing_h}+{landing_x}+{landing_y}"
        else:
            geometry_str = "250x300"

        self.root = tk.Toplevel(app.root) if hasattr(app, "root") else tk.Tk()
        self.root.geometry(geometry_str)
        self.root.configure(bg=self.transparent_color)
        set_window_transparency(self.root, color=self.transparent_color, alpha=0.8)
        self.root.overrideredirect(True)
        self.root.wm_attributes("-topmost", True)

        # Window move support
        self._drag_start_pointer_x = 0
        self._drag_start_pointer_y = 0
        self._drag_start_win_x = 0
        self._drag_start_win_y = 0
        self._dragging = False

        self.build_ui()

    def build_ui(self):
        # Canvas for everything
        self.canvas = tk.Canvas(
            self.root,
            width=300,
            height=250,
            bg=self.transparent_color,
            highlightthickness=0,
        )
        self.canvas.place(x=0, y=0, relwidth=1, relheight=1)

        # Display the title screen image at the top-left
        try:
            from PIL import Image, ImageTk

            title_img = Image.open("assets/signs/title_screen.png")
            self.title_img_tk = ImageTk.PhotoImage(title_img)
            self.canvas.create_image(0, 0, anchor="nw", image=self.title_img_tk)
        except Exception as e:
            print(f"Could not load title image: {e}")

        # Close button (top right, inside canvas)
        self.close_btn = tk.Button(
            self.canvas,
            text="❎",
            command=self.on_close,
            bg=WOOD_ENGRAVING_COLOR,
            fg="white",
            bd=0,
            font=("Helvetica", 10),
            takefocus=0,
        )
        self.close_btn_window = self.canvas.create_window(
            220, 10, anchor="nw", window=self.close_btn, width=20, height=20
        )

        # Bind window move to top area (top 40px)
        self.canvas.bind("<Button-1>", self.start_move)
        self.canvas.bind("<B1-Motion>", self.do_move)

        # Host arrow (left, above)
        host_points = [152, 137, 84, 138, 84, 134, 71, 145, 83, 157, 83, 152, 152, 152]
        self.host_arrow = self.canvas.create_polygon(
            host_points, fill=WOOD_COLOR, width=2, tags="host_arrow"
        )
        self.canvas.create_text(
            120,
            145,
            text="Host",
            fill=WOOD_ENGRAVING_COLOR,
            font=("Helvetica", 13, "bold"),
            tags="host_text",
        )
        self.canvas.tag_bind("host_arrow", "<Button-1>", self.on_host)
        self.canvas.tag_bind("host_text", "<Button-1>", self.on_host)

        # Join arrow (right, below)
        join_points = [
            105,
            168,
            171,
            171,
            172,
            165,
            183,
            175,
            173,
            187,
            173,
            182,
            107,
            181,
        ]
        self.join_arrow = self.canvas.create_polygon(
            join_points, fill=WOOD_COLOR, width=2, tags="join_arrow"
        )
        self.canvas.create_text(
            140,
            177,
            text="Join",
            fill=WOOD_ENGRAVING_COLOR,
            font=("Helvetica", 13, "bold"),
            tags="join_text",
        )
        self.canvas.tag_bind("join_arrow", "<Button-1>", self.on_join)
        self.canvas.tag_bind("join_text", "<Button-1>", self.on_join)

    def start_move(self, event):
        # Only allow move if click is in top 40px
        if event.y <= 40:
            self._drag_start_pointer_x = self.root.winfo_pointerx()
            self._drag_start_pointer_y = self.root.winfo_pointery()
            self._drag_start_win_x = self.root.winfo_x()
            self._drag_start_win_y = self.root.winfo_y()
            self._dragging = True
        else:
            self._dragging = False

    def do_move(self, event):
        if getattr(self, "_dragging", False):
            dx = self.root.winfo_pointerx() - self._drag_start_pointer_x
            dy = self.root.winfo_pointery() - self._drag_start_pointer_y
            new_x = self._drag_start_win_x + dx
            new_y = self._drag_start_win_y + dy
            self.root.geometry(f"+{new_x}+{new_y}")

    def get_window_position(self):
        self.root.update_idletasks()
        x = self.root.winfo_x()
        y = self.root.winfo_y()
        return x, y

    def go_to_character_screen(self, is_host):
        # Destroy landing and spawn character screen at same x/y
        x, y = self.get_window_position()
        self.root.destroy()
        CharacterScreen(self.app.audio_player, self.app, is_host, x, y)

    def on_join(self, event=None):
        self.go_to_character_screen(is_host=False)

    def on_host(self, event=None):
        self.go_to_character_screen(is_host=True)

    def on_close(self):
        # Disconnect client if possible, then destroy window
        try:
            if (
                hasattr(self.app, "client")
                and hasattr(self.app.client, "sio")
                and self.app.client.sio.connected
            ):
                self.app.client.sio.disconnect()
        except Exception as e:
            print(f"Error during disconnect: {e}")
        self.root.destroy()
