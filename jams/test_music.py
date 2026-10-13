"""Run: uv run python -m jams.test_music (offline: nothing is searched or downloaded)"""

import threading
import time
from unittest import mock

from jams import music
from jams.music import (
    parse,
    parse_playlist,
    spotify_tags,
    spotify_tracks,
    square_cover,
    youtube_tracks,
)

ID = "48pycZxk2eE"
LIST = "PLRBp0Fe2GpgmgoscNFLxNyBVSFVdYmFkq"
# Trimmed from https://open.spotify.com/embed/album/18pzJc8GyrVQmunRXrY3ch (Oct 2026), plus an episode
SPOTIFY_EMBED = (
    '</div><script id="__NEXT_DATA__" type="application/json">{"props":{"pageProps":{"state":'
    '{"data":{"entity":{"type":"album","name":"to love in the 21st century","trackList":['
    '{"uri":"spotify:track:7AluDV7hM6tnPYsLxpZYMA","uid":"e5264445f99cb0b1d7a5","title":"intro",'
    '"subtitle":"Lyn Lapid","duration":70706,"isPlayable":true,"entityType":"track"},'
    '{"uri":"spotify:track:2vjX1VkntJPIQkqwbJQvoa","uid":"738a4314ad5cdec6df98",'
    '"title":"do u really?","subtitle":"Lyn Lapid,\xa0Ruth B.","duration":161120,'
    '"isPlayable":true,"entityType":"track"},'
    '{"uri":"spotify:episode:4rOoJ6Egrf8K2IrywzwOMk","title":"A podcast","subtitle":"Someone",'
    '"entityType":"episode"}]}}}}},"page":"/album/[id]"}</script>'
)
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


def test_parse_playlist():
    for link in (
        f"https://www.youtube.com/playlist?list={LIST}",
        f"https://music.youtube.com/playlist?list={LIST}&si=abc",
        f" youtube.com/playlist?list={LIST} ",
        f"https://m.youtube.com/playlist?feature=share&list={LIST}#top",
        f"https://www.youtube.com/watch?v={ID}&list={LIST}",  # the add box keeps just the song
        f"https://youtu.be/{ID}?list={LIST}",
    ):
        assert parse_playlist(link) == ("youtube", LIST), link
    spotify = "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M?si=ef56a78b"
    assert parse_playlist(spotify) == ("playlist", "37i9dQZF1DXcBWIGoYBM5M")
    for link in (
        "https://open.spotify.com/intl-fr/album/18pzJc8GyrVQmunRXrY3ch",
        "HTTPS://OPEN.SPOTIFY.COM/ALBUM/18pzJc8GyrVQmunRXrY3ch",  # its page path is lowercase
    ):
        assert parse_playlist(link) == ("album", "18pzJc8GyrVQmunRXrY3ch"), link
    for bad in (
        "",
        "lofi beats",
        f"https://www.youtube.com/watch?v={ID}",  # one song, no list
        f"https://youtu.be/{ID}",
        "https://www.youtube.com/playlist?list=",
        "https://www.youtube.com/playlist?list=" + "a" * 65,
        f"https://www.youtube.com/playlist?list={LIST}/../../x",
        f"https://www.youtube.com/playlist?list={LIST}%22onload",
        f"https://youtube.com.evil.example/playlist?list={LIST}",
        f"https://evil.example/?u=https://www.youtube.com/playlist?list={LIST}",
        "https://open.spotify.com/track/17Wks0pgofBbv53Ay7m4Jc",
        "https://open.spotify.com/artist/4pfy05cNNTacuOQ6SiSu4v",
        "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5MXYZ",  # not a 22-char id
        "https://open.spotify.com.evil.example/playlist/37i9dQZF1DXcBWIGoYBM5M",
        "file:///C:/Windows/win.ini",
    ):
        assert raises_value_error(parse_playlist, bad), bad


def test_youtube_tracks():
    entries = [
        {"id": "hG6YzmvbosI", "title": "for when it’s warmer", "channel": "Sleepy Fish - Topic"},
        {"id": "ETbOX50t0kw", "title": "[Private video]", "channel": None, "duration": None},
        {"id": "RcUnmaanrNM", "title": "[Deleted video]", "channel": None, "duration": None},
        {"id": "1FxeCa6kypU", "title": "Still", "channel": None, "uploader": "idealism"},
        {"id": "UCx/../../etc", "title": "Not a video"},
        {"id": None, "title": "No id"},
    ]
    tracks = youtube_tracks(entries)
    assert tracks == [
        {"title": "for when it’s warmer", "artist": "Sleepy Fish", "text": "https://youtu.be/hG6YzmvbosI"},
        {"title": "Still", "artist": "idealism", "text": "https://youtu.be/1FxeCa6kypU"},
    ]
    assert [parse(t["text"]) for t in tracks] == [("youtube", "hG6YzmvbosI"), ("youtube", "1FxeCa6kypU")]


def test_spotify_tracks():
    found = spotify_tracks(SPOTIFY_EMBED)
    assert found == {
        "title": "to love in the 21st century",
        "tracks": [
            {
                "title": "intro",
                "artist": "Lyn Lapid",
                "text": "https://open.spotify.com/track/7AluDV7hM6tnPYsLxpZYMA",
            },
            {
                "title": "do u really?",
                "artist": "Lyn Lapid, Ruth B.",
                "text": "https://open.spotify.com/track/2vjX1VkntJPIQkqwbJQvoa",
            },
        ],
    }
    assert [parse(t["text"])[0] for t in found["tracks"]] == ["spotify", "spotify"]  # add takes them
    not_found = '<script id="__NEXT_DATA__">{"props":{"pageProps":{"status":404}}}</script>'
    new_layout = SPOTIFY_EMBED.replace('"trackList"', '"tracks"')
    for page in (not_found, "<html><head></head></html>", new_layout):
        assert raises_value_error(spotify_tracks, page)
    with mock.patch("jams.music.youtube_playlist", return_value={"title": "t", "tracks": []}):
        assert raises_value_error(music.playlist, f"https://www.youtube.com/playlist?list={LIST}")  # empty


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
    test_parse_playlist()
    test_youtube_tracks()
    test_spotify_tracks()
    test_spotify_tags()
    test_square_cover()
    test_one_download_per_song()
    print("ok")
