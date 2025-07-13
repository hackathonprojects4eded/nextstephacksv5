import os
import random
from mutagen.mp3 import MP3
from mutagen.id3 import ID3
from mutagen.id3._frames import APIC, TIT2, TPE1, TALB
from PIL import Image
import io
import base64

SONG_DIR = "songs"


def image_to_base64(image):
    """Convert a PIL Image to base64 string for JSON serialization."""
    if image is None:
        return None

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    img_str = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return img_str


def base64_to_image(base64_str):
    """Convert a base64 string back to PIL Image."""
    if base64_str is None:
        return None

    try:
        img_data = base64.b64decode(base64_str)
        image = Image.open(io.BytesIO(img_data))
        return image
    except Exception as e:
        print(f"Error converting base64 to image: {e}")
        return None


def get_song_metadata(filepath):
    # Extract metadata from a given mp3 file path
    audio = MP3(filepath, ID3=ID3)
    tags = audio.tags
    if tags is None:
        # No tags found, return defaults
        return {
            "title": "Unknown Title",
            "artist": "Unknown Artist",
            "album": "Unknown Album",
            "length": int(audio.info.length),
            "filepath": filepath,
            "cover_image": None,
        }
    metadata = {
        "title": tags.get("TIT2", TIT2(encoding=3, text=["Unknown Title"])).text[0],
        "artist": tags.get("TPE1", TPE1(encoding=3, text=["Unknown Artist"])).text[0],
        "album": tags.get("TALB", TALB(encoding=3, text=["Unknown Album"])).text[0],
        "length": int(audio.info.length),
        "filepath": filepath,
    }
    # Extract album art
    album_art = tags.getall("APIC") if hasattr(tags, "getall") else []
    if album_art:
        image_data = album_art[0].data
        img = Image.open(io.BytesIO(image_data))
        # Convert to base64 for JSON serialization
        metadata["cover_image"] = image_to_base64(img)
    else:
        metadata["cover_image"] = None
    return metadata


def get_random_song_metadata(song_dir):
    # 1. Select random .mp3 file
    songs = [f for f in os.listdir(song_dir) if f.lower().endswith(".mp3")]
    if not songs:
        raise Exception("No MP3 files found in directory.")

    song_file = random.choice(songs)
    full_path = os.path.join(song_dir, song_file)
    return get_song_metadata(full_path)


# Example usage
if __name__ == "__main__":
    song_info = get_random_song_metadata(SONG_DIR)
    print("🎵 Now playing:", song_info["title"])
    print("👤 Artist:", song_info["artist"])
    print("💽 Album:", song_info["album"])
    print("⏱ Length:", song_info["length"], "seconds")
    if song_info["cover_image"]:
        # Convert back to image for display
        img = base64_to_image(song_info["cover_image"])
        if img:
            img.show()  # Open album cover
