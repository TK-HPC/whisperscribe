import os
import subprocess
import threading
import wave

import numpy as np
import pyaudio

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_PATH = os.path.join(ROOT_DIR, "1.wav")
MODEL_PATH = os.path.join(ROOT_DIR, "model/Qwen3-ASR-1.7B-Q4_K_M.gguf")
KEYWORDS_PATH = os.path.join(ROOT_DIR, "keywords.txt")
CLI_PATH = os.path.join(ROOT_DIR, "transcribe.cpp/build/bin/transcribe-cli")
RATE = 16000
CHUNK = 1024


class Transcriber:
    def __init__(self):
        self.recording = threading.Event()
        self.level = 0.0
        self.transcript = None

    def start(self):
        self.level = 0.0
        self.transcript = None
        self.recording.set()
        threading.Thread(target=self._run, daemon=True).start()

    def stop(self):
        self.recording.clear()

    def _run(self):
        frames = self._record()
        self.transcript = self._transcribe(frames)

    def _record(self):
        frames = []
        audio = pyaudio.PyAudio()
        stream = audio.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=RATE,
            input=True,
            frames_per_buffer=CHUNK,
        )
        try:
            while self.recording.is_set():
                data = stream.read(CHUNK, exception_on_overflow=False)
                frames.append(data)
                samples = np.frombuffer(data, dtype=np.int16).astype(np.float32)
                self.level = float(np.sqrt(np.mean(samples * samples)) / 32768)
        finally:
            stream.stop_stream()
            stream.close()
            audio.terminate()
        return frames

    @staticmethod
    def _transcribe(frames):
        with wave.open(OUTPUT_PATH, "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(RATE)
            output.writeframes(b"".join(frames))

        result = subprocess.run(
            [CLI_PATH, "-m", MODEL_PATH, "--vocabulary-file", KEYWORDS_PATH, OUTPUT_PATH],
            capture_output=True,
            text=True,
            check=True,
        )
        for line in result.stdout.splitlines():
            if line.startswith("text: "):
                return line.removeprefix("text: ").strip()
        raise RuntimeError("transcribe-cli returned no transcript")
