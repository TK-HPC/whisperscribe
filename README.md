# WhisperScribe

> **Unofficial personal project.** WhisperScribe is homemade and independent. It is not affiliated with, endorsed by, or sponsored by Wispr Flow or its owners. “Wispr Flow” is a trademark of its respective owner.

I was inspired by Wispr Flow, but wanted dictation on **Arch Linux + Hyprland** using a local model. So I decided to try making my own with Qwen3-ASR running on my machine.

I might later experiment with custom vocabulary and fine-tuning for my own voice. For now, it works well enough for me.

**Win+X** starts recording; press it again to stop. The recording is transcribed locally with [transcribe.cpp](https://github.com/handy-computer/transcribe.cpp), and the transcript is copied to the Wayland clipboard.

On my GPU, transcription after recording runs at about **70× real time**. Speed varies with the GPU, model, and audio.

The app records 16 kHz mono audio. The model and recording are local files and are ignored by Git.

## Project layout

```text
WhisperScribe/
├── main.py                         # app entry point
├── README.md
├── pyproject.toml                  # Python dependencies
├── uv.lock                         # locked Python dependency versions
├── .python-version
├── .gitignore
├── model/                          # download the GGUF model here (ignored)
│   └── Qwen3-ASR-1.7B-Q4_K_M.gguf
├── transcribe.cpp/                 # upstream clone (ignored, separate Git repo)
│   └── build/bin/transcribe-cli    # built by CMake
├── 1.wav                           # recording created by the app (ignored)
└── .venv/                          # created by `uv sync` (ignored)
```

`main.py` expects the model and CLI at those exact paths. `src/wisprflow/` is leftover starter-package scaffolding; the Hyprland shortcut runs `main.py` directly.

## Requirements

These instructions are for Arch Linux and Hyprland. Install the system tools:

```bash
sudo pacman -S --needed base-devel cmake cuda portaudio tk wl-clipboard uv
```

The CUDA toolkit is needed for the NVIDIA build below. For a CPU-only build, skip `cuda` and turn off the CUDA option in the build command. Install a working NVIDIA driver for CUDA acceleration.

## Set up the Python app

From the project directory:

```bash
uv sync
```

This creates `.venv` and installs the locked Python dependencies. `main.py` uses Tkinter for the capsule, PyAudio for recording, and `pyperclip` to copy the transcript.

## Get and compile transcribe.cpp

If `transcribe.cpp/` is not already present, clone the upstream project into this directory. It is a separate Git repository and is intentionally ignored by this app's Git repository:

```bash
git clone https://github.com/handy-computer/transcribe.cpp.git
```

Build the CUDA CLI used by `main.py`:

```bash
cd transcribe.cpp
cmake -B build \
  -DTRANSCRIBE_CUDA=ON \
  -DTRANSCRIBE_USE_SYSTEM_BLAS=OFF \
  -DCMAKE_BUILD_TYPE=Release
cmake --build build --target transcribe-cli -j"$(nproc)"
cd ..
```

For CPU-only, set `-DTRANSCRIBE_CUDA=OFF` (or omit the CUDA option) and build the same `transcribe-cli` target. The executable must end up at `transcribe.cpp/build/bin/transcribe-cli`, which is the path `main.py` calls.

## Download the model

Download the Q4_K_M model used by the app (about 1.32 GB):

```bash
mkdir -p model
curl -fL \
  'https://huggingface.co/handy-computer/Qwen3-ASR-1.7B-gguf/resolve/main/Qwen3-ASR-1.7B-Q4_K_M.gguf' \
  -o model/Qwen3-ASR-1.7B-Q4_K_M.gguf
```

The model is hosted in the [`handy-computer/Qwen3-ASR-1.7B-gguf`](https://huggingface.co/handy-computer/Qwen3-ASR-1.7B-gguf) repository. Other quantizations and details are in the upstream [Qwen3-ASR model guide](https://github.com/handy-computer/transcribe.cpp/blob/main/docs/models/qwen3-asr-1.7b.md).

## Add the shortcut and capsule to Hyprland

In `~/.config/hypr/hyprland.lua`, add a key binding. Replace `/path/to/WhisperScribe` with this project's directory:

```lua
hl.bind("SUPER + X", hl.dsp.exec_cmd(
    "/path/to/WhisperScribe/.venv/bin/python /path/to/WhisperScribe/main.py"
))
```

Also add this window rule so the capsule floats at the bottom center without taking focus:

```lua
hl.window_rule({
    name  = "whisperscribe-capsule",
    match = { title = "^WhisperScribe Capsule$" },
    float = true,
    no_focus = true,
    no_blur = true,
    move = { "(monitor_w-window_w)/2", "monitor_h-window_h-48" },
})
```

Reload Hyprland:

```bash
hyprctl reload
```

Press **Win+X** once to start recording and again to stop and transcribe. The transcript is copied to the clipboard; paste it where you need it. The CLI can also transcribe a 16 kHz mono WAV directly:

```bash
./transcribe.cpp/build/bin/transcribe-cli \
  -m model/Qwen3-ASR-1.7B-Q4_K_M.gguf \
  /path/to/audio-16k-mono.wav
```

Convert audio to the required format with FFmpeg if needed:

```bash
ffmpeg -i input.wav -ar 16000 -ac 1 /tmp/audio-16k-mono.wav
```
