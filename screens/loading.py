import tkinter as tk
from .constants import WOOD_COLOR, WOOD_ENGRAVING_COLOR, LOCAL_IP, LOCAL_PORT
from .joinhostcode import JoinHostCodeScreen
from utils.tkinter_compat import set_window_transparency


class LoadingScreen:
    """
    Loading screen that shows while server is starting and room is being created.
    """

    def __init__(self, app, client, username, color, x, y):
        self.app = app
        self.client = client
        self.username = username
        self.color = color
        self.transparent_color = "black"
        self.x = x
        self.y = y

        geometry_str = f"250x230+{x}+{y}"
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
        self.server_thread = None

        self.fire_images = []
        try:
            from PIL import Image, ImageTk

            for i in range(1, 4):
                fire_img = Image.open(f"assets/fire/Fire_{i}.png")
                # Resize fire images to fit better (157x210 original size)
                fire_img = fire_img.resize((157, 210))
                fire_tk = ImageTk.PhotoImage(fire_img)
                self.fire_images.append(fire_tk)
        except Exception as e:
            print(f"Could not load fire images: {e}")
            self.fire_images = []

        self.build_ui()
        self.start_loading()

    def build_ui(self):
        self.canvas = tk.Canvas(
            self.root,
            width=300,
            height=250,
            bg=self.transparent_color,
            highlightthickness=0,
        )
        self.canvas.place(x=0, y=0, relwidth=1, relheight=1)

        # Position fire at center bottom with padding
        fire_x = 125  # Center of 250px width
        fire_y = 250 - 50  # Bottom with 50px padding

        # Create fire image on canvas
        if self.fire_images:
            self.fire_image_id = self.canvas.create_image(
                fire_x, fire_y, anchor="s", image=self.fire_images[0]
            )
        else:
            self.fire_image_id = None

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

        # Loading text (positioned above fire)
        self.loading_text = self.canvas.create_text(
            125,
            80,
            text="Creating room...",
            fill="white",
            font=("Helvetica", 14, "bold"),
            tags="loading_text",
        )

        # Loading dots animation
        self.dots_text = self.canvas.create_text(
            125,
            100,
            text="",
            fill="white",
            font=("Helvetica", 12),
            tags="dots_text",
        )

        # Progress text
        self.progress_text = self.canvas.create_text(
            125,
            120,
            text="Starting server...",
            fill="white",
            font=("Helvetica", 10),
            tags="progress_text",
        )

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

    def update_progress(self, text):
        """Update the progress text."""
        self.canvas.itemconfig(self.progress_text, text=text)
        self.root.update()

    def animate_dots(self, count=0):
        """Animate the loading dots."""
        dots = "." * (count % 4)
        self.canvas.itemconfig(self.dots_text, text=dots)
        self.root.update()

        # Continue animation until loading is complete
        if hasattr(self, "loading_complete") and self.loading_complete:
            return

        self.root.after(500, lambda: self.animate_dots(count + 1))

    def animate_fire(self, frame=0):
        """Animate the fire by cycling through the fire images."""
        if hasattr(self, "loading_complete") and self.loading_complete:
            return

        if self.fire_images and self.fire_image_id:
            # Cycle through the 3 fire images
            current_frame = frame % len(self.fire_images)
            self.canvas.itemconfig(
                self.fire_image_id, image=self.fire_images[current_frame]
            )
            self.root.update()

        # Continue animation
        self.root.after(200, lambda: self.animate_fire(frame + 1))

    def start_loading(self):
        """Start the loading process."""
        import threading
        import time
        from jams.server import JamServer
        from .joinhostcode import JoinHostCodeScreen

        # Start animations
        self.animate_dots()
        self.animate_fire()

        def loading_process():
            try:
                # Step 1: Start server
                self.root.after(0, lambda: self.update_progress("Starting server..."))
                time.sleep(0.5)

                def start_server():
                    try:
                        server = JamServer()
                        server.run(host="0.0.0.0", port=5000)
                    except Exception as e:
                        print(f"Server error: {e}")

                self.server_thread = threading.Thread(target=start_server, daemon=True)
                self.server_thread.start()

                # Step 2: Wait for server to start
                self.root.after(
                    0, lambda: self.update_progress("Waiting for server...")
                )
                time.sleep(3)  # Increased wait time to ensure server is ready

                # Step 3: Connect client
                self.root.after(
                    0, lambda: self.update_progress("Connecting to server...")
                )
                max_retries = 5  # Increased retries
                for attempt in range(max_retries):
                    try:
                        if self.client.connect_to_server(
                            f"http://{LOCAL_IP}:{LOCAL_PORT}"
                        ):
                            self.root.after(
                                0, lambda: self.update_progress("Connected to server")
                            )
                            time.sleep(1)  # Increased wait time

                            # Step 4: Create room
                            self.root.after(
                                0, lambda: self.update_progress("Creating room...")
                            )
                            if self.client.create_room(self.username, self.color):
                                self.root.after(
                                    0, lambda: self.update_progress("Room created!")
                                )
                                time.sleep(0.5)

                                # Step 5: Navigate to joinhostcode screen
                                self.root.after(0, self.complete_loading)
                                return
                            else:
                                self.root.after(
                                    0,
                                    lambda: self.update_progress(
                                        "Failed to create room"
                                    ),
                                )
                        else:
                            self.root.after(
                                0,
                                lambda: self.update_progress(
                                    f"Connection failed (attempt {attempt + 1})"
                                ),
                            )
                    except Exception as e:
                        self.root.after(
                            0, lambda: self.update_progress(f"Connection error: {e}")
                        )

                    if attempt < max_retries - 1:
                        time.sleep(2)  # Increased wait time between retries

                self.root.after(0, lambda: self.update_progress("Failed to connect"))

            except Exception as e:
                self.root.after(0, lambda: self.update_progress(f"Error: {e}"))

        # Start loading in background thread
        loading_thread = threading.Thread(target=loading_process, daemon=True)
        loading_thread.start()

    def complete_loading(self):
        """Complete loading and navigate to joinhostcode screen."""
        self.loading_complete = True

        # Navigate to joinhostcode screen
        x, y = self.root.winfo_x(), self.root.winfo_y()
        self.root.destroy()
        JoinHostCodeScreen(
            self.app,
            self.client,
            is_host=True,
            username=self.username,
            color=self.color,
            x=x,
            y=y,
        )

    def on_close(self):
        # Disconnect client if possible, then destroy window
        try:
            if hasattr(self.client, "sio") and self.client.sio.connected:
                self.client.sio.disconnect()
        except Exception as e:
            print(f"Error during disconnect: {e}")
        self.root.destroy()
