import time
import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageTk
import pygame
from jams.client import Client
from screens.landing import LandingScreen
from screens.audio_player_screen import AudioPlayerScreen

from utils.song import get_random_song_metadata

if __name__ == "__main__":
    try:
        root = tk.Tk()
        client = Client(root)
        app = AudioPlayerScreen(root, client)
        landing = LandingScreen(client)

        root.mainloop()
    except Exception as e:
        messagebox.showerror("Error", str(e))
