import json
import wave
import sys
import os
import time
from pathlib import Path
import threading
import queue

import vosk
import ffmpeg

from socket_server import SocketServer


FRAMES_SIZE = 4000
MIN_CHARS = 4
MONO = 1

CODEC = "pcm_s16le"
RATE = "16000"


class VoskService:
    def __init__(
        self, model_path="model", watch_directory="./input", output_directory="./output"
    ):
        self.model_path = model_path
        self.watch_directory = Path(watch_directory)
        self.output_directory = Path(output_directory)

        self.watch_directory.mkdir(exist_ok=True)
        self.output_directory.mkdir(exist_ok=True)

        print("Cargando modelo...")
        if not os.path.exists(model_path):
            print(f"Modelo no econtrado en {model_path}")
            sys.exit(1)

        self.model = vosk.Model(model_path)
        print("Modelo cargado.")

        self.processing_queue = queue.Queue()
        self.is_running = True

        self.processor_thread = threading.Thread(target=self._processor_worker)
        self.processor_thread.daemon = True
        self.processor_thread.start()

    def _processor_worker(self):
        while self.is_running:
            try:
                file_path = self.processing_queue.get(timeout=1)
                self._transcribe_file(file_path)
                self.processing_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Error en procesamiento: {e}")

    def _convert_to_wav(self, audio_file):
        output_file = self.output_directory / f"temp_{int(time.time())}.wav"
        try:
            (
                ffmpeg.input(str(audio_file))
                .output(str(output_file), acodec=CODEC, ac=MONO, ar=RATE)
                .overwrite_output()
                .run(capture_stdout=True, capture_stderr=True)
            )
            return output_file
        except ffmpeg.Error as e:
            print(f"Error convirtiendo {audio_file}: {e.stderr.decode()}")
            return None

    def _transcribe_file(self, audio_file):
        print(f"Procesando: {audio_file.name}")

        wav_file = self._prepare_audio_file(audio_file)
        if not wav_file:
            return

        try:
            full_text = self._process_audio(wav_file)
            self._cleanup_files(audio_file, wav_file)
            self._send_message(full_text)

        except Exception as e:
            print(f"Error procesando {audio_file}: {e}")

    def _prepare_audio_file(self, audio_file):
        if audio_file.suffix.lower() != ".wav":
            wav_file = self._convert_to_wav(audio_file)
            if not wav_file:
                return None
        else:
            wav_file = audio_file
        return wav_file

    def _process_audio(self, wav_file):
        wf = wave.open(str(wav_file), "rb")

        try:
            self._validate_audio_format(wf, wav_file)
            rec = self._create_recognizer(wf)
            words = self._extract_words(wf, rec)
            return self._get_full_text(words)
        finally:
            wf.close()

    def _validate_audio_format(self, wf, wav_file):
        if wf.getnchannels() != MONO or wf.getsampwidth() != 2:
            raise ValueError(f"formato inválido: {wav_file.name}")

    def _create_recognizer(self, wf):
        rec = vosk.KaldiRecognizer(self.model, wf.getframerate())
        rec.SetWords(True)
        return rec

    def _extract_words(self, wf, rec):
        words = []

        while True:
            data = wf.readframes(FRAMES_SIZE)
            if len(data) == 0:
                break
            if rec.AcceptWaveform(data):
                word = json.loads(rec.Result())
                if word.get("text"):
                    words.append(word)

        final_result = json.loads(rec.FinalResult())
        if final_result.get("text"):
            words.append(final_result)

        return words

    def _cleanup_files(self, original_file, wav_file):
        if wav_file != original_file:
            wav_file.unlink()
        original_file.unlink()

    def _send_message(self, text):
        socket = SocketServer()
        socket.send_message(text)

    def _get_full_text(self, words):
        return " ".join(
            [
                r["text"]
                for r in words
                if r.get("text") and len(r.get("text")) >= MIN_CHARS
            ]
        )
