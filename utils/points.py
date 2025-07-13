import tkinter as tk
from PIL import Image, ImageTk

array = []


def log_coords(event):
    print(f"Clicked at: ({event.x}, {event.y})")
    array.append(event.x)
    array.append(event.y)

    print(array)


root = tk.Tk()
img = Image.open("assets/stage.png")
photo = ImageTk.PhotoImage(img)

canvas = tk.Canvas(root, width=img.width, height=img.height)
canvas.pack()
canvas.create_image(0, 0, anchor="nw", image=photo)
canvas.bind("<Button-1>", log_coords)

root.mainloop()
