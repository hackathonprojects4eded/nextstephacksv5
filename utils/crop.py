from PIL import Image
import os

# Set crop box: (left, upper, right, lower)
# crop_box = (95, 235, 180, 375)  # for left sitting people
# crop_box = (363, 235, 445, 375)  # for right
# crop_box = (188, 190, 345, 400) # for fire
crop_box = (298, 313, 358, 380)  # for box

input_folder = "assets/fire"
output_folder = "assets/fire/crop/"
os.makedirs(output_folder, exist_ok=True)

for filename in os.listdir(input_folder):
    if filename.lower().endswith((".png")):
        img_path = os.path.join(input_folder, filename)
        img = Image.open(img_path)
        cropped = img.crop(crop_box)
        cropped.save(os.path.join(output_folder, filename))


# from rembg import remove
# from PIL import Image
# import io
# import numpy as np


# def crop_sticker(image_path, save_path):
#     with open(image_path, "rb") as i:
#         input_image = i.read()
#     print("Started removing background")
#     output_image = remove(input_image)
#     print("Finished removing background")
#     if isinstance(output_image, bytes):
#         img = Image.open(io.BytesIO(output_image)).convert("RGBA")
#     elif isinstance(output_image, np.ndarray):
#         img = Image.fromarray(output_image).convert("RGBA")
#     else:
#         img = output_image.convert("RGBA")

#     # Crop to non-transparent area
#     bbox = img.getbbox()
#     cropped = img.crop(bbox)
#     cropped.save(save_path)


# for i in range(1, 7):
#     crop_sticker(
#         f"assets/players/_raw/HLO{i}.png", f"assets/players/_raw_crop/HLO{i}.png"
#     )


# def ensure_transparency(
#     input_path, output_path, color_to_make_transparent=(255, 255, 255)
# ):
#     """
#     Ensures the image at input_path has a transparent background.
#     If not, converts the specified color (default: white) to transparent and saves to output_path.
#     """
#     img = Image.open(input_path).convert("RGBA")
#     datas = img.getdata()
#     newData = []
#     for item in datas:
#         # If pixel matches the color, make it transparent
#         if item[:3] == color_to_make_transparent:
#             newData.append((255, 255, 255, 0))
#         else:
#             newData.append(item)
#     img.putdata(newData)
#     img.save(output_path)
#     print(f"Saved with transparency: {output_path}")


# ensure_transparency(
#     "assets/fire-cropped/fire1.png", "assets/fire-cropped/fire1_transparent.png"
# )
