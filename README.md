# NEXAURA FUSE

**Merge Windows and Linux workspaces** - Keeps `NEXAURA DEVELOPER` in sync across OSes. Tray daemon that migrates app configs, sessions, and models to the shared `SHARED/MODELS` drive while keeping executables on the host.

![Logo](assets/logo-256.png)

## Quick Start
```bash
# Linux / Zorin
python3 fuse.py --merge all
# Or run tray
python3 fuse.py

# Windows (exe)
FUSE.exe
```

## Usage
- **Tray:** Right-click `NEXAURA FUSE` icon -> `Merge all` / `Merge app` -> `claude|opencode|zcode|air|lmstudio|ollama|jan` / `Sync models to providers` / `Open DEVELOPER`
- **CLI:** `python fuse.py lmstudio` or `FUSE.exe lmstudio`

## What it does
- Migrates `~/.config`, `~/.cache`, `~/.local/share`, `~/.var`, `~/Documents` to `/mnt/NEXAURA/DEVELOPER/<App>/` and symlinks back
- Watches `SHARED/MODELS` (`/mnt/NEXAURA/DEVELOPER/SHARED/MODELS` -> `Models/Global`) for new `*.gguf` and auto-adds to `opencode`, `claude`, `lmstudio`, `ollama`, `jan` via `ollama create` / `lms import` and provider JSON
- Keeps `ollama` `OLLAMA_MODELS=/mnt/NEXAURA/DEVELOPER/Models/Ollama` and `lmstudio` `downloadsFolder` on `SHARED`

## Shared Models
- **Global:** `SHARED/MODELS` (`/mnt/NEXAURA/DEVELOPER/SHARED/MODELS` -> `Models/Global`) - raw GGUFs, visible on both OSes as `NEXAURA:\DEVELOPER\SHARED\MODELS`
- **Ollama:** `Models/Ollama` blobs at same path
- **For JAN:** Set `Settings -> Models Directory -> /mnt/NEXAURA/DEVELOPER/SHARED/MODELS` then `/merge jan`

## Install
- **Linux:** `pip install -r requirements.txt && python fuse.py` or `FUSE` binary
- **Windows:** `FUSE.exe` (PyInstaller) - auto finds `NEXAURA` drive via `DEVELOPER` folder
- **Autostart:** `~/.config/autostart/nexaura-fuse.desktop` `Exec=python3 /path/to/fuse.py`

## Cross-platform
- Linux: `AyatanaAppIndicator3` / `pystray`, Windows: `pystray` native, macOS: `pystray`
- Single `fuse.py` works everywhere, `PyInstaller` builds `FUSE.exe` / `FUSE` / `FUSE.app`

## License
MIT - EvercoreNetwork
