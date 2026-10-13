"""
A room's shared playback: one queue and where everyone is in it. The server owns
it and broadcasts state(); clients send commands and play/render what comes back.
`now` is time.time() seconds, passed in so the logic is easy to test.
"""

import itertools
import random


class Jam:
    def __init__(self):
        self.queue = []  # played and upcoming tracks, in order
        self.current = 0  # index of the playing track; == len(queue) when idle
        self.is_playing = False
        self.position_ms = 0  # playback position as of `since`
        self.since = 0.0
        self._keys = itertools.count(1)  # tells apart two copies of one song

    @property
    def track(self):
        return self.queue[self.current] if self.current < len(self.queue) else None

    def position(self, now):
        if self.is_playing:
            return self.position_ms + int((now - self.since) * 1000)
        return self.position_ms

    def state(self, now):
        """What everyone plays and renders."""
        return {
            "track": self.track,
            "is_playing": self.is_playing,
            "progress_ms": self.position(now),
            "queue": self.queue[self.current + 1 :],
            # ponytail: every song played this session rides along in each broadcast;
            # send only the last few if a long session makes broadcasts slow
            "history": self.queue[: self.current],
        }

    def _go(self, index, now):
        """Play queue[index] from the top (past the end = idle)."""
        self.current = min(max(index, 0), len(self.queue))
        self.position_ms, self.since = 0, now
        self.is_playing = self.track is not None

    def add(self, track, now):
        idle = self.track is None
        self.queue.append({**track, "key": next(self._keys)})
        if idle:
            self._go(self.current, now)

    def play(self, now):
        if self.track and not self.is_playing:
            self.since, self.is_playing = now, True

    def pause(self, now):
        if self.is_playing:
            self.position_ms, self.is_playing = self.position(now), False

    def seek(self, position_ms, now):
        if self.track:
            self.position_ms = min(max(int(position_ms), 0), self.track["duration_ms"])
            self.since = now

    def next(self, now):
        self._go(self.current + 1, now)

    def previous(self, now):
        self._go(self.current - 1, now)

    def jump(self, key, now):
        """Play a queued song right away."""
        self._go(self._index(key), now)

    def remove(self, key):
        """Drop an upcoming song."""
        i = self._index(key)
        if i > self.current:
            del self.queue[i]

    def move(self, key, index):
        """Put an upcoming song at `index` of what's up next (0 = plays next)."""
        index, i = int(index), self._index(key)
        if i > self.current:
            track = self.queue.pop(i)
            index = min(max(index, 0), len(self.queue) - self.current - 1)
            self.queue.insert(self.current + 1 + index, track)

    def shuffle(self):
        """Shuffle what's up next; the playing song keeps playing."""
        upcoming = self.queue[self.current + 1 :]
        random.shuffle(upcoming)
        self.queue[self.current + 1 :] = upcoming

    def tick(self, now):
        """Move on when the song ends. True if anything changed."""
        if self.is_playing and self.position(now) >= self.track["duration_ms"]:
            self.next(now)
            return True
        return False

    def _index(self, key):
        i = next((i for i, t in enumerate(self.queue) if t["key"] == key), None)
        if i is None:
            raise ValueError("That song isn't in the queue anymore")
        return i
