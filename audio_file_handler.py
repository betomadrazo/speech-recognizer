import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler


class AudioFileHandler(FileSystemEventHandler):
    def __init__(self, service):
        self.service = service
        self.supported_formats = {
            ".mp3",
            ".wav",
            ".flac",
        }

    def on_created(self, event):
        if not event.is_directory:
            file_path = Path(event.src_path)
            if file_path.suffix.lower() in self.supported_formats:
                time.sleep(0.5)
                self.service.processing_queue.put(file_path)
