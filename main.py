import math
import os
import queue
import socket
import subprocess
import threading
import time
import tkinter as tk
import wave

import numpy as np
import pyaudio
import pyperclip

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_PATH = os.path.join(ROOT_DIR, "1.wav")
MODEL_PATH = os.path.join(ROOT_DIR, "model/Qwen3-ASR-1.7B-Q4_K_M.gguf")
KEYWORDS_PATH = os.path.join(ROOT_DIR, "keywords.txt")
CLI_PATH = os.path.join(ROOT_DIR, "transcribe.cpp/build/bin/transcribe-cli")
SOCKET_PATH = f"/tmp/wisprflow-{os.getuid()}.sock"
RATE = 16000
CHUNK = 1024
WIDTH = 108
HEIGHT = 46


class Transcriber:
    def __init__(self, on_level, on_transcript, on_error):
        self.on_level = on_level
        self.on_transcript = on_transcript
        self.on_error = on_error
        self.recording = threading.Event()

    def start(self):
        self.recording.set()
        threading.Thread(target=self._run, daemon=True).start()

    def stop(self):
        self.recording.clear()

    def _run(self):
        try:
            frames = self._record()
            if not frames:
                raise RuntimeError("No audio captured")
            self._write_audio(frames)
            self.on_transcript(self._transcribe())
        except Exception as error:
            self.on_error(error)

    def _record(self):
        frames = []
        audio = pyaudio.PyAudio()
        stream = None
        try:
            stream = audio.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=RATE,
                input=True,
                frames_per_buffer=CHUNK,
            )
            while self.recording.is_set():
                data = stream.read(CHUNK, exception_on_overflow=False)
                frames.append(data)
                samples = np.frombuffer(data, dtype=np.int16).astype(np.float32)
                self.on_level(float(np.sqrt(np.mean(samples * samples)) / 32768))
        finally:
            if stream is not None:
                stream.stop_stream()
                stream.close()
            audio.terminate()
        return frames

    @staticmethod
    def _write_audio(frames):
        with wave.open(OUTPUT_PATH, "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(RATE)
            output.writeframes(b"".join(frames))

    @staticmethod
    def _transcribe():
        command = [CLI_PATH, "-m", MODEL_PATH]
        if os.path.isfile(KEYWORDS_PATH):
            command.extend(["--vocabulary-file", KEYWORDS_PATH])
        result = subprocess.run(
            [*command, OUTPUT_PATH],
            capture_output=True,
            text=True,
            check=True,
        )
        for line in result.stdout.splitlines():
            if line.startswith("text: "):
                return line.removeprefix("text: ").strip()
        raise RuntimeError("transcribe-cli returned no transcript")


class Capsule:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("WhisperScribe Capsule")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg="#050607")
        self.root.geometry(f"{WIDTH}x{HEIGHT}")

        self.canvas = tk.Canvas(
            self.root, width=WIDTH, height=HEIGHT,
            bg="#050607", highlightthickness=0,
        )
        self.canvas.pack()
        self._draw_capsule()

        self.status = "idle"
        self.level = 0.0
        self.levels = queue.SimpleQueue()
        self.transcriber = Transcriber(
            on_level=self.levels.put,
            on_transcript=self._transcription_finished,
            on_error=self._transcription_failed,
        )
        self.commands = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self.commands.bind(SOCKET_PATH)
        self.commands.setblocking(False)

        self.root.withdraw()
        self.root.after(40, self._tick)
        self.root.after(40, self._poll_commands)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def _draw_capsule(self):
        c = self.canvas
        c.create_oval(2, 2, 42, 42, fill="#0c0e10", outline="")
        c.create_rectangle(22, 2, 86, 42, fill="#0c0e10", outline="")
        c.create_oval(66, 2, 106, 42, fill="#0c0e10", outline="")
        self.waveform = c.create_line(
            *([54, 23] * 11), fill="#ffffff", width=2,
            smooth=True, splinesteps=12, capstyle=tk.ROUND, joinstyle=tk.ROUND,
        )

    def _show(self):
        self.root.deiconify()
        self.root.lift()
        self.root.attributes("-topmost", True)

    def toggle(self):
        if self.status == "listening":
            self.status = "transcribing"
            self.transcriber.stop()
            self.root.withdraw()
        elif self.status == "idle":
            self.status = "listening"
            self.level = 0.0
            self._show()
            self.transcriber.start()

    def _transcription_finished(self, transcript):
        self.root.after(0, self._handle_transcript, transcript)

    def _transcription_failed(self, error):
        self.root.after(0, self._show_error, error)

    def _handle_transcript(self, transcript):
        pyperclip.copy(transcript)
        try:
            subprocess.run(
                [
                    "hyprctl", "eval",
                    "hl.dispatch(hl.dsp.send_shortcut({mods = 'CTRL+SHIFT', key = 'V'}))",
                ],
                capture_output=True,
                text=True,
                check=True,
            )
        except (OSError, subprocess.CalledProcessError) as error:
            print(
                f"WhisperScribe: copied transcript, but auto-paste failed: {error}",
                flush=True,
            )
        print(transcript, flush=True)
        self._show_copied()

    def _show_copied(self):
        self.status = "copied"
        self.root.after(700, self._hide)

    def _show_error(self, error):
        self.status = "error"
        print(f"WhisperScribe: {error}", flush=True)
        self.root.after(1200, self._hide)

    def _hide(self):
        if self.status != "listening":
            self.status = "idle"
            self.level = 0.0
            self.root.withdraw()

    def _poll_commands(self):
        try:
            while self.commands.recv(32):
                self.toggle()
        except BlockingIOError:
            pass
        self.root.after(40, self._poll_commands)

    def _tick(self):
        while not self.levels.empty():
            self.level = self.levels.get()

        amplitude = min(1.0, self.level * 7.0) if self.status == "listening" else 0.2
        now = time.monotonic()
        points = []
        for index in range(11):
            pulse = 0.15 + 0.85 * abs(math.sin(now * 8.0 - index * 0.65))
            height = 1 + 9 * amplitude * pulse
            points.extend((34 + index * 4, 23 + math.sin(index * 0.8 + now * 5) * height))
        self.canvas.coords(self.waveform, *points)

        self.root.after(40, self._tick)

    def close(self):
        self.transcriber.stop()
        self.commands.close()
        try:
            os.unlink(SOCKET_PATH)
        except FileNotFoundError:
            pass
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def toggle_running_app():
    client = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    try:
        client.sendto(b"toggle", SOCKET_PATH)
        return True
    except OSError:
        return False
    finally:
        client.close()


if __name__ == "__main__":
    if not toggle_running_app():
        try:
            os.unlink(SOCKET_PATH)
        except FileNotFoundError:
            pass
        app = Capsule()
        app.toggle()
        app.run()
