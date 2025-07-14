import tkinter as tk
from fire_radio_screen import FireRadioScreen

if __name__ == "__main__":
    try:
        root = tk.Tk()
        fire_radio = FireRadioScreen(root)
        root.mainloop()
    except Exception as e:
        print(f"Error: {e}")
