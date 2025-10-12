import argparse
import time

from watchdog.observers import Observer

from vosk_service import VoskService
from audio_file_handler import AudioFileHandler


def main():

    parser = argparse.ArgumentParser()
    parser.add_argument("-m", "--model", default="model", help="Directorio del modelo")
    parser.add_argument(
        "-w",
        "--watch",
        default="./input",
        help="Directorio donde se depositan los audios input",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="./output",
        help="Directorio donde se ponen los outputs",
    )

    args = parser.parse_args()

    service = VoskService(args.model, args.watch, args.output)

    event_handler = AudioFileHandler(service)
    observer = Observer()
    observer.schedule(event_handler, str(service.watch_directory), recursive=False)
    observer.start()

    print("Servicio iniciado\n")
    print("Esperando input")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        service.is_running = False
        observer.stop()
        observer.join()


if __name__ == "__main__":
    main()
