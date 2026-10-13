"""Run: uv run python -m jams.test_music (offline: nothing is searched or downloaded)"""

import threading
import time
from unittest import mock

from jams import music
from jams.music import parse, spotify_tags, square_cover

ID = "48pycZxk2eE"
SPOTIFY_PAGE = """<head><meta property="og:title" content="Peaches (feat. Daniel Caesar &amp; Giveon)"/>
<meta property="og:description" content="Justin Bieber, Daniel Caesar, GIVĒON · Justice · Song · 2021"/>
<meta property="og:image" content="https://i.scdn.co/image/ab67616d0000b273e6f407c7f3a0ec98845e4431"/>
<meta name="music:duration" content="198"/>
<meta name="music:musician_description" content="Justin Bieber, Daniel Caesar, GIVĒON"/></head>"""


def raises_value_error(fn, *args):
    try:
        fn(*args)
    except ValueError:
        return True
    return False


def test_parse():
    for link in (
        "https://open.spotify.com/track/17Wks0pgofBbv53Ay7m4Jc?si=ef56a78b3b0b476f",
        "https://open.spotify.com/intl-fr/track/17Wks0pgofBbv53Ay7m4Jc",
        "spotify:track:17Wks0pgofBbv53Ay7m4Jc",
    ):
        assert parse(link) == ("spotify", "17Wks0pgofBbv53Ay7m4Jc"), link
    for link in (
        f"https://www.youtube.com/watch?v={ID}",
        f"https://music.youtube.com/watch?v={ID}&si=abc",
        f"https://youtu.be/{ID}?si=abc",
        f" youtu.be/{ID} ",
        f"https://m.youtube.com/watch?feature=share&v={ID}",
        f"https://www.youtube.com/watch?v={ID}&list=RD{ID}",  # just the song
        f"https://youtube.com/shorts/{ID}",
    ):
        assert parse(link) == ("youtube", ID), link
    assert parse("  Lyn Lapid poster boy ") == ("search", "Lyn Lapid poster boy")
    assert parse("file:///C:/Windows/win.ini")[0] == "search"  # only ever searched for
    for bad in (
        "",
        "   ",
        "https://example.com/song.mp3",
        "http://192.168.86.111:5000/",
        f"https://youtube.com.evil.example/watch?v={ID}",
        f"https://evil.example/?u=https://youtu.be/{ID}",
        "https://www.youtube.com/playlist?list=PL1234567890",
        f"https://youtu.be/{ID}XYZ",  # not an 11-character id
        "https://open.spotify.com/album/18pzJc8GyrVQmunRXrY3ch",
    ):
        assert raises_value_error(parse, bad), bad


def test_spotify_tags():
    assert spotify_tags(SPOTIFY_PAGE) == {
        "title": "Peaches (feat. Daniel Caesar & Giveon)",
        "artist": "Justin Bieber, Daniel Caesar, GIVĒON",
        "cover_url": "https://i.scdn.co/image/ab67616d0000b273e6f407c7f3a0ec98845e4431",
    }
    no_cover = SPOTIFY_PAGE.replace("https://i.scdn", "http://i.scdn")
    assert spotify_tags(no_cover)["cover_url"] is None
    assert raises_value_error(spotify_tags, "<html><head></head></html>")  # app shell


def test_square_cover():
    still = {"url": "https://i.ytimg.com/maxres.jpg", "width": 1280, "height": 720}
    small = {"url": "https://yt3.ggpht.com/a=w120", "width": 120, "height": 120}
    big = {"url": "https://yt3.ggpht.com/a=w544", "width": 544, "height": 544}
    plain = {"url": "http://yt3.ggpht.com/a=w999", "width": 999, "height": 999}
    assert square_cover([small, still, big, plain]) == big["url"]
    assert square_cover([still, {"url": "https://i.ytimg.com/default.jpg"}]) is None


def test_one_download_per_song():
    """Two friends adding one song at once must not write the same file together."""
    busy, overlaps = [], []

    def slow_download(video_id, folder):
        overlaps.append(video_id in busy)
        busy.append(video_id)
        time.sleep(0.2)
        busy.remove(video_id)
        return {"title": "t", "requested_downloads": [{"filepath": "assets/fire-sound.mp3"}]}

    with mock.patch("jams.music.download", slow_download):
        adds = [threading.Thread(target=music.fetch, args=(f"https://youtu.be/{ID}",)) for _ in range(3)]
        for add in adds:
            add.start()
        for add in adds:
            add.join()
    assert overlaps == [False] * 3


if __name__ == "__main__":
    test_parse()
    test_spotify_tags()
    test_square_cover()
    test_one_download_per_song()
    print("ok")
