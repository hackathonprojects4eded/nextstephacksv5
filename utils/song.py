import io
import urllib.request
from functools import lru_cache

from PIL import Image, ImageTk


@lru_cache(maxsize=256)
def fetch_cover(url):
    """Album art bytes, or None. Cached either way, so each url is only tried once."""
    try:
        if not url.startswith("https://"):  # urls come from the host; never read local files
            return None
        with urllib.request.urlopen(url, timeout=5) as resp:
            return resp.read()
    except Exception:
        return None


def cover_photo(url, size):
    """Album art as a Tk image (fetch_cover it off the Tk thread first), gray if missing."""
    try:
        img = Image.open(io.BytesIO(fetch_cover(url)))
    except Exception:
        img = Image.new("RGB", (size, size), "gray")
    return ImageTk.PhotoImage(img.resize((size, size)))
