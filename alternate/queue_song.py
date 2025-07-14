import time
import random


class QueueSong:
    def __init__(self):
        self.queue = []
        self.current_idx = -1  # -1 means no song is currently playing

    def add_url_to_queue(self, url):
        """Add a URL to the queue with mock metadata."""
        # Create mock song metadata for demonstration
        mock_song = {
            "title": f"Song from {url[:20]}...",
            "artist": "Unknown Artist",
            "url": url,
            "length": random.randint(120, 300),  # Random duration between 2-5 minutes
            "cover_image": None,  # No cover image for mock songs
            "added_at": time.time(),
        }

        self.queue.append(mock_song)
        print(f"Added song to queue: {mock_song['title']}")
        return len(self.queue) - 1  # Return the index of the added song

    def remove_from_queue(self, idx):
        """Remove a song from the queue at the given index."""
        if 0 <= idx < len(self.queue):
            removed_song = self.queue.pop(idx)
            print(f"Removed song from queue: {removed_song['title']}")

            # Adjust current_idx if necessary
            if self.current_idx >= idx:
                self.current_idx = max(0, self.current_idx - 1)

            return True
        return False

    def get_current_song(self):
        """Get the currently playing song."""
        if 0 <= self.current_idx < len(self.queue):
            return self.queue[self.current_idx]
        return None

    def get_next_song(self):
        """Get the next song in the queue."""
        next_idx = self.current_idx + 1
        if 0 <= next_idx < len(self.queue):
            return self.queue[next_idx]
        return None

    def get_previous_song(self):
        """Get the previous song in the queue."""
        prev_idx = self.current_idx - 1
        if 0 <= prev_idx < len(self.queue):
            return self.queue[prev_idx]
        return None

    def shuffle_queue(self):
        """Shuffle the queue while preserving the current song."""
        if len(self.queue) <= 1:
            return

        current_song = self.get_current_song()

        # Shuffle the queue
        random.shuffle(self.queue)

        # Find the current song in the shuffled queue and update current_idx
        if current_song:
            try:
                self.current_idx = self.queue.index(current_song)
            except ValueError:
                self.current_idx = -1  # Current song not found in shuffled queue

        print("Queue shuffled")

    def clear_queue(self):
        """Clear the entire queue."""
        self.queue.clear()
        self.current_idx = -1
        print("Queue cleared")

    def get_queue_length(self):
        """Get the total number of songs in the queue."""
        return len(self.queue)

    def is_empty(self):
        """Check if the queue is empty."""
        return len(self.queue) == 0

    def get_queue_info(self):
        """Get information about the queue."""
        return {
            "total_songs": len(self.queue),
            "current_index": self.current_idx,
            "current_song": self.get_current_song(),
            "next_song": self.get_next_song(),
            "previous_song": self.get_previous_song(),
        }
