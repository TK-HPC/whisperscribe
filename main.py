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
CLI_PATH = os.path.join(ROOT_DIR, "transcribe.cpp/build/bin/transcribe-cli")
SOCKET_PATH = f"/tmp/wisprflow-{os.getuid()}.sock"
RATE = 16000
CHUNK = 1024
WIDTH = 108
HEIGHT = 46


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
        self.stop_event = threading.Event()
        self.levels = queue.SimpleQueue()
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
            *( [54, 23] * 11 ), fill="#ffffff", width=2,
            smooth=True, splinesteps=12, capstyle=tk.ROUND, joinstyle=tk.ROUND,
        )

    def _show(self):
        self.root.deiconify()
        self.root.lift()
        self.root.attributes("-topmost", True)

    def toggle(self):
        if self.status == "listening":
            self.status = "transcribing"
            self.stop_event.clear()
        elif self.status == "idle":
            self.status = "listening"
            self.level = 0.0
            self.stop_event.set()
            self._show()
            threading.Thread(target=self._record_and_transcribe, daemon=True).start()

    def _record_and_transcribe(self):
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
            while self.stop_event.is_set():
                data = stream.read(CHUNK, exception_on_overflow=False)
                frames.append(data)
                samples = np.frombuffer(data, dtype=np.int16).astype(np.float32)
                self.levels.put(float(np.sqrt(np.mean(samples * samples)) / 32768))
        except Exception as error:
            self.root.after(0, lambda error=error: self._show_error(error))
            return
        finally:
            if stream is not None:
                stream.stop_stream()
                stream.close()
            audio.terminate()

        if not frames:
            self.root.after(0, lambda: self._show_error("No audio captured"))
            return

        try:
            with wave.open(OUTPUT_PATH, "wb") as output:
                output.setnchannels(1)
                output.setsampwidth(2)
                output.setframerate(RATE)
                output.writeframes(b"".join(frames))

            result = subprocess.run(
                [CLI_PATH, "-m", MODEL_PATH, OUTPUT_PATH],
                capture_output=True,
                text=True,
                check=True,
            )
            transcript = next(
                line.removeprefix("text: ").strip()
                for line in result.stdout.splitlines()
                if line.startswith("text: ")
            )
            pyperclip.copy(transcript)
            print(transcript, flush=True)
            self.root.after(0, self._show_copied)
        except Exception as error:
            self.root.after(0, lambda error=error: self._show_error(error))

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
        self.stop_event.clear()
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
