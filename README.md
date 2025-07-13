## Inspiration

I don't have spotify premium. At 12:00 am the founder told me "if you want to go against big tech then do it" something along the lines of that in the discord. And then the idea clicked - why not make a jam thats much more indie, much more personalized, so much calm, relaxing, and detached from the grasps of big coorperations like spotify collecting all your data.

## What it does

You create a room and get a code, and then you can jam to the same music as your friends, from anywhere!

It's like a desktop pet - you let it sit there and enjoy the company of your friends as you listen to music with them, around a camp fire, slowly enjoying your day. 😊.


## How we built it

Firejams is a cross-platform, real-time collaborative music listening and queueing app built with Python. Here’s how we put it together:

Oh, and also, **an all nighter debugging a bug caused by base64 😔**.

We implemented everything in native python (crazy, right?!). 

A lot of personalizaiton and beautiful UI. Little things that go a long way. E.g. there's the talking thing you guys can use when yall in a vc or just vibing

### Architecture

- **Client-Server Model:**  
  The app uses a custom server (`jams/server.py`) built with Python, Eventlet, and Socket.IO to manage real-time communication, room management, and music queue synchronization between users.

- **Tkinter GUI:**  
  The user interface is built with Tkinter (`screens/`), providing a desktop app experience on both Windows and Mac. We use custom window transparency and styling for a modern look.

- **Audio Streaming:**  
  Audio playback and streaming are handled with PyAudio and Pydub, allowing synchronized music playback for all users in a room. The server streams audio in chunks to clients.

- **Spotify Integration:**  
  Songs are added to the queue via Spotify track URLs. The server uses [spotdl](https://spotdl.io/) to download tracks and extract metadata and cover art.

### Key Components

- **`main.py`:**  
  Entry point for the app. Initializes the Tkinter root window, client, and landing screen.

- **`jams/client.py`:**  
  Handles the client-side logic, including socket communication, queue management, and audio playback.

- **`jams/server.py`:**  
  Manages rooms, users, queue synchronization, and audio streaming. Uses Eventlet’s WSGI server for async networking.

- **`screens/`:**  
  Contains all the Tkinter UI screens:
  - `landing.py`: Landing page and navigation.
  - `character.py`: Character/color selection.
  - `audio_player_screen.py`: Main music player and fire animation.
  - `queue_screen.py`: Queue management and song addition.
  - `joinhostcode.py`, `loading.py`: Room join/host flows.

- **`custom_classes/`:**  
  Custom color and utility classes for player avatars and UI theming.

- **`utils/`:**  
  Helper modules for audio processing, cropping, and Tkinter compatibility.

- **`assets/`:**  
  All images, icons, and sound effects (fire animation, player avatars, backgrounds, etc.).

### Cross-Platform Support

- **Run Scripts:**  
  - `run.sh` for Mac/Linux (activates `.venv` if present).
  - `run.bat` for Windows.
- **Tkinter Compatibility:**  
  Platform-specific tweaks (e.g., window transparency, `overrideredirect` logic) ensure the app looks and feels native on both Mac and Windows.

### Real-Time Features

- **Socket.IO:**  
  Real-time events keep all clients in sync for queue updates, song changes, and user actions.
- **Voice Detection:**  
  The app uses a simple voice detector to animate avatars when users are talking.

### How it works

1. **Start the app** and join or create a room.
2. **Add songs** by pasting Spotify track URLs.
3. **Listen together:** The server streams the audio to all clients in sync.
4. **Interact:** See who’s in the room, who’s talking, and manage the queue collaboratively.



## Challenges we ran into

A lot
- Threading issues
- APi call issues
- Jsonification issues
- Tkinter issues
- Platform issues
- Streaming audio overflow
- Memory management

its only form the top of my head

## Accomplishments that we're proud of

Threading! Using tkinter! Only python! 

## What's next for FireJams
Integrating AI mood detection to fully use the emotions