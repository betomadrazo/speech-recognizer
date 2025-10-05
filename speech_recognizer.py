import json
import wave
import sys
import os
import time
from pathlib import Path
import vosk
import ffmpeg
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import threading
import queue

from socket_server import SocketServer


class VoskTranscriptionService:
    def __init__(
        self, model_path="model", watch_directory="./input", output_directory="./output"
    ):
        self.model_path = model_path
        self.watch_directory = Path(watch_directory)
        self.output_directory = Path(output_directory)

        # Create directories if they don't exist
        self.watch_directory.mkdir(exist_ok=True)
        self.output_directory.mkdir(exist_ok=True)

        # Load Vosk model once
        print(f"Loading Vosk model from {model_path}...")
        if not os.path.exists(model_path):
            print(f"Model not found at {model_path}")
            print("Download a model from https://alphacephei.com/vosk/models")
            sys.exit(1)

        self.model = vosk.Model(model_path)
        print("✓ Model loaded successfully!")

        # Processing queue
        self.processing_queue = queue.Queue()
        self.is_running = True

        # Start processing thread
        self.processor_thread = threading.Thread(target=self._processor_worker)
        self.processor_thread.daemon = True
        self.processor_thread.start()

    def _processor_worker(self):
        """Worker thread that processes files from the queue"""
        while self.is_running:
            try:
                file_path = self.processing_queue.get(timeout=1)
                self._transcribe_file(file_path)
                self.processing_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Error in processor worker: {e}")

    def _convert_to_wav(self, input_file):
        """Convert audio/video to WAV"""
        output_file = self.output_directory / f"temp_{int(time.time())}.wav"
        try:
            (
                ffmpeg.input(str(input_file))
                .output(str(output_file), acodec="pcm_s16le", ac=1, ar="16000")
                .overwrite_output()
                .run(capture_stdout=True, capture_stderr=True)
            )
            return output_file
        except ffmpeg.Error as e:
            print(f"Error converting {input_file}: {e.stderr.decode()}")
            return None

    def _transcribe_file(self, audio_file):
        """Transcribe a single file"""
        start_time = time.time()
        print(f"🎵 Processing: {audio_file.name}")

        # Convert to WAV if needed
        if audio_file.suffix.lower() != ".wav":
            wav_file = self._convert_to_wav(audio_file)
            if not wav_file:
                return
        else:
            wav_file = audio_file

        try:
            # Open and process WAV
            wf = wave.open(str(wav_file), "rb")

            if wf.getnchannels() != 1 or wf.getsampwidth() != 2:
                print(f"❌ Invalid audio format for {audio_file.name}")
                return

            # Create recognizer (fast since model is already loaded)
            rec = vosk.KaldiRecognizer(self.model, wf.getframerate())
            rec.SetWords(True)

            results = []

            # Process audio
            while True:
                data = wf.readframes(4000)
                if len(data) == 0:
                    break
                if rec.AcceptWaveform(data):
                    result = json.loads(rec.Result())
                    if result.get("text"):
                        results.append(result)

            # Final result
            final_result = json.loads(rec.FinalResult())
            if final_result.get("text"):
                results.append(final_result)

            # Combine text
            MIN_CHARS = 4
            full_text = " ".join(
                [
                    r["text"]
                    for r in results
                    if r.get("text") and len(r.get("text")) >= MIN_CHARS
                ]
            )

            # Save result
            # output_file = self.output_directory / f"{audio_file.stem}.txt"
            # with open(output_file, "w", encoding="utf-8") as f:
            #     f.write(full_text)

            # Clean up
            wf.close()
            if wav_file != audio_file:
                wav_file.unlink()

            # Remove original file after processing
            audio_file.unlink()

            processing_time = time.time() - start_time
            # print(
            #     f"✅ Completed {audio_file.name} in {processing_time:.2f}s -> {output_file.name}"
            # )

            self._send_message(full_text)

        except Exception as e:
            print(f"❌ Error processing {audio_file}: {e}")

    def _send_message(self, text):
        # Send result to socket
        socket = SocketServer()
        socket.send_message(text)

class AudioFileHandler(FileSystemEventHandler):
    def __init__(self, service):
        self.service = service
        self.supported_formats = {
            ".mp3",
            ".wav",
            ".mp4",
            ".avi",
            ".mov",
            ".m4a",
            ".flac",
            ".ogg",
        }

    def on_created(self, event):
        if not event.is_directory:
            file_path = Path(event.src_path)
            if file_path.suffix.lower() in self.supported_formats:
                print(f"📁 New file detected: {file_path.name}")
                # Add small delay to ensure file is fully written
                time.sleep(0.5)
                self.service.processing_queue.put(file_path)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Vosk Transcription Service")
    parser.add_argument("-m", "--model", default="model", help="Vosk model directory")
    parser.add_argument(
        "-w", "--watch", default="./input", help="Directory to watch for audio files"
    )
    parser.add_argument(
        "-o", "--output", default="./output", help="Output directory for transcriptions"
    )

    args = parser.parse_args()

    # Create service
    service = VoskTranscriptionService(args.model, args.watch, args.output)

    # Set up file watcher
    event_handler = AudioFileHandler(service)
    observer = Observer()
    observer.schedule(event_handler, str(service.watch_directory), recursive=False)
    observer.start()

    print(f"🚀 Vosk Transcription Service started!")
    print(f"📂 Watching: {service.watch_directory}")
    print(f"📄 Output: {service.output_directory}")
    print("🎯 Drop audio/video files in the input directory to transcribe them")
    print("Press Ctrl+C to stop")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 Stopping service...")
        service.is_running = False
        observer.stop()
        observer.join()
        print("✅ Service stopped")


if __name__ == "__main__":
    main()
