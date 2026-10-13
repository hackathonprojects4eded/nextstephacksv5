import shutil
import tkinter as tk
from tkinter import messagebox
from jams.client import Client
from screens.constants import DOWNLOADS_FOLDER
from screens.landing import LandingScreen

if __name__ == "__main__":
    # Songs last one session. Wiping at startup too catches runs that never reached
    # `finally`: a closed terminal, Task Manager, a crash, a power cut.
    # ponytail: one app per checkout; a second app (or `python -m jams.server`) on this
    # computer shares downloads/ and loses its songs to these wipes
    shutil.rmtree(DOWNLOADS_FOLDER, ignore_errors=True)
    try:
        root = tk.Tk()
        client = Client(root)
        landing = LandingScreen(client)
        root.mainloop()
    except Exception as e:
        messagebox.showerror("Error", str(e))
    finally:  # ❎ or Ctrl+C: files still being written are left for the next startup
        shutil.rmtree(DOWNLOADS_FOLDER, ignore_errors=True)
