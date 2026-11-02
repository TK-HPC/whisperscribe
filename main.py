import math
import os
from pathlib import Path
import socket
import subprocess
import time
import tkinter as tk

import pyperclip

from transcriber import Transcriber

SOCKET_PATH = f"/tmp/wisprflow-{os.getuid()}.sock"
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
        self.transcriber = Transcriber()
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

    def _handle_transcript(self, transcript):
        pyperclip.copy(transcript)
        subprocess.run(
            [
                "hyprctl", "eval",
                "hl.dispatch(hl.dsp.send_shortcut({mods = 'CTRL+SHIFT', key = 'V'}))",
            ],
            capture_output=True,
            text=True,
        )
        print(transcript, flush=True)
        self._show_copied()

    def _show_copied(self):
        self.status = "copied"
        self.root.after(700, self._hide)

    def _hide(self):
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
        self.level = self.transcriber.level
        if self.transcriber.error:
            print(f"WhisperScribe: {self.transcriber.error}", flush=True)
            self.transcriber.error = None
            self._hide()
        elif self.transcriber.transcript is not None:
            transcript = self.transcriber.transcript
            self.transcriber.transcript = None
            self._handle_transcript(transcript)

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
        Path(SOCKET_PATH).unlink(missing_ok=True)
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
        Path(SOCKET_PATH).unlink(missing_ok=True)
        app = Capsule()
        app.toggle()
        app.run()
