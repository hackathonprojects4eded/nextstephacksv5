import time
import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageTk
import pygame
from jams.client import Client
from screens.landing import LandingScreen

from utils.song import get_random_song_metadata

if __name__ == "__main__":
    try:
        root = tk.Tk()
        client = Client(root, None)
        landing = LandingScreen(client)

        def on_close():
            try:
                if hasattr(client, "sio") and client.sio.connected:
                    client.sio.disconnect()
            except Exception as e:
                print(f"Error during disconnect: {e}")
            root.destroy()

        root.protocol("WM_DELETE_WINDOW", on_close)
        root.mainloop()
    except Exception as e:
        messagebox.showerror("Error", str(e))
