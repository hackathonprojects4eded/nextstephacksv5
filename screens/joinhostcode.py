import tkinter as tk
from .constants import WOOD_COLOR, WOOD_ENGRAVING_COLOR, WOOD_ENTER_USERNAME_COLOR
from utils.tkinter_compat import set_window_transparency


class JoinHostCodeScreen:
    """
    Handles the join/host code logic. Displays or requests code, and navigation to main app.
    """

    def __init__(self, app, client, is_host, username, color, x, y):
        self.app = app
        self.client = client
        self.is_host = is_host
        self.username = username
        self.color = color
        self.transparent_color = "black"
        self.x = x
        self.y = y

        geometry_str = f"250x300+{x}+{y}"
        self.root = tk.Toplevel(app.root) if hasattr(app, "root") else tk.Tk()
        self.root.geometry(geometry_str)
        self.root.configure(bg=self.transparent_color)
        set_window_transparency(self.root, color=self.transparent_color, alpha=0.8)
        self.root.overrideredirect(True)
        self.root.wm_attributes("-topmost", True)

        self._drag_start_pointer_x = 0
        self._drag_start_pointer_y = 0
        self._drag_start_win_x = 0
        self._drag_start_win_y = 0
        self._dragging = False

        # Set this screen as the current screen in the client
        self.client.current_screen = self

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

        # For host mode, set up callback for room creation
        if self.is_host:
            # Set up callback for when room is created
            print("Setting up room_created callback...")
            self.client.sio.on("room_created", self.on_room_created)
            print("Callback set up successfully")

        # Display the correct background image
        try:
            from PIL import Image, ImageTk

            if self.is_host:
                bg_img = Image.open("assets/signs/host_code_thing.png")
            else:
                bg_img = Image.open("assets/signs/join_code_enter_png.png")
            self.bg_img_tk = ImageTk.PhotoImage(bg_img)
            self.canvas.create_image(0, 0, anchor="nw", image=self.bg_img_tk)
        except Exception as e:
            print(f"Could not load joinhostcode screen image: {e}")

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

        # Bind window move to entire canvas
        self.canvas.bind("<Button-1>", self.start_move)
        self.canvas.bind("<B1-Motion>", self.do_move)

        # Code entry box (inside polygon/rectangle) - only for join mode
        # Polygon: [61, 97, 181, 91, 182, 108, 64, 111]
        entry_x = (61 + 181) // 2
        entry_y = (97 + 108) // 2
        self.code_var = tk.StringVar()

        if not self.is_host:
            # Only show entry box for join mode
            self.code_entry = tk.Entry(
                self.canvas,
                textvariable=self.code_var,
                font=("Helvetica", 12, "bold"),
                width=7,
                justify="center",
                bg=WOOD_ENTER_USERNAME_COLOR,
                fg="#D3D3D3",
                relief="flat",
                bd=0,
                highlightthickness=0,
            )
            self.code_entry_window = self.canvas.create_window(
                entry_x,
                entry_y,
                anchor="center",
                window=self.code_entry,
                width=120,
                height=22,
            )
        else:
            # For host mode, create a read-only display
            self.code_entry = tk.Entry(
                self.canvas,
                textvariable=self.code_var,
                font=("Helvetica", 12, "bold"),
                width=7,
                justify="center",
                bg=WOOD_ENTER_USERNAME_COLOR,
                fg="#D3D3D3",
                relief="flat",
                bd=0,
                highlightthickness=0,
                readonlybackground=WOOD_ENTER_USERNAME_COLOR,
                state="readonly",
            )
            self.code_entry_window = self.canvas.create_window(
                entry_x,
                entry_y,
                anchor="center",
                window=self.code_entry,
                width=120,
                height=22,
            )

        # Single arrow for both host and join
        arrow_points = [
            154,
            199,
            152,
            188,
            197,
            185,
            198,
            182,
            208,
            191,
            202,
            200,
            201,
            197,
            157,
            200,
        ]
        self.arrow = self.canvas.create_polygon(
            arrow_points, fill=WOOD_COLOR, width=2, tags="arrow"
        )

        # Arrow text based on is_host
        if self.is_host:
            arrow_text = "Create"
        else:
            arrow_text = "Join"

        self.canvas.create_text(
            175,
            194,
            text=arrow_text,
            fill=WOOD_ENGRAVING_COLOR,
            font=("Helvetica", 10, "bold"),
            tags="arrow_text",
        )
        self.canvas.tag_bind("arrow", "<Button-1>", self.on_arrow_click)
        self.canvas.tag_bind("arrow_text", "<Button-1>", self.on_arrow_click)

        # For host mode, set up callback after UI is built
        if self.is_host:
            # Callback already set up earlier
            # Start checking for room code
            self.check_for_room_code()

    def start_move(self, event):
        # Allow dragging from anywhere on the canvas, not just top 40px
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

    def on_arrow_click(self, event=None):
        if self.is_host:
            print(f"Host: Room code is {self.client.room_code}")
            # Update the code display if we have a room code
            if self.client.room_code:
                self.code_var.set(self.client.room_code)

            # Show notification for host
            self.show_host_notification()
        else:
            code = self.code_var.get().strip()
            if not code:
                print("No code!")
                return

            print(f"Join: Joining room with code: {code}")
            self.join_room(code)

    def show_host_notification(self):
        """Show a notification for the host to share the code."""
        # Create a simple notification popup
        notification = tk.Toplevel(self.root)
        notification.wm_attributes("-topmost", True)
        notification.geometry("200x100")
        notification.title("Share Code")
        notification.configure(bg="white")
        notification.overrideredirect(True)

        # Position notification near the main window
        x = self.root.winfo_x() + 50
        y = self.root.winfo_y() + 50
        notification.geometry(f"200x100+{x}+{y}")

        # Add notification content
        tk.Label(
            notification,
            text="Share this code with others!",
            bg="white",
            font=("Helvetica", 10, "bold"),
        ).pack(pady=10)

        tk.Label(
            notification,
            text=f"Room Code: {self.client.room_code}",
            bg="white",
            font=("Helvetica", 12),
            fg="#007ACC",
        ).pack(pady=5)

        notification.after(2500, notification.destroy)

    def join_room(self, room_code):
        """Join a room with the given code."""
        # Show loading state
        self.update_join_status("Connecting to server...")

        # First, connect to the server if not already connected
        if not self.client.is_connected():
            print(f"Client not connected, attempting to connect...")

            # Try to connect to existing server first
            if not self.client.connect_to_server("http://169.254.100.138:5000"):
                print("No existing server found, starting new server...")
                self.update_join_status("Starting server...")

                # Start server in background
                import threading
                import time
                from jams.server import JamServer

                def start_server():
                    try:
                        server = JamServer()
                        server.run(host="0.0.0.0", port=5000)
                    except Exception as e:
                        print(f"Server error: {e}")

                server_thread = threading.Thread(target=start_server, daemon=True)
                server_thread.start()

                # Wait for server to start
                time.sleep(2)

                # Try connecting again
                if not self.client.connect_to_server("http://169.254.100.138:5000"):
                    self.update_join_status("Failed to connect to server")
                    print("Failed to connect to server")
                    return
                else:
                    print("Successfully connected to server")
            else:
                print("Successfully connected to existing server")

        self.update_join_status("Joining room...")
        print(f"Attempting to join room: {room_code}")

        # Try to join the room
        if self.client.join_room(room_code, self.username, self.color):
            self.update_join_status("Joining room...")
            print("Join room request sent successfully")

        else:
            self.update_join_status("Failed to join room")
            print("Failed to send join room request")

        self.root.destroy()

    def update_join_status(self, status):
        """Update the join status text."""
        if hasattr(self, "status_text"):
            self.canvas.itemconfig(self.status_text, text=status)
        else:
            # Create status text if it doesn't exist
            self.status_text = self.canvas.create_text(
                123, 135, text=status, fill="gray", font=("Helvetica", 10)
            )

    def on_room_created(self, data):
        """Called when room is created by the server."""
        print(f"on_room_created called with data: {data}")
        room_code = data.get("room_code")
        if room_code:
            print(f"Setting room code to: {room_code}")
            # Use after to schedule UI update on main thread
            self.root.after(0, lambda: self._update_room_code(room_code))
            print(f"Room created with code: {room_code}")
        else:
            print("No room_code in data")

    def _update_room_code(self, room_code):
        """Update room code on main thread."""
        try:
            if hasattr(self, "code_var"):
                self.code_var.set(room_code)
                print(f"Room code updated to: {room_code}")
            else:
                print("code_var not available yet")
        except Exception as e:
            print(f"Error updating room code: {e}")

    def check_for_room_code(self):
        """Check if room code is available and update display."""
        if self.is_host and self.client.room_code:
            self.code_var.set(self.client.room_code)
            # print(f"Room code set to: {self.client.room_code}")

        # Schedule next check
        self.root.after(100, self.check_for_room_code)
