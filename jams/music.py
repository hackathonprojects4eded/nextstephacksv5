"""
Songs for the queue: fetch() turns what a friend typed in the add box (a Spotify track
link, a YouTube / YouTube Music link, or a song name) into an audio file from YouTube,
which the host then serves to the room. playlist() lists a playlist's songs as add-box texts.
"""

import html
import json
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
YOUTUBE_PLAYLIST = re.compile(
    r"(?:https?://)?(?:(?:www|m|music)\.)?(?:youtube\.com|youtu\.be)/\S*?[?&]list="
    r"([A-Za-z0-9_-]{2,64})(?=[&#]|$)",
    re.I,
)
SPOTIFY_PLAYLIST = re.compile(
    r"(?:https?://)?open\.spotify\.com/(?:intl-[a-z-]+/)?(playlist|album)/"
    r"([A-Za-z0-9]{22})(?![A-Za-z0-9])",
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


def parse_playlist(text):
    """A playlist link: ("youtube", list id), or ("playlist" or "album", Spotify id)."""
    text = text.strip()
    if m := YOUTUBE_PLAYLIST.match(text):
        return "youtube", m[1]
    if m := SPOTIFY_PLAYLIST.match(text):
        return m[1].lower(), m[2]
    raise ValueError("Paste a YouTube or Spotify playlist link")


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


def youtube_tracks(entries):
    """A YouTube playlist's videos as add-box texts, minus private and deleted ones."""
    tracks = []
    for entry in entries:
        video_id = entry.get("id") or ""
        if entry.get("title") in ("[Private video]", "[Deleted video]"):
            continue
        if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
            continue
        artist = entry.get("channel") or entry.get("uploader") or ""
        tracks.append(
            {
                "title": entry.get("title") or "",
                "artist": artist.removesuffix(" - Topic"),  # YouTube Music's artist channels
                "text": f"https://youtu.be/{video_id}",
            }
        )
    return tracks


def youtube_playlist(list_id):
    """A YouTube (Music) playlist's name and first 100 songs, without opening each video."""
    url = f"https://www.youtube.com/playlist?list={list_id}"
    try:
        with yt_dlp.YoutubeDL({**YTDL, "extract_flat": True, "playlistend": 100}) as ydl:
            info = ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError:
        raise ValueError("Couldn't read that playlist") from None
    return {"title": info.get("title") or "", "tracks": youtube_tracks(info.get("entries") or [])}


def spotify_tracks(page):
    """Name and songs of a Spotify playlist or album, from its embed page's JSON."""
    try:
        data = re.search(r'id="__NEXT_DATA__"[^>]*>(.*?)</script>', page, re.S)
        entity = json.loads(data[1])["props"]["pageProps"]["state"]["data"]["entity"]
        tracks = []
        for song in entity["trackList"]:
            m = re.fullmatch(r"spotify:track:([A-Za-z0-9]{22})", song.get("uri") or "")
            if m:  # not a podcast episode or a local file
                tracks.append(
                    {
                        "title": song["title"],
                        "artist": song["subtitle"].replace("\xa0", " "),  # "A,\xa0B"
                        "text": f"https://open.spotify.com/track/{m[1]}",
                    }
                )
        return {"title": entity["name"], "tracks": tracks[:100]}
    except (AttributeError, KeyError, TypeError, ValueError):  # no such list, or a new page layout
        raise ValueError("Couldn't read that playlist") from None


def spotify_playlist(kind, list_id):
    """A Spotify playlist's or album's name and first 100 songs, with no account."""
    # Its public embed page names the first 100 songs; the plain page only links 30 of them
    url = f"https://open.spotify.com/embed/{kind}/{list_id}"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            return spotify_tracks(resp.read().decode("utf-8", "replace"))
    except OSError:  # offline, timed out or turned away
        raise ValueError("Couldn't read that playlist") from None


def playlist(text):
    """A YouTube or Spotify playlist (or Spotify album) link's name and songs, as add-box texts."""
    kind, list_id = parse_playlist(text)
    found = youtube_playlist(list_id) if kind == "youtube" else spotify_playlist(kind, list_id)
    if not found["tracks"]:
        raise ValueError("That playlist is empty")
    return found
