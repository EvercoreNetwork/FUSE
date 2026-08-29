#!/usr/bin/env python3
"""
NEXAURA FUSE - Merge Windows and Linux workspaces
Tray daemon that keeps NEXAURA DEVELOPER in sync across OSes.
Cross-platform: Linux (AyatanaAppIndicator3/Gtk), Windows (pystray native), macOS.
"""
import os, sys, json, pathlib, shutil, subprocess, threading, time
from pathlib import Path

# Config
HOME = Path.home()
NEXAURA_MNT = Path("/mnt/NEXAURA")
if not NEXAURA_MNT.exists():
    # Windows: find NEXAURA drive
    for d in "DEFGHIJKLMNOPQRSTUVWXYZ":
        p = Path(f"{d}:/")
        if (p / "DEVELOPER").exists():
            NEXAURA_MNT = p
            break
    else:
        NEXAURA_MNT = HOME / "NEXAURA"

DEVELOPER = NEXAURA_MNT / "DEVELOPER"
SHARED_MODELS = DEVELOPER / "SHARED" / "MODELS"
GLOBAL_MODELS = DEVELOPER / "Models" / "Global"
OLLAMA_MODELS = DEVELOPER / "Models" / "Ollama"

APPS = {
    "claude": {"src": HOME / ".config/Claude", "dst": DEVELOPER / "Claude"},
    "opencode": {"src": HOME / ".config/opencode", "dst": DEVELOPER / "OpenCode/config"},
    "opencode-share": {"src": HOME / ".local/share/opencode", "dst": DEVELOPER / "OpenCode/share"},
    "opencode-cache": {"src": HOME / ".cache/opencode", "dst": DEVELOPER / "OpenCode/cache"},
    "opencode-desktop": {"src": HOME / ".config/ai.opencode.desktop", "dst": DEVELOPER / "OpenCode/desktop"},
    "zcode": {"src": HOME / ".config/ZCode", "dst": DEVELOPER / "Zcode/config"},
    "zcode-share": {"src": HOME / ".zcode", "dst": DEVELOPER / "Zcode/share"},
    "jetbrains-config": {"src": HOME / ".config/JetBrains", "dst": DEVELOPER / "JetBrains/config"},
    "jetbrains-share": {"src": HOME / ".local/share/JetBrains", "dst": DEVELOPER / "JetBrains/share"},
    "jetbrains-cache": {"src": HOME / ".cache/JetBrains", "dst": DEVELOPER / "JetBrains/cache"},
    "lmstudio": {"src": HOME / ".var/app/ai.lmstudio.lm-studio/.lmstudio", "dst": DEVELOPER / "LMStudio/.lmstudio"},
    "codex": {"src": HOME / ".codex", "dst": DEVELOPER / "Codex"},
    "gemini": {"src": HOME / ".gemini", "dst": DEVELOPER / "Gemini"},
    "projects": {"src": HOME / "Documents", "dst": DEVELOPER / "Projects"},
}

def ensure_mounted():
    return DEVELOPER.exists()

def merge_app(app):
    cfg = APPS.get(app)
    if not cfg:
        return f"Unknown app {app}. Try: {', '.join(APPS)}"
    src, dst = cfg["src"], cfg["dst"]
    if not ensure_mounted():
        return "NEXAURA not mounted at /mnt/NEXAURA"
    if src.is_symlink() and dst.exists():
        return f"{app} already merged -> {dst}"
    if not src.exists():
        return f"{app} source not found {src}"
    dst.parent.mkdir(parents=True, exist_ok=True)
    # remove singleton locks
    for pat in ["Singleton*"]:
        for f in src.glob(pat):
            try: f.unlink()
            except: pass
    # rsync-like copy
    if dst.exists():
        return f"{app} dst exists, skipping"
    shutil.copytree(src, dst, symlinks=True)
    # backup
    bak = Path(str(src) + ".bak")
    if not bak.exists():
        src.rename(bak)
    else:
        # remove original if bak exists
        if src.is_dir():
            shutil.rmtree(src)
        else:
            src.unlink()
    src.symlink_to(dst)
    return f"{app} merged {src} -> {dst}"

def sync_models_to_providers():
    """When a GGUF appears in SHARED/MODELS, add it to opencode etc."""
    if not SHARED_MODELS.exists():
        return "SHARED/MODELS not found"
    ggufs = list(SHARED_MODELS.glob("*.gguf")) + list(SHARED_MODELS.glob("**/*.gguf"))
    if not ggufs:
        return "No GGUFs in SHARED/MODELS"
    # OpenCode
    opencode_cfg = HOME / ".config/opencode/config/opencode.jsonc"
    # Actually via symlink at DEVELOPER/OpenCode/config
    try:
        p = DEVELOPER / "OpenCode/config/opencode.jsonc"
        if p.exists():
            import json
            data = json.loads(p.read_text())
            changed = False
            for g in ggufs:
                model_id = f"shared/{g.stem}"
                for prov in data.get("provider", {}).values():
                    if "models" in prov and model_id not in prov["models"]:
                        prov["models"][model_id] = {"name": g.stem.replace("-", " ").title()}
                        changed = True
            if changed:
                p.write_text(json.dumps(data, indent=2))
                return f"Added {len(ggufs)} models to opencode"
    except Exception as e:
        return f"opencode sync err: {e}"
    return f"Found {len(ggufs)} models in SHARED/MODELS"

def get_status():
    mounted = ensure_mounted()
    try:
        import psutil
        disk = psutil.disk_usage(str(DEVELOPER)) if mounted else None
    except:
        disk = None
    models = len(list(SHARED_MODELS.glob("**/*.gguf"))) if SHARED_MODELS.exists() else 0
    return {
        "mounted": mounted,
        "disk": f"{disk.free//1024**3}GB free" if disk else "n/a",
        "models": models,
        "apps_merged": sum(1 for v in APPS.values() if v["src"].is_symlink())
    }

# Tray
def run_tray():
    try:
        import pystray
        from PIL import Image
        # Try Ayatana on Linux
        try:
            import gi
            gi.require_version('AyatanaAppIndicator3', '0.1')
            from gi.repository import AyatanaAppIndicator3 as AppIndicator, Gtk
            HAS_AYATANA = True
        except:
            HAS_AYATANA = False

        # Icon
        icon_path = DEVELOPER / "FUSE/assets/logo-256.png"
        if not icon_path.exists():
            icon_path = Path(__file__).parent / "assets/logo-256.png"
        image = Image.open(icon_path) if icon_path.exists() else Image.new('RGBA', (64,64), (10,10,12,255))

        def on_merge_all(icon, item):
            for app in APPS:
                print(merge_app(app))

        def on_merge_app(icon, item, app=None):
            if app:
                print(merge_app(app))

        def on_sync_models(icon, item):
            print(sync_models_to_providers())

        def on_open_developer(icon, item):
            import webbrowser, platform
            path = str(DEVELOPER)
            if platform.system() == "Windows":
                os.startfile(path)
            elif platform.system() == "Darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])

        def on_quit(icon, item):
            icon.stop()
            os._exit(0)

        s = get_status()
        menu = pystray.Menu(
            pystray.MenuItem(f"NEXAURA FUSE - {s['disk']} {s['models']} models", None, enabled=False),
            pystray.MenuItem("Merge all", on_merge_all),
            pystray.MenuItem("Merge app", pystray.Menu(
                *[pystray.MenuItem(app, lambda icon, item, a=app: print(merge_app(a))) for app in APPS]
            )),
            pystray.MenuItem("Sync models to providers", on_sync_models),
            pystray.MenuItem("Open DEVELOPER", on_open_developer),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", on_quit)
        )
        icon = pystray.Icon("nexaura-fuse", image, "NEXAURA FUSE", menu)
        # Watchdog in thread
        def watch():
            try:
                from watchdog.observers import Observer
                from watchdog.events import FileSystemEventHandler
                class H(FileSystemEventHandler):
                    def on_created(self, e):
                        if e.src_path.endswith(".gguf"):
                            time.sleep(1)
                            sync_models_to_providers()
                obs = Observer()
                if SHARED_MODELS.exists():
                    obs.schedule(H(), str(SHARED_MODELS), recursive=True)
                    obs.start()
                    obs.join()
            except: pass
        threading.Thread(target=watch, daemon=True).start()
        icon.run()
    except Exception as e:
        print(f"Tray failed {e}, running headless. Use --merge <app>")
        # Fallback CLI
        if len(sys.argv) > 1:
            print(merge_app(sys.argv[1]))
        else:
            for a in APPS:
                print(a, get_status())

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in APPS:
        print(merge_app(sys.argv[1]))
        print(sync_models_to_providers())
    elif len(sys.argv) > 1 and sys.argv[1] == "--sync-models":
        print(sync_models_to_providers())
    else:
        run_tray()
