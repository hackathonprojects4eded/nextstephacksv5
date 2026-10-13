# Firejams

A cozy "desktop pet" campfire overlay (Tkinter, Windows-first). Friends sit around a fire as avatars whose mouths move when they talk (mic voice detection) and listen to the same music together. Hard rule: joining is FREE, with no Spotify Premium or any other account.

## Commands (Windows + Git Bash, from the repo root)
- Run: `uv run main.py`, or `run.bat` / `run.sh` (they `cd` to the repo first). Asset and `downloads/` paths are relative to the root.
- Self-checks (offline, about 1 s each, each prints `ok`):
  `uv run python -m jams.test_jam && uv run python -m jams.test_music && uv run python -m jams.test_player`
  Always use `-m` from the root: `python jams/test_jam.py` fails with `No module named 'jams'`.
- Don't launch `main.py` from a session unless asked: at startup it opens borderless topmost windows, the mic and the speakers. Check work with the self-checks.
- Headless room server, same as the host's server thread: `uv run python -m jams.server` (binds port 5000 and blocks).
- uv only. Python 3.12 is pinned (`.python-version`); add deps with `uv add <pkg>`. No pip, no requirements.txt.
- YouTube changes break yt-dlp: `uv lock --upgrade-package yt-dlp`, then `uv sync`. Its JS runtime `deno` comes from the `yt-dlp[default,deno]` extra and lives in `.venv`.

## How it works
- **Server**: the host's app runs the Socket.IO server (`jams/server.py`, python-socketio on eventlet) on a thread started by `screens/loading.py`. Every app, the host's included, connects to `LOCAL_IP:LOCAL_PORT` from `screens/constants.py`.
- **Rooms**: the server owns one `Jam` (`jams/jam.py`) per room. Any member sends `jam_cmd`; the server changes the `Jam` and broadcasts `jam_state` (`Jam.state()` plus an increasing `seq`).
- **Jam**: `queue` keeps played songs too (so `previous` works); `state()` sends only the upcoming ones. Each entry gets a `key`, so two copies of a song differ; the UI names songs by `key`, never by index.
- **Ticker**: the `tick_rooms` greenthread checks every 0.5 s and moves a room on when its song ends.
- **Adding a song**: `music.fetch` runs on a plain thread via `off_loop` while the hub keeps serving. Not `eventlet.tpool`: with the hub off the main thread, tpool's atexit hook prints a `greenlet.error` traceback.
- **Fetching** (`jams/music.py`):
  - A Spotify track link: read the public page's `og:`/`music:` meta tags (Python's default User-Agent gets them; a browser's gets an empty app shell), search YouTube Music for "artist title", and keep Spotify's names and art.
  - A YouTube link gives its 11-char video id. Anything else is a YouTube Music "songs" search via yt-dlp.
  - yt-dlp saves `bestaudio` as-is to `downloads/<11-char id>.<ext>` (no ffmpeg needed). PyAV reads the exact duration.
- **Serving**: `JamServer.serve_audio`, the WSGI app behind Socket.IO, serves `GET /audio/<file>` from `downloads/`.
- **Playback** (`jams/player.py`): every app, the host's too, plays the song itself. PyAV decodes the whole song to 44.1 kHz int16 stereo in RAM (about 10 MB/min), and a sounddevice output callback plays it.
  - `sync()` seeks to `progress_ms` plus the time since the state arrived (load time included) and ignores drift under 250 ms.
  - It decodes the next queued song ahead on a thread, so song changes are instant.
  - Joiners download songs over HTTP into their own `downloads/`, which is their cache. The host already has them.
- **Ordering** (`jams/client.py`): python-socketio runs each event on its own thread. `jam_state` applies a state only if its `seq` is newer than the last one, under `jam_lock`, then hands the UI work to `root.after(0, ...)`.
- **Timings** (owner's laptop): adding a song takes about 4–5 s (lookup + download). A decode takes 0.4–1.4 s depending on CPU state: Windows moves busy background processes to slower cores after a few seconds.
- **Screens**: `main.py` builds `Client(root)`, whose `AudioPlayerScreen` is the stage on the `tk.Tk()` root (mic, speakers and fire crackle start right away). Then `LandingScreen` → `CharacterScreen` → host: `LoadingScreen` → `JoinHostCodeScreen`; join: `JoinHostCodeScreen`. Each is a borderless topmost `Toplevel` that destroys itself and builds the next.

## Socket.IO events
- Client → server: `create_room`, `join_room`, `jam_cmd`, `user_talking_state`.
- Server → client: `room_created`, `room_joined`, `user_joined`, `user_left`, `players_updated`, `jam_state`, `user_talking_update`, `error`.
- `jam_cmd` is `{room_code, action, ...}`. Actions: `add` (`text`), `play`, `pause`, `next`, `previous`, `seek` (`position_ms`), `jump` and `remove` (`key`), `shuffle`.
- `jam_cmd` answers through the Socket.IO ack: an error string or `None`, which the client shows the sender in a warning box. Any exception's text reaches the user, so raise `ValueError("a friendly message")` in `jam.py`/`music.py`.

## Trust boundaries
Room members are other people's computers sending arbitrary payloads.
- `music.fetch` never hands user text to yt-dlp as a URL: links shrink to regex-checked ids, and anything else becomes a URL-quoted search query.
- The audio route (`AUDIO_RE`) and the player (`SONG_FILE`) whitelist file names: `<11-char id>.<ext>`, never a path.
- Cover art is only fetched over https (`utils/song.py`).
- Joiners never run yt-dlp: only `jams/server.py` imports `jams/music.py`.
- Known gap: the server doesn't check that `jam_cmd` or `user_talking_state` senders are in the room. The 6-char room code is the only gate.

## Conventions
- Tk is not thread-safe. Socket, mic and audio threads marshal UI work with `root.after(0, ...)`. Known violators to fix when touched: `user_joined`, `user_left` and `user_talking_update` in `jams/client.py`, and `_on_voice_state_change` (mic thread) in `screens/audio_player_screen.py`.
- The server isn't monkey-patched, so a blocking call in a handler stalls every room. Slow work goes through `off_loop`. `Jam`s are only touched by greenthreads on the hub, so they need no lock; never touch one from an `off_loop` thread.
- A new playback feature is a `Jam` method (it takes `now`; it never calls `time.time()`) with asserts in `jams/test_jam.py`, a branch in `jam_cmd`, and `client.send_jam(...)` from the UI. The UI shows what `jam_state` says (`render_state`).
- Cover art: call `fetch_cover(url)` off the Tk thread (it fills a cache), then `cover_photo(url, size)` on it.
- UI positions are absolute pixel coordinates on the art. `utils/points.py` prints the coordinates you click on an image.
- Self-checks are plain `assert` scripts with a `__main__` runner, runnable with `python -m` and offline (`Player(..., speakers=False)`, a `file://` URL as the host). There's no pytest; keep that style.
- Code style: match the surrounding code; small plain functions; short docstrings; `# ponytail:` comments mark deliberate shortcuts and their ceiling.

## Traps
- `LOCAL_IP = "192.168.86.111"` is a hardcoded LAN IP: it only works on one network, and the host's PC must have that address. To try two apps on one PC, set it to `127.0.0.1` locally (don't commit that).
- `screens/loading.py` and `screens/joinhostcode.py` start the server with a literal `port=5000`. Change them together with `LOCAL_PORT`.
- If a joiner can't reach `LOCAL_IP`, `JoinHostCodeScreen.join_room` starts its own empty `JamServer`, blocks the Tk thread, and retries the same address. It never yields a joinable room.
- The close button on the loading and code screens disconnects the shared socket, so closing the host's code sign leaves the room.
- `JoinHostCodeScreen` calls `sio.on("room_created", ...)`, which replaces `Client`'s handler that sets `client.room_code`. It works only because the reply beats `LoadingScreen`'s 0.5 s wait. If the reply loses, the host's `send_jam` silently does nothing.
- Avatars: `render_player` loads `assets/allplayers/H{L|R}{O|C}{1-7}.png`, but `.gitignore` has `allplayers/`. Those files exist only on this PC, so fresh clones show no avatars (the error is caught and printed). The tracked `assets/players/<Color>/*-removebg-preview.png` (the commented-out path) are the same size but different art. Committing `assets/allplayers/` is the owner's call.
- Pure black is the transparency key of the stage and sign windows (`utils/tkinter_compat.py`; `-transparentcolor` on Windows), so anything drawn `black`/`#000` turns see-through. macOS uses `-transparent`; Linux only gets an 80% alpha window.
- The fire crackle uses pydub + PyAudio, and `AudioSegment.from_mp3` needs a system ffmpeg on PATH. Without it, the error is caught and the fire is silent.
- Importing `jams.server` prints an `EventletDeprecationWarning`. That's expected.
- `README.md` is the hackathon write-up; its spotdl and server-streamed audio are gone. Trust the code.
- `alternate/` is a separate single-user prototype with a mock queue. Its paths are `../assets`, so run it from inside: `cd alternate && uv run main.py`.
- Not part of the app:
  - `utils/test_voice_detector.py` is a manual mic-threshold tool that runs until Ctrl+C (`uv run python utils/test_voice_detector.py`).
  - `utils/crop.py` and `utils/points.py` do their work at import (`crop.py` rewrites `assets/notes/crop/`). Never import them.
  - `songs/` holds unused spotdl-era mp3s. `downloads/` is gitignored and never pruned.

## Why not Spotify (don't retry these routes)
- Spotify Jams have no public API.
- Web API playback control requires Premium.
- Since Feb 2026, Development Mode apps need a Premium owner and are capped at 5 users.
- Joining a Jam remotely needs Premium.
- The Spotify embed plays 30-second previews when logged out.
- Spotify's Developer Policy §III forbids "an application which plays content from a single source to several simultaneous listeners".

Spotify track links are still accepted as input; only their public page metadata is read.

## Legal
Downloading from YouTube and serving the files to friends is against YouTube's terms. This is a personal project among friends; keep it that way.
