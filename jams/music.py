"""
Songs for the queue: fetch() turns what a friend typed in the add box (a Spotify track
link, a YouTube / YouTube Music link, or a song name) into an audio file from YouTube,
which the host then serves to the room.
"""

import html
import os
import re
import threading
import urllib.error
import urllib.parse
import urllib.request

import av
import yt_dlp

from screens.constants import DOWNLOADS_FOLDER

SPOTIFY_LINK = re.compile(
    r"(?:(?:https?://)?open\.spotify\.com/(?:intl-[a-z-]+/)?track/|spotify:track:)"
    r"([A-Za-z0-9]{22})(?![A-Za-z0-9])",
    re.I,
)
YOUTUBE_LINK = re.compile(
    r"(?:https?://)?(?:(?:www|m|music)\.)?"
    r"(?:youtube\.com/(?:watch\?(?:\S*&)?v=|(?:shorts|live|embed)/)|youtu\.be/)"
    r"([A-Za-z0-9_-]{11})(?![A-Za-z0-9_-])",
    re.I,
)
YTDL = {"quiet": True, "no_warnings": True, "noprogress": True, "noplaylist": True}
DOWNLOADING = {}  # video id -> lock: two adds of one song would write the same file


def parse(text):
    """What a friend typed: ("spotify", track id), ("youtube", video id) or ("search", text)."""
    text = text.strip()
    if m := SPOTIFY_LINK.match(text):
        return "spotify", m[1]
    if m := YOUTUBE_LINK.match(text):
        return "youtube", m[1]
    if re.match(r"https?://", text, re.I):
        raise ValueError("Paste a Spotify or YouTube song link, or type a song name")
    if not text:
        raise ValueError("Type a song name or paste a link")
    return "search", text


def spotify_tags(page):
    """Title, artist and cover art from a Spotify track page's meta tags."""
    tags = re.findall(r'<meta (?:property|name)="([^"]+)" content="([^"]*)"', page)
    tags = {name: html.unescape(value) for name, value in tags}
    if not tags.get("og:title") or not tags.get("music:musician_description"):
        raise ValueError("Couldn't read that Spotify link")
    cover = tags.get("og:image", "")
    return {
        "title": tags["og:title"],
        "artist": tags["music:musician_description"],
        "cover_url": cover if cover.startswith("https://") else None,
    }


def square_cover(thumbnails):
    """The biggest roughly square https thumbnail: album art, not a 16:9 video still."""
    squares = [
        t
        for t in thumbnails
        if t.get("width") and t.get("height") and 0.9 <= t["width"] / t["height"] <= 1.1
    ]
    squares = [t for t in squares if t["url"].startswith("https://")]
    return max(squares, key=lambda t: t["width"])["url"] if squares else None


def spotify_song(track_id):
    """Title, artist and cover art of a Spotify track."""
    # Python's own User-Agent gets the meta tags; a browser's gets an empty app shell
    try:
        url = f"https://open.spotify.com/track/{track_id}"
        with urllib.request.urlopen(url, timeout=10) as resp:
            return spotify_tags(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise ValueError("Couldn't find that Spotify song") from None
        raise


def search(query):
    """Video id of the top song in YouTube Music's search results."""
    url = "https://music.youtube.com/search?q=" + urllib.parse.quote(query) + "#songs"
    with yt_dlp.YoutubeDL({**YTDL, "extract_flat": True, "playlistend": 1}) as ydl:
        songs = ydl.extract_info(url, download=False).get("entries") or []
    if not songs or not re.fullmatch(r"[A-Za-z0-9_-]{11}", songs[0].get("id") or ""):
        raise ValueError("Couldn't find that song")
    return songs[0]["id"]


def download(video_id, folder):
    """A video's yt-dlp info, once its audio is in `folder` (kept if already there)."""
    options = {
        **YTDL,
        "format": "bestaudio",  # saved as-is (webm/m4a): no ffmpeg needed
        "paths": {"home": folder},
        # ponytail: yt-dlp won't download a file it already has, but still looks the
        # video up (~3 s); keep track dicts around if re-adding songs feels slow
        "outtmpl": "%(id)s.%(ext)s",
        # YouTube Music's client adds square album art to the thumbnails
        "extractor_args": {"youtube": {"player_client": ["default", "web_music"]}},
    }
    url = f"https://www.youtube.com/watch?v={video_id}"
    for attempt in range(3):  # downloads now and then fail with a one-off HTTP 403
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=False)  # fresh links each try
            minutes = (info.get("duration") or 0) / 60
            if info.get("is_live") or not 0 < minutes <= 15:
                raise ValueError("Pick a song under 15 minutes")
            try:
                return ydl.process_ie_result(info)
            except yt_dlp.utils.DownloadError:
                if attempt == 2:
                    raise


def fetch(text, folder=DOWNLOADS_FOLDER):
    """Find a song (Spotify track link, YouTube/YouTube Music link, or a song name) and download its audio."""
    kind, value = parse(text)
    spotify = spotify_song(value) if kind == "spotify" else {}
    query = f"{spotify['artist']} {spotify['title']}" if spotify else value
    video_id = value if kind == "youtube" else search(query)
    with DOWNLOADING.setdefault(video_id, threading.Lock()):
        info = download(video_id, folder)
    path = info["requested_downloads"][0]["filepath"]
    with av.open(path) as media:
        duration_ms = media.duration // 1000  # av counts microseconds
    return {
        "id": video_id,
        "file": os.path.basename(path),
        "title": info.get("track") or info["title"],
        "artist": info.get("artist") or info.get("uploader") or "",
        "cover_url": square_cover(info.get("thumbnails") or []),
        "duration_ms": duration_ms,
        **spotify,  # Spotify's names and art, for songs linked from there
    }
