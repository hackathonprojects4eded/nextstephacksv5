class SongQueue:
    def __init__(self, queue):
        self.queue = queue  # should be a list of dictinoaries
        self.current_idx = 0

    # def add_song(self, song_data):
    #     """Add a song to the queue."""
    #     self.queue.append(song_data)
    #     self.sync_queue_with_friends(self.queue)

    def add_url_to_queue(self, app, url):
        """Add a URL to the queue by sending it to the server for processing."""
        # Send URL to server for download and processing
        app.client.sio.emit(
            "add_url_to_queue", {"room_code": app.client.room_code, "url": url}
        )

    def shuffle_queue(self, app, client=None):
        """Shuffle the queue (excluding the current song)."""
        import random

        # Get the queue excluding the current song
        if hasattr(self, "current_idx") and self.current_idx < len(self.queue):
            # Shuffle the remaining songs after the current one
            remaining_songs = self.queue[self.current_idx + 1 :]
            random.shuffle(remaining_songs)
            # Reconstruct the queue with current song + shuffled remaining songs
            self.queue = self.queue[: self.current_idx + 1] + remaining_songs
        else:
            # If no current song, shuffle the entire queue
            random.shuffle(self.queue)

        # Update the UI if available
        if hasattr(app, "queue_ui") and app.queue_ui:
            app.queue_ui.display_queue()

        # Call sync function with client reference
        self.sync_queue_with_friends(self.queue, client)

    def sync_queue_with_friends(self, queue, client=None):
        """Sync queue with friends via Socket.IO."""
        # Send queue to server for synchronization
        if client and hasattr(client, "sync_queue_with_server"):
            # Use the client's sync method
            client.sync_queue_with_server(queue)
        else:
            # Fallback - the actual sync will be handled by the client
            # when it receives queue updates from the server
            print("[SYNC] Queue sync requested:", len(queue), "songs")
            print("[SYNC] No client reference available for direct sync")

    def remove_from_queue(self, idx: int):
        if 0 <= idx < len(self.queue):
            del self.queue[idx]
