import tkinter as tk
from tkinter import messagebox
from jams.client import Client
from screens.landing import LandingScreen

if __name__ == "__main__":
    try:
        root = tk.Tk()
        client = Client(root)
        landing = LandingScreen(client)
        root.mainloop()
    except Exception as e:
        messagebox.showerror("Error", str(e))
