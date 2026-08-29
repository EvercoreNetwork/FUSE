#!/usr/bin/env python3
"""
NEXAURA FUSE - Merge Windows and Linux workspaces
Tray daemon that keeps NEXAURA DEVELOPER in sync across OSes.
Cross-platform: Linux (AyatanaAppIndicator3/Gtk), Windows (pystray native), macOS.
"""
import os, sys, json, pathlib, shutil, subprocess, threading, time, fcntl, atexit
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
# --- Settings (persistent) ---
SETTINGS_DIR = HOME / ".config" / "nexaura-fuse"
SETTINGS_PATH = SETTINGS_DIR / "settings.json"
DEFAULT_SETTINGS = {
    "developer_path": str(DEVELOPER),
    "run_on_startup": True,
    "start_minimized": False,
    "tray_custom_popup": True,  # Linux X11 custom tray vs native menu
}

def load_settings():
    try:
        if SETTINGS_PATH.exists():
            import json as _js
            data = _js.loads(SETTINGS_PATH.read_text())
            # merge defaults
            for k,v in DEFAULT_SETTINGS.items():
                if k not in data:
                    data[k] = v
            return data
    except: pass
    return dict(DEFAULT_SETTINGS)

def save_settings(data):
    try:
        SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
        import json as _js, tempfile, os as _os
        tmp = SETTINGS_PATH.with_suffix(".tmp")
        tmp.write_text(_js.dumps(data, indent=2))
        tmp.replace(SETTINGS_PATH)
        return True
    except Exception as e:
        try: print(f"save_settings err {e}")
        except: pass
        return False

def get_executable_path():
    """Return executable for autostart: frozen bundle or dist/FUSE or python fallback"""
    try:
        if getattr(sys, 'frozen', False):
            return Path(sys.executable).resolve()
    except: pass
    # Check dist/FUSE next to this file or DEVELOPER/FUSE/dist/FUSE
    candidates = [
        Path(__file__).parent / "dist" / "FUSE",
        Path(__file__).parent / "dist" / "FUSE.exe",
        Path("/mnt/NEXAURA/DEVELOPER/FUSE/dist/FUSE"),
        Path("/mnt/NEXAURA/DEVELOPER/FUSE/dist/FUSE.exe"),
        Path.home() / ".local/bin/FUSE",
        Path("/usr/local/bin/FUSE"),
    ]
    for c in candidates:
        try:
            if c.exists() and c.stat().st_size > 1024*1024:
                return c.resolve()
        except: pass
    # fallback to python
    return None

def get_autostart_exec():
    exe = get_executable_path()
    if exe:
        # Use executable directly; for Linux need no args, for frozen we are good
        return str(exe)
    # fallback python
    try:
        fuse_py = Path(__file__).resolve()
        return f"python3 {fuse_py}"
    except:
        return "python3 /mnt/NEXAURA/DEVELOPER/FUSE/fuse.py"

def is_autostart_enabled():
    plat = sys.platform
    try:
        if plat.startswith("linux"):
            p = HOME / ".config/autostart/nexaura-fuse.desktop"
            return p.exists()
        elif plat == "win32":
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_READ)
            try:
                v,_ = winreg.QueryValueEx(key, "NEXAURA_FUSE")
                return bool(v)
            except: return False
        elif plat == "darwin":
            p = HOME / "Library/LaunchAgents/network.evercore.fuse.plist"
            return p.exists()
    except: return False
    return False

def set_autostart(enabled: bool):
    plat = sys.platform
    exe = get_autostart_exec()
    try:
        if plat.startswith("linux"):
            p = HOME / ".config/autostart/nexaura-fuse.desktop"
            if enabled:
                p.parent.mkdir(parents=True, exist_ok=True)
                # Prefer exe if available, else python
                icon = DEVELOPER / "FUSE/assets/logo-256.png"
                if not icon.exists():
                    icon = Path(__file__).parent / "assets/logo-256.png"
                content = f"""[Desktop Entry]
Name=NEXAURA FUSE
Comment=Merge Windows and Linux workspaces - tray daemon
Exec={exe}
Icon={icon}
Terminal=false
Type=Application
Categories=Development;Utility;
StartupWMClass=FUSE
X-GNOME-Autostart-enabled=true
X-GNOME-Autostart-Delay=3
Hidden=false
"""
                p.write_text(content)
            else:
                try: p.unlink()
                except: pass
            return True
        elif plat == "win32":
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_WRITE)
            if enabled:
                winreg.SetValueEx(key, "NEXAURA_FUSE", 0, winreg.REG_SZ, f'"{exe}"')
            else:
                try: winreg.DeleteValue(key, "NEXAURA_FUSE")
                except: pass
            winreg.CloseKey(key)
            return True
        elif plat == "darwin":
            p = HOME / "Library/LaunchAgents/network.evercore.fuse.plist"
            if enabled:
                p.parent.mkdir(parents=True, exist_ok=True)
                plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>network.evercore.fuse</string>
<key>ProgramArguments</key><array><string>{exe}</string></array>
<key>RunAtLoad</key><true/>
<key>KeepAlive</key><false/>
</dict></plist>"""
                p.write_text(plist)
            else:
                try: p.unlink()
                except: pass
            return True
    except Exception as e:
        print(f"set_autostart err {e}")
        import traceback; traceback.print_exc()
        return False
    return False

# Load settings early and override DEVELOPER if custom
_SETTINGS = load_settings()
try:
    _custom_dev = Path(_SETTINGS.get("developer_path", str(DEVELOPER))).expanduser()
    if _custom_dev and str(_custom_dev) != str(DEVELOPER):
        # Only override if path exists or parent exists (allow fresh)
        if _custom_dev.exists() or _custom_dev.parent.exists():
            DEVELOPER = _custom_dev
except: pass
SHARED_MODELS = DEVELOPER / "SHARED" / "MODELS"
GLOBAL_MODELS = DEVELOPER / "Models" / "Global"
OLLAMA_MODELS = DEVELOPER / "Models" / "Ollama"
# Sync autostart to use executable (not python) if setting says enabled
try:
    if _SETTINGS.get("run_on_startup", True):
        # Ensure autostart points to executable
        cur_enabled = is_autostart_enabled()
        # If enabled but points to python while exe exists, update
        exe = get_executable_path()
        if cur_enabled and exe:
            # Check current desktop file Exec
            p = HOME / ".config/autostart/nexaura-fuse.desktop"
            if p.exists():
                content = p.read_text()
                if str(exe) not in content and "python3" in content:
                    set_autostart(True)
        elif not cur_enabled and _SETTINGS.get("run_on_startup"):
            set_autostart(True)
except: pass

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

APP_LAUNCH = {
    "claude": ["claude", "Claude", "code"],
    "opencode": ["opencode", "/opt/OpenCode/opencode", "code"],
    "opencode-share": ["opencode"],
    "opencode-cache": ["opencode"],
    "opencode-desktop": ["opencode"],
    "zcode": ["zcode"],
    "zcode-share": ["zcode"],
    "jetbrains-config": ["jetbrains-toolbox", "idea", "pycharm"],
    "jetbrains-share": ["jetbrains-toolbox"],
    "jetbrains-cache": ["jetbrains-toolbox"],
    "lmstudio": ["lmstudio", "flatpak run ai.lmstudio.lm-studio"],
    "codex": ["codex"],
    "gemini": ["gemini"],
    "projects": ["xdg-open", str(HOME / "Documents")],
}

def refresh_developer_paths(new_dev: Path):
    """Update globals when DEVELOPER changes (called after settings save)"""
    global DEVELOPER, SHARED_MODELS, GLOBAL_MODELS, OLLAMA_MODELS, APPS
    try:
        DEVELOPER = Path(new_dev).expanduser().resolve()
        SHARED_MODELS = DEVELOPER / "SHARED" / "MODELS"
        GLOBAL_MODELS = DEVELOPER / "Models" / "Global"
        OLLAMA_MODELS = DEVELOPER / "Models" / "Ollama"
        # Update APPS dsts to new DEVELOPER
        for k, cfg in APPS.items():
            # dst is DEVELOPER / <relative>
            try:
                # keep relative part after original DEVELOPER
                rel = Path(cfg["dst"]).name if Path(cfg["dst"]).parent == DEVELOPER else Path(cfg["dst"]).relative_to(DEVELOPER) if False else None
            except: pass
        # Rebuild APPS with new DEVELOPER
        APPS.update({
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
        })
        return True
    except Exception as e:
        print(f"refresh_developer_paths err {e}")
        return False

def show_settings_dialog(parent=None):
    """GTK settings dialog: DEVELOPER folder, run on startup, etc."""
    import gi
    try:
        gi.require_version('Gtk', '3.0')
        from gi.repository import Gtk
    except Exception as e:
        print(f"Gtk not available for settings {e}")
        return
    settings = load_settings()
    # Build dialog
    dlg = Gtk.Dialog(title="FUSE Settings", transient_for=parent, flags=0)
    dlg.set_default_size(520, 340)
    dlg.set_border_width(10)
    dlg.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OK, Gtk.ResponseType.OK)
    dlg.set_position(Gtk.WindowPosition.CENTER)
    try:
        dlg.set_icon_from_file(str(Path(__file__).parent / "assets/logo-256.png"))
    except: pass
    content = dlg.get_content_area()
    content.set_spacing(12)
    # Title
    lbl = Gtk.Label()
    lbl.set_markup('<b>NEXAURA FUSE — Settings</b>')
    lbl.set_halign(Gtk.Align.START)
    content.pack_start(lbl, False, False, 4)
    # DEVELOPER folder row
    hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    l = Gtk.Label(label="DEVELOPER folder:")
    l.set_halign(Gtk.Align.START)
    l.set_size_request(140, -1)
    hbox.pack_start(l, False, False, 0)
    entry = Gtk.Entry()
    entry.set_text(settings.get("developer_path", str(DEVELOPER)))
    entry.set_hexpand(True)
    entry.set_tooltip_text("Target folder for merged workspaces (e.g. /mnt/NEXAURA/DEVELOPER)")
    hbox.pack_start(entry, True, True, 0)
    btn_browse = Gtk.Button(label="Browse…")
    hbox.pack_start(btn_browse, False, False, 0)
    content.pack_start(hbox, False, False, 4)
    # Autostart switch
    hbox2 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    l2 = Gtk.Label(label="Run on startup:")
    l2.set_halign(Gtk.Align.START)
    l2.set_size_request(140, -1)
    hbox2.pack_start(l2, False, False, 0)
    sw_autostart = Gtk.Switch()
    sw_autostart.set_active(settings.get("run_on_startup", is_autostart_enabled()))
    sw_autostart.set_halign(Gtk.Align.START)
    hbox2.pack_start(sw_autostart, False, False, 0)
    # Show exe path hint
    exe_hint = Gtk.Label()
    exe_hint.set_markup(f'<span size="small" color="#888">Exec: {get_autostart_exec()}</span>')
    exe_hint.set_halign(Gtk.Align.START)
    exe_hint.set_line_wrap(True)
    exe_hint.set_max_width_chars(60)
    vbox2 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
    vbox2.pack_start(hbox2, False, False, 0)
    vbox2.pack_start(exe_hint, False, False, 0)
    content.pack_start(vbox2, False, False, 4)
    # Start minimized
    hbox3 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    l3 = Gtk.Label(label="Start minimized:")
    l3.set_halign(Gtk.Align.START)
    l3.set_size_request(140, -1)
    hbox3.pack_start(l3, False, False, 0)
    sw_min = Gtk.Switch()
    sw_min.set_active(settings.get("start_minimized", False))
    hbox3.pack_start(sw_min, False, False, 0)
    content.pack_start(hbox3, False, False, 4)
    # Info
    info = Gtk.Label()
    info.set_markup('<span size="small" color="#888">Changes to DEVELOPER require restart. Autostart uses the executable (dist/FUSE) when available, else python.</span>')
    info.set_line_wrap(True)
    info.set_max_width_chars(60)
    info.set_halign(Gtk.Align.START)
    content.pack_start(info, False, False, 6)
    # Browse handler
    def on_browse(btn):
        chooser = Gtk.FileChooserDialog(title="Pick DEVELOPER folder", parent=dlg, action=Gtk.FileChooserAction.SELECT_FOLDER)
        chooser.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, "Select", Gtk.ResponseType.OK)
        chooser.set_current_folder(entry.get_text() or str(HOME))
        if chooser.run() == Gtk.ResponseType.OK:
            entry.set_text(chooser.get_filename())
        chooser.destroy()
    btn_browse.connect("clicked", on_browse)
    dlg.show_all()
    resp = dlg.run()
    if resp == Gtk.ResponseType.OK:
        new_dev = entry.get_text().strip()
        new_autostart = sw_autostart.get_active()
        new_min = sw_min.get_active()
        # Save
        settings["developer_path"] = new_dev
        settings["run_on_startup"] = new_autostart
        settings["start_minimized"] = new_min
        save_settings(settings)
        # Update autostart file to use executable
        set_autostart(new_autostart)
        # Try to refresh paths (will be reloaded on next restart)
        try:
            refresh_developer_paths(Path(new_dev))
        except: pass
        # Inform
        msg = Gtk.MessageDialog(transient_for=dlg, flags=0, message_type=Gtk.MessageType.INFO, buttons=Gtk.ButtonsType.OK, text="Settings saved — restart FUSE to apply DEVELOPER change." if new_dev != str(DEVELOPER) else "Settings saved.")
        msg.run()
        msg.destroy()
    dlg.destroy()
    return

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
    # Log startup to file so reboot failures are visible
    import traceback as _tb
    log_path = Path("/tmp/nexaura-fuse.log")
    def _log(msg):
        line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n"
        try:
            with log_path.open("a") as f:
                f.write(line); f.flush()
        except: pass
        try:
            print(line, end="", flush=True)
            sys.stderr.write(line); sys.stderr.flush()
        except: pass
    _log(f"FUSE starting pid={os.getpid()} DEVELOPER={DEVELOPER} exists={DEVELOPER.exists()}")
    # Proper Linux tray: no GNOME Shell JS patching (anti-pattern)
    # SNI spec: Activate=left, ContextMenu=right, SecondaryActivate=middle
    # GNOME AppIndicator host shows menu on both left+right by design (ubuntu/appindicator#313)
    # pystray: appindicator HAS_DEFAULT_ACTION=False, gtk has activate/popup-menu (pystray#47)
    # Correct: X11+legacy tray -> Gtk.StatusIcon for custom popup left/right; else AppIndicator native menu
    try:
        import pystray
        from PIL import Image
        # Let pystray handle AppIndicator vs Ayatana itself (pystray/_appindicator.py does AppIndicator3 -> Ayatana fallback)
        # Just verify GI is importable for debugging
        try:
            import gi
            gi.require_version('Gtk', '3.0')
            from gi.repository import Gtk
            _log("Gtk 3.0 OK")
        except Exception as e:
            _log(f"Gtk import warn: {e}")
            _tb.print_exc()

        # Icon - handle PyInstaller _MEIPASS
        icon_path = DEVELOPER / "FUSE/assets/logo-256.png"
        if not icon_path.exists():
            base = Path(getattr(sys, '_MEIPASS', Path(__file__).parent))
            for cand in [base / "assets/logo-256.png", base / "logo-256.png", Path(__file__).parent / "assets/logo-256.png"]:
                if cand.exists():
                    icon_path = cand; break
        _log(f"icon_path={icon_path} exists={icon_path.exists()}")
        try:
            image = Image.open(icon_path) if icon_path.exists() else Image.new('RGBA', (64,64), (10,10,12,255))
            _log(f"icon loaded {image.size} mode={image.mode}")
        except Exception as e:
            _log(f"icon load failed {e!r}")
            image = Image.new('RGBA', (64,64), (10,10,12,255))

        def on_merge_all(icon, item):
            for app in APPS:
                print(merge_app(app))

        def _make_merge_cb(a):
            def cb(icon, item):
                print(merge_app(a))
            return cb

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

        # --- Custom tray UI: stars at far left/right with centered text via HTML popup ---
        # Native pystray menu can't center with stars at edges (variable font + GTK trims spaces).
        # So we show a custom Gtk/WebKit popup at bottom-right on click, with flex justify-content:space-between.
        custom_tray_win = {"win": None}

        def _show_dashboard():
            try:
                gwin = globals().get("_DARK_WIN")
                if gwin:
                    from gi.repository import GLib
                    GLib.idle_add(lambda: (gwin.show_all(), gwin.present(), gwin.deiconify(), False)[3])
                    GLib.idle_add(lambda: gwin.present_with_time(0))
                    return
            except: pass
            try:
                subprocess.Popen(["wmctrl","-a","NEXAURA FUSE"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                subprocess.Popen(["xdotool","search","--name","NEXAURA FUSE","windowactivate"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except: pass
            try:
                if not Path("/tmp/nexaura-fuse.lock").exists():
                    subprocess.Popen([sys.executable, str(Path(__file__).parent / "fuse.py"), "--dark"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except: pass

        def _get_pointer_pos():
            try:
                from gi.repository import Gdk
                disp = Gdk.Display.get_default()
                seat = disp.get_default_seat()
                dev = seat.get_pointer()
                scr, x, y = dev.get_position()
                return x, y
            except:
                try:
                    from gi.repository import Gdk
                    scr = Gdk.Screen.get_default()
                    return scr.get_width() - 100, scr.get_height() - 100
                except:
                    return 960, 540

        # Animation state for tray popup (fade+slide) - no delay, 180ms
        _tray_anim = {"active": False}
        def _tray_animate_show(win, tx, ty, duration=190):
            try:
                if _tray_anim["active"]:
                    return
                _tray_anim["active"] = True
                win.set_opacity(0)
                try:
                    win.move(int(tx), int(ty + 10))
                except: pass
                win.show_all()
                win.present()
                try:
                    win.set_keep_above(True)
                    # grab so clicking outside closes (focus-out + button outside)
                    win.set_can_focus(True)
                    win.grab_focus()
                    import gi as _gi_grab
                    from gi.repository import Gtk as _Gtk_grab
                    try: _Gtk_grab.grab_add(win)
                    except: pass
                except: pass
                _start = __import__("time").time()
                def _tick():
                    elapsed = (__import__("time").time() - _start) * 1000
                    p = min(1.0, elapsed / duration)
                    e = 1 - pow(1 - p, 3)  # easeOutCubic
                    try:
                        win.set_opacity(e)
                        win.move(int(tx), int(ty + 10 * (1 - e)))
                    except: pass
                    if p < 1:
                        return True
                    try:
                        win.set_opacity(1)
                        win.move(int(tx), int(ty))
                    except: pass
                    _tray_anim["active"] = False
                    return False
                from gi.repository import GLib as _GLib_anim
                _GLib_anim.timeout_add(10, _tick)
            except Exception as e:
                try: _log(f"tray animate show err {e}")
                except: pass
                try:
                    win.set_opacity(1)
                    win.show_all()
                    win.present()
                except: pass
                _tray_anim["active"] = False

        def _tray_animate_hide(win, duration=150):
            try:
                # remove grab first so outside clicks stop being captured
                try:
                    from gi.repository import Gtk as _Gtk_grab2
                    _Gtk_grab2.grab_remove(win)
                except: pass
                if not win.get_visible() or _tray_anim["active"]:
                    try: win.hide()
                    except: pass
                    _tray_anim["active"] = False
                    return
                _tray_anim["active"] = True
                try:
                    sx, sy = win.get_position()
                except:
                    sx, sy = 0, 0
                start = __import__("time").time()
                start_op = 1.0
                try: start_op = win.get_opacity()
                except: pass
                def _tick():
                    elapsed = (__import__("time").time() - start) * 1000
                    p = min(1.0, elapsed / duration)
                    e = 1 - p
                    try:
                        win.set_opacity(start_op * e)
                        win.move(int(sx), int(sy + 10 * p))
                    except: pass
                    if p < 1:
                        return True
                    try:
                        win.hide()
                        win.set_opacity(1)
                        win.move(int(sx), int(sy))
                    except: pass
                    _tray_anim["active"] = False
                    return False
                from gi.repository import GLib as _GLib_h
                _GLib_h.timeout_add(10, _tick)
            except Exception as e:
                try: _log(f"tray animate hide err {e}")
                except: pass
                try: win.hide()
                except: pass
                _tray_anim["active"] = False

        def _show_custom_tray(*_):
            try:
                _log(f"_show_custom_tray called args={_}")
            except: pass
            try:
                from gi.repository import Gtk, Gdk, WebKit2, GLib
                import cairo
                win = custom_tray_win["win"]
                if win and win.get_visible():
                    try: _log("tray hide (was visible)")
                    except: pass
                    _tray_animate_hide(win)
                    return
                if win:
                    # reposition near tray icon (pointer) - bottom taskbar is at sh-48
                    try:
                        x, y = _get_pointer_pos()
                        scr = Gdk.Screen.get_default()
                        sw, sh = scr.get_width(), scr.get_height()
                        tx = max(8, min(x - 160, sw - 320 - 8))
                        ty = sh - 210 - 48 - 8
                        _tray_animate_show(win, tx, ty)
                    except:
                        try:
                            _tray_animate_show(win, 100, 100)
                        except: pass
                    return
                # --- Transparent popup: POPUP + RGBA visual (canonical, fixes white rectangle) ---
                # POPUP windows on GNOME Mutter/X11 need RGBA visual + SOURCE clear
                # if the visual is not RGBA or if the draw handler uses wrong operator.
                # Use POPUP + POPUP_MENU hint + app_paintable + SOURCE clear (canonical).
                win = Gtk.Window(type=Gtk.WindowType.POPUP)
                custom_tray_win["win"] = win
                win.set_title("FUSE Tray")
                win.set_decorated(False)
                win.set_skip_taskbar_hint(True)
                win.set_skip_pager_hint(True)
                win.set_keep_above(True)
                win.set_type_hint(Gdk.WindowTypeHint.POPUP_MENU)
                win.set_resizable(False)
                win.set_default_size(320, 220)
                win.set_app_paintable(True)
                # Must set RGBA visual BEFORE realize/show for compositor transparency
                try:
                    scr = win.get_screen()
                    vis = scr.get_rgba_visual()
                    if vis and scr.is_composited():
                        win.set_visual(vis)
                    # Clean transparent draw: clear to transparent with SOURCE, then restore OVER
                    def _on_draw(w, cr):
                        cr.set_source_rgba(0, 0, 0, 0)
                        cr.set_operator(cairo.Operator.SOURCE)
                        cr.paint()
                        cr.set_operator(cairo.Operator.OVER)
                        return False
                    win.connect("draw", _on_draw)
                    # Make every layer transparent; .tray card itself is opaque (#1a1a1a)
                    css = b"""
                        window, decoration, .background {
                            background-color: transparent;
                            background: transparent;
                            border: none;
                            box-shadow: none;
                        }
                        GtkWindow { background: transparent; }
                    """
                    prov = Gtk.CssProvider()
                    prov.load_from_data(css)
                    Gtk.StyleContext.add_provider_for_screen(scr, prov, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
                except: pass
                try:
                    x, y = _get_pointer_pos()
                    scr = Gdk.Screen.get_default()
                    sw, sh = scr.get_width(), scr.get_height()
                    tx = max(8, min(x - 160, sw - 320 - 8))
                    ty = sh - 220 - 48 - 8
                    win.move(int(tx), int(ty))
                except:
                    try:
                        scr = Gdk.Screen.get_default()
                        win.move(scr.get_width() - 320 - 12, scr.get_height() - 180 - 58)
                    except:
                        win.set_position(Gtk.WindowPosition.MOUSE)
                mgr = WebKit2.UserContentManager()
                mgr.register_script_message_handler("fuse")
                def _on_msg(m, msg):
                    try:
                        try: js = msg.get_js_value()
                        except: js = msg.get_jsc_value()
                        raw = js.to_string()
                        import json as _j
                        d = _j.loads(raw)
                        act = d.get("action") if isinstance(d,dict) else str(d)
                    except:
                        act = ""
                    if act == "dashboard":
                        _show_dashboard()
                        GLib.idle_add(lambda: _tray_animate_hide(win))
                    elif act == "merge":
                        for a in APPS: print(merge_app(a))
                        GLib.idle_add(lambda: _tray_animate_hide(win))
                    elif act == "settings":
                        try:
                            _show_dashboard()
                            # After dashboard shows, switch to settings view via JS, plus offer native dialog
                            def _open_settings_view():
                                try:
                                    wv = globals().get("_DARK_WEBVIEW")
                                    if wv:
                                        try:
                                            wv.run_javascript("try{setView('settings'); loadSettings();}catch(e){}", None, None, None)
                                        except:
                                            try: wv.evaluate_javascript("setView('settings')", -1, None, None, None, None)
                                            except: pass
                                except: pass
                                # also offer native dialog as alternative (non-blocking)
                                # show_settings_dialog()  # optional, keep dashboard view as primary
                                return False
                            GLib.timeout_add(700, _open_settings_view)
                        except:
                            try: show_settings_dialog()
                            except: pass
                        GLib.idle_add(lambda: _tray_animate_hide(win))
                    elif act == "quit":
                        try: _tray_animate_hide(win)
                        except:
                            try: win.hide()
                            except: pass
                        try: icon.stop()
                        except: pass
                        import time as _t; _t.sleep(0.2)
                        os._exit(0)
                mgr.connect("script-message-received::fuse", _on_msg)
                settings = WebKit2.Settings()
                try:
                    settings.set_enable_javascript(True)
                    settings.set_allow_file_access_from_file_urls(True)
                    settings.set_allow_universal_access_from_file_urls(True)
                except: pass
                view = WebKit2.WebView.new_with_user_content_manager(mgr)
                view.set_settings(settings)
                # Critical for no white rectangle: WebKit view itself must be transparent.
                try:
                    # GTK3 requires set_background_color with alpha 0
                    rgba = Gdk.RGBA()
                    rgba.parse("rgba(0,0,0,0)")
                    view.set_background_color(rgba)
                    # Also make the view widget transparent via CSS
                    view.set_app_paintable(True)
                except: pass
                html_path = DEVELOPER / "FUSE/frontend/tray.html"
                if not html_path.exists():
                    html_path = Path(__file__).parent / "frontend/tray.html"
                view.load_uri(html_path.as_uri())
                # Wrap in EventBox with transparent bg to avoid GtkBin white
                try:
                    box = Gtk.EventBox()
                    box.set_visible_window(False)
                    # Ensure box doesn't draw background
                    box.set_app_paintable(True)
                    box.connect("draw", lambda w, cr: False)
                    box.add(view)
                    win.add(box)
                except:
                    win.add(view)
                win.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.FOCUS_CHANGE_MASK)
                win.set_can_focus(True)
                win.connect("focus-out-event", lambda w,e: (_tray_animate_hide(w), False)[1] or True)
                win.connect("key-press-event", lambda w,e: (_tray_animate_hide(w), False)[1] if e.keyval==65307 else None)
                # clicking outside (with grab, all presses go to win) -> if coords outside allocation, hide
                def _on_btn_press(w, ev):
                    try:
                        # ev.x, ev.y relative to win; outside means <0 or > alloc
                        aw, ah = w.get_allocated_width(), w.get_allocated_height()
                        if ev.x < 0 or ev.y < 0 or ev.x > aw or ev.y > ah:
                            _tray_animate_hide(w)
                            return True
                    except: pass
                    return False
                win.connect("button-press-event", _on_btn_press)
                # also handle grab broken (e.g., other grab)
                try:
                    win.connect("grab-broken-event", lambda w,e: (_tray_animate_hide(w), False)[1])
                except: pass
                # Realize with RGBA before show
                # Animate in near tray icon (no delay)
                try:
                    scr2 = Gdk.Screen.get_default()
                    sw2, sh2 = scr2.get_width(), scr2.get_height()
                    try:
                        x2, y2 = _get_pointer_pos()
                        tx2 = max(8, min(x2 - 160, sw2 - 320 - 8))
                        ty2 = sh2 - 180 - 48 - 8
                    except:
                        tx2, ty2 = sw2 - 320 - 12, sh2 - 180 - 58
                    # prepare for animate: opacity 0 offset
                    try:
                        win.set_opacity(0)
                        win.move(int(tx2), int(ty2 + 10))
                    except: pass
                    win.show_all()
                    win.present()
                    _tray_animate_show(win, tx2, ty2)
                except:
                    try:
                        win.show_all()
                        win.set_opacity(1.0)
                    except: pass
            except Exception as e:
                print(f"custom tray err {e}")
                import traceback; traceback.print_exc()

        # Pre-create tray window to avoid first-click 1s delay (WebKit init)
        # Do it idle shortly after startup so first click animates instantly
        def _preload_tray_win():
            try:
                # trigger creation without showing animation: create win, load uri, then hide
                # Use the same creation path but keep hidden
                from gi.repository import Gtk, Gdk, WebKit2, GLib
                import cairo
                if custom_tray_win["win"] is not None:
                    return False
                # Create window (duplicate minimal creation to preload)
                win = Gtk.Window(type=Gtk.WindowType.POPUP)
                custom_tray_win["win"] = win
                win.set_title("FUSE Tray")
                win.set_decorated(False)
                win.set_skip_taskbar_hint(True)
                win.set_skip_pager_hint(True)
                win.set_keep_above(True)
                win.set_type_hint(Gdk.WindowTypeHint.POPUP_MENU)
                win.set_resizable(False)
                win.set_default_size(320, 220)
                win.set_app_paintable(True)
                try:
                    scr = win.get_screen()
                    vis = scr.get_rgba_visual()
                    if vis and scr.is_composited():
                        win.set_visual(vis)
                    def _on_draw(w, cr):
                        cr.set_source_rgba(0, 0, 0, 0)
                        cr.set_operator(cairo.Operator.SOURCE)
                        cr.paint()
                        cr.set_operator(cairo.Operator.OVER)
                        return False
                    win.connect("draw", _on_draw)
                    css = b"window, decoration, .background { background-color: transparent; background: transparent; border: none; box-shadow: none; } GtkWindow { background: transparent; }"
                    prov = Gtk.CssProvider()
                    prov.load_from_data(css)
                    Gtk.StyleContext.add_provider_for_screen(scr, prov, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
                except: pass
                # offscreen position for preload
                try:
                    win.move(-1000, -1000)
                    win.set_opacity(0)
                except: pass
                mgr = WebKit2.UserContentManager()
                mgr.register_script_message_handler("fuse")
                def _on_msg(m, msg):
                    try:
                        try: js = msg.get_js_value()
                        except: js = msg.get_jsc_value()
                        raw = js.to_string()
                        import json as _j
                        d = _j.loads(raw)
                        act = d.get("action") if isinstance(d,dict) else str(d)
                    except: act = ""
                    if act == "dashboard":
                        _show_dashboard()
                        GLib.idle_add(lambda: _tray_animate_hide(win))
                    elif act == "merge":
                        for a in APPS: print(merge_app(a))
                    elif act == "quit":
                        try: win.hide()
                        except: pass
                        try: icon.stop()
                        except: pass
                        import os as _os; _os._exit(0)
                mgr.connect("script-message-received::fuse", _on_msg)
                settings = WebKit2.Settings()
                try:
                    settings.set_enable_javascript(True)
                    settings.set_allow_file_access_from_file_urls(True)
                    settings.set_allow_universal_access_from_file_urls(True)
                except: pass
                view = WebKit2.WebView.new_with_user_content_manager(mgr)
                view.set_settings(settings)
                try:
                    rgba = Gdk.RGBA()
                    rgba.parse("rgba(0,0,0,0)")
                    view.set_background_color(rgba)
                    view.set_app_paintable(True)
                except: pass
                html_path = DEVELOPER / "FUSE/frontend/tray.html"
                if not html_path.exists():
                    html_path = Path(__file__).parent / "frontend/tray.html"
                view.load_uri(html_path.as_uri())
                try:
                    box = Gtk.EventBox()
                    box.set_visible_window(False)
                    box.set_app_paintable(True)
                    box.connect("draw", lambda w, cr: False)
                    box.add(view)
                    win.add(box)
                except:
                    win.add(view)
                win.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.FOCUS_CHANGE_MASK)
                win.set_can_focus(True)
                win.connect("focus-out-event", lambda w,e: (_tray_animate_hide(w), False)[1] or True)
                win.connect("key-press-event", lambda w,e: (_tray_animate_hide(w), False)[1] if e.keyval==65307 else None)
                def _on_btn_press(w, ev):
                    try:
                        aw, ah = w.get_allocated_width(), w.get_allocated_height()
                        if ev.x < 0 or ev.y < 0 or ev.x > aw or ev.y > ah:
                            _tray_animate_hide(w)
                            return True
                    except: pass
                    return False
                win.connect("button-press-event", _on_btn_press)
                try: win.connect("grab-broken-event", lambda w,e: (_tray_animate_hide(w), False)[1])
                except: pass
                # show briefly offscreen to realize, then hide
                win.show_all()
                win.hide()
                win.set_opacity(1)
                _log("tray preload done (first click will animate)")
            except Exception as e:
                try: _log(f"preload err {e}")
                except: pass
                import traceback; traceback.print_exc()
            return False
        try:
            from gi.repository import GLib as _GLib_pre
            _GLib_pre.timeout_add(350, _preload_tray_win)
        except: pass

        # DBUS service so shell taskbar clicks (AppIcons) and AppIndicator can trigger tray via Gio.DBus
        # Exposes org.nexaura.FUSE at /org/nexaura/FUSE with ShowTray/ToggleTray/HideTray
        try:
            from gi.repository import Gio as _Gio2, GLib as _GLib2b
            _dbus_xml = """
            <node>
              <interface name="org.nexaura.FUSE">
                <method name="ShowTray"/>
                <method name="ToggleTray"/>
                <method name="HideTray"/>
              </interface>
            </node>"""
            _dbus_node2 = _Gio2.DBusNodeInfo.new_for_xml(_dbus_xml)
            _dbus_iface2 = _dbus_node2.lookup_interface("org.nexaura.FUSE")
            def _dbus_call(conn, sender, obj_path, iface_name, method_name, params, invocation):
                try: _log(f"DBUS {method_name} from {sender}")
                except: pass
                try:
                    if method_name in ("ShowTray", "ToggleTray"):
                        _GLib2b.idle_add(lambda: (_show_custom_tray(), False)[1])
                        invocation.return_value(None)
                    elif method_name == "HideTray":
                        try:
                            w2 = custom_tray_win.get("win")
                            if w2: _GLib2b.idle_add(lambda: (w2.hide(), False)[1])
                        except: pass
                        invocation.return_value(None)
                    else:
                        invocation.return_error_literal(_Gio2.DBusError, _Gio2.DBusError.UNKNOWN_METHOD, "Unknown")
                except Exception as e:
                    try: invocation.return_error_literal(_Gio2.DBusError, _Gio2.DBusError.FAILED, str(e))
                    except: pass
            def _on_bus_acquired(conn, name):
                try:
                    conn.register_object("/org/nexaura/FUSE", _dbus_iface2, _dbus_call, None, None)
                    _log("DBUS org.nexaura.FUSE ShowTray ready")
                except Exception as e:
                    _log(f"DBUS register err {e}")
            _Gio2.bus_own_name(_Gio2.BusType.SESSION, "org.nexaura.FUSE", _Gio2.BusNameOwnerFlags.NONE, _on_bus_acquired, lambda c,n: _log(f"DBUS acquired {n}"), lambda c,n: _log(f"DBUS lost {n}"))
        except Exception as e:
            try: _log(f"DBUS setup err {e}")
            except: pass

        def on_dashboard(icon, item):
            _show_custom_tray()

        def on_quit(icon, item):
            try: icon.stop()
            except: pass
            os._exit(0)

        s = get_status()
        # --- Proper Linux tray per SNI/pystray docs ---
        # - pystray AppIndicator: HAS_DEFAULT_ACTION=False, menu shown on both left+right by GNOME host (ubuntu/appindicator#313)
        # - pystray Gtk: activate=left, popup-menu=right (pystray/_gtk.py:30, pystray#47)
        # - OSS pattern (Nextcloud/Discord/Electron): X11+legacy tray -> Gtk StatusIcon for custom popup; else AppIndicator native menu
        # Inspiration: Ayatana simple-client.c app_indicator_set_menu + secondary target=middle only; SNI Activate/ContextMenu
        use_gtk_for_custom = False
        is_linux = sys.platform.startswith("linux")
        if is_linux and not os.environ.get("PYSTRAY_BACKEND"):
            try:
                # Prefer Gtk on X11 where legacy tray manager can show XEmbed icon (Zorin bottom bar)
                # Check X11 and composited screen + legacy-tray-enabled (proper per GNOME fallback docs)
                if os.environ.get("XDG_SESSION_TYPE", "x11") == "x11":
                    import gi as _gi2
                    _gi2.require_version('Gtk', '3.0')
                    from gi.repository import Gdk as _Gdk2
                    _screen = None
                    try:
                        _screen = _Gdk2.Screen.get_default()
                    except:
                        _screen = None
                    _composited = False
                    try:
                        _composited = _screen.is_composited() if _screen else False
                    except:
                        _composited = True  # assume composited on X11
                    _legacy_ok = True
                    try:
                        import subprocess as _sp2
                        _out = _sp2.check_output(["gsettings", "get", "org.gnome.shell.extensions.zorin-appindicator", "legacy-tray-enabled"], text=True, timeout=2).strip()
                        _legacy_ok = "true" in _out.lower()
                    except:
                        _legacy_ok = True
                    if _composited and _legacy_ok:
                        use_gtk_for_custom = True
            except Exception as _e:
                _log(f"Gtk custom check err {_e}")
                use_gtk_for_custom = False
        if use_gtk_for_custom:
            try:
                import pystray._gtk as _gtk_mod
                from gi.repository import GLib as _GLib_gtk
                def _fuse_gtk_activate(self, status_icon):
                    try: _log("Gtk activate (left) -> custom tray")
                    except: pass
                    try: _GLib_gtk.idle_add(lambda: (_show_custom_tray(), False)[1])
                    except: _show_custom_tray()
                def _fuse_gtk_popup(self, status_icon, button, activate_time):
                    try: _log(f"Gtk popup-menu (right) button={button} -> custom tray")
                    except: pass
                    try: _GLib_gtk.idle_add(lambda: (_show_custom_tray(), False)[1])
                    except: _show_custom_tray()
                _gtk_mod.Icon._on_status_icon_activate = _fuse_gtk_activate
                _gtk_mod.Icon._on_status_icon_popup_menu = _fuse_gtk_popup
                pystray.Icon = _gtk_mod.Icon
                _log("Linux X11 legacy tray: using Gtk.StatusIcon for left/right custom popup (per pystray#47)")
            except Exception as e:
                _log(f"Gtk patch warn: {e}")
                use_gtk_for_custom = False

        # Cross-platform menu: keep custom WebKit popup as Linux Gtk custom; AppIndicator/Win/mac use native menu
        is_linux = sys.platform.startswith("linux")
        if is_linux and use_gtk_for_custom:
            # Gtk custom popup handles both clicks; native menu hidden (empty) so no double menu
            try:
                menu = pystray.Menu()  # empty -> Gtk popup-menu handler shows custom instead
            except:
                menu = None
        elif is_linux:
            # AppIndicator on GNOME/Wayland: native menu per HIG (both clicks show menu). Provide real actions.
            # Custom WebKit available via "Dashboard" item (second click) – proper per SNI spec.
            def _open_settings(icon, item):
                try:
                    from gi.repository import GLib
                    # Try dashboard settings view, else standalone dialog
                    _show_dashboard()
                    # Also show standalone dialog as fallback
                    GLib.timeout_add(600, lambda: (show_settings_dialog(), False)[1])
                except:
                    try: show_settings_dialog()
                    except: pass
            try:
                menu = pystray.Menu(
                    pystray.MenuItem("Dashboard", lambda i, it: _show_dashboard()),
                    pystray.MenuItem("Open DEVELOPER", on_open_developer),
                    pystray.Menu.SEPARATOR,
                    pystray.MenuItem("Merge all", on_merge_all),
                    pystray.MenuItem("Sync models", on_sync_models),
                    pystray.Menu.SEPARATOR,
                    pystray.MenuItem("Settings…", _open_settings),
                    pystray.MenuItem("Quit", on_quit),
                )
            except:
                try:
                    menu = pystray.Menu(pystray.MenuItem("Quit", on_quit))
                except:
                    menu = None
        else:
            # Windows / macOS: native pystray menu
            def _open_settings_win(icon, item):
                try:
                    # On Win/mac, try dashboard; fallback dialog not available (no Gtk), just open dashboard
                    _show_dashboard()
                except:
                    pass
                try:
                    # Windows settings via dashboard or simple message
                    import json as _js
                    s = load_settings()
                    # Toggle autostart as example
                    pass
                except: pass
            try:
                menu = pystray.Menu(
                    pystray.MenuItem("Open DEVELOPER", on_open_developer),
                    pystray.MenuItem("Merge all", on_merge_all),
                    pystray.Menu.SEPARATOR,
                    pystray.MenuItem("Sync models", on_sync_models),
                    pystray.Menu.SEPARATOR,
                    pystray.MenuItem("Settings…", _open_settings_win),
                    pystray.MenuItem("Quit", on_quit),
                )
            except:
                menu = pystray.Menu(
                    pystray.MenuItem("Quit", on_quit)
                )

        icon = pystray.Icon("nexaura-fuse", image, "NEXAURA FUSE", menu)

        # No secondary-activate hack: proper backend already handles clicks per spec
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
        _log(f"Tray entering icon.run() backend={pystray.Icon.__module__}")
        icon.run()
        _log("Tray icon.run() exited normally")
    except Exception as e:
        _log(f"Tray failed {e!r}, running headless. Use --merge <app>")
        _tb.print_exc()
        # Fallback CLI
        if len(sys.argv) > 1:
            print(merge_app(sys.argv[1]))
        else:
            for a in APPS:
                print(a, get_status())

def run_window():
    """Fallback for Zorin single bottom bar - appears as app in taskbar, not tray"""
    import gi
    gi.require_version('Gtk', '3.0')
    from gi.repository import Gtk, GdkPixbuf
    s = get_status()
    win = Gtk.Window(title="NEXAURA FUSE")
    win.set_default_size(360, 220)
    win.set_position(Gtk.WindowPosition.CENTER)
    win.set_skip_taskbar_hint(False)
    win.set_skip_pager_hint(False)
    # icon
    icon_path = DEVELOPER / "FUSE/assets/logo-256.png"
    if not icon_path.exists():
        base = Path(getattr(sys, '_MEIPASS', Path(__file__).parent))
        for cand in [base / "assets/logo-256.png", Path(__file__).parent / "assets/logo-256.png"]:
            if cand.exists():
                icon_path = cand; break
    if icon_path.exists():
        try:
            win.set_icon_from_file(str(icon_path))
        except: pass
    vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    vbox.set_border_width(12)
    win.add(vbox)
    lbl = Gtk.Label(label=f"NEXAURA FUSE\n{s['disk']} • {s['models']} models • {s['apps_merged']} apps merged")
    lbl.set_justify(Gtk.Justification.CENTER)
    vbox.pack_start(lbl, False, False, 4)
    # buttons
    def mk_btn(label, cb):
        b = Gtk.Button(label=label)
        b.connect("clicked", cb)
        vbox.pack_start(b, False, False, 2)
        return b
    mk_btn("Merge all", lambda w: [print(merge_app(a)) for a in APPS])
    mk_btn("Open DEVELOPER", lambda w: subprocess.Popen(["xdg-open", str(DEVELOPER)]))
    mk_btn("Sync models", lambda w: print(sync_models_to_providers()))
    mk_btn("Quit", lambda w: Gtk.main_quit())
    # merge app submenu as combo
    combo = Gtk.ComboBoxText()
    for app in APPS: combo.append_text(app)
    combo.set_active(0)
    vbox.pack_start(combo, False, False, 2)
    def on_combo_merge(w):
        app = combo.get_active_text()
        if app: print(merge_app(app))
    mk_btn("Merge selected app", on_combo_merge)
    win.set_wmclass("FUSE","FUSE")
    # X should hide to taskbar, not quit - use minimize
    def _on_delete(w,e):
        w.hide_on_delete()
        return True
    win.connect("delete-event", _on_delete)
    win.show_all()
    # keep tray also if possible in bg thread
    def try_tray():
        try: run_tray()
        except: pass
    import threading
    threading.Thread(target=try_tray, daemon=True).start()
    Gtk.main()

def run_dark():
    """Modern dark animated frontend - opencode oc-2 style with WebKit2"""
    import gi
    gi.require_version('Gtk', '3.0')
    gi.require_version('WebKit2', '4.1')
    from gi.repository import Gtk, GdkPixbuf, WebKit2, GLib
    import json as _json

    win = Gtk.Window(title="NEXAURA FUSE")
    win.set_default_size(1020, 680)
    win.set_position(Gtk.WindowPosition.CENTER)
    win.set_skip_taskbar_hint(False)
    win.set_skip_pager_hint(False)
    win.set_wmclass("FUSE","FUSE")
    win.set_decorated(False)  # frameless - opencode style, no native header
    win.set_resizable(True)
    # store globally for tray DASHBOARD to focus
    globals()["_DARK_WIN"] = win
    # --- Frameless rounded + transparent (fix black square around window) ---
    # Must set RGBA visual BEFORE realize, app_paintable, and clear with SOURCE
    # Window itself is transparent; WebKit is also transparent so HTML border-radius shows desktop, not black
    try:
        from gi.repository import Gdk
        import cairo as _cairo_dash
        screen = win.get_screen()
        visual = screen.get_rgba_visual()
        if visual:
            win.set_visual(visual)
        win.set_app_paintable(True)
        # Clear window to transparent - fixes black square on Mutter/X11
        def _dash_draw(w, cr):
            cr.set_source_rgba(0, 0, 0, 0)
            cr.set_operator(_cairo_dash.Operator.SOURCE)
            cr.paint()
            cr.set_operator(_cairo_dash.Operator.OVER)
            return False
        win.connect("draw", _dash_draw)
        css = b"""
        window, decoration, .background, window.background {
            background-color: transparent;
            background: transparent;
            border: none;
            box-shadow: none;
        }
        decoration, window.csd decoration {
            border-radius: 12px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.55), 0 0 0 1px rgba(255,255,255,0.08);
            background: transparent;
        }
        /* HTML body provides visible #080808 with 12px radius; window remains transparent outside */
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css)
        Gtk.StyleContext.add_provider_for_screen(screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        # also add class for CSD rounding
        try:
            win.get_style_context().add_class("csd")
        except: pass
    except: pass
    # icon
    icon_path = DEVELOPER / "FUSE/assets/logo-256.png"
    if not icon_path.exists():
        base = Path(getattr(sys, '_MEIPASS', Path(__file__).parent))
        for cand in [base / "assets/logo-256.png", Path(__file__).parent / "assets/logo-256.png"]:
            if cand.exists():
                icon_path = cand; break
    if icon_path.exists():
        try: win.set_icon_from_file(str(icon_path))
        except: pass

    # WebKit view
    manager = WebKit2.UserContentManager()
    manager.register_script_message_handler("fuse")
    settings = WebKit2.Settings()
    try:
        settings.set_enable_javascript(True)
        settings.set_allow_file_access_from_file_urls(True)
        settings.set_allow_universal_access_from_file_urls(True)
        settings.set_enable_developer_extras(True)
    except: pass

    webview = WebKit2.WebView.new_with_user_content_manager(manager)
    webview.set_settings(settings)
    try:
        from gi.repository import Gdk
        # Transparent so window's rounded transparent corners show desktop, not black square
        # HTML body (#080808) provides the visible dark background with border-radius:12px
        rgba = Gdk.RGBA()
        rgba.parse("rgba(0,0,0,0)")
        webview.set_background_color(rgba)
        view = webview  # alias for compat
        webview.set_app_paintable(True)
    except: pass
    # No extra container - window transparent + WebKit transparent + HTML rounded (12px)
    # keeps outer corners transparent (no black square). EventBox would reintroduce opaque square.
    _dash_container = None
    # Store globally for tray -> settings view switch
    globals()["_DARK_WEBVIEW"] = webview

    def on_fuse_message(mgr, msg):
        try:
            # WebKit2 API differs: try get_js_value / get_jsc_value
            try: js = msg.get_js_value()
            except: js = msg.get_jsc_value()
            raw = js.to_string() if hasattr(js,"to_string") else str(js)
        except Exception as e:
            print(f"fuse msg parse err {e}")
            return
        try:
            data = _json.loads(raw)
        except:
            # raw may be quoted string
            try: data = _json.loads(_json.loads(raw))
            except: data = {"action": raw}
        action = data.get("action") if isinstance(data, dict) else str(data)
        app = data.get("app") if isinstance(data, dict) else None
        cb = data.get("cb") if isinstance(data, dict) else None
        result = ""
        try:
            if action == "get_status":
                result = _json.dumps(get_status())
            elif action == "merge":
                result = merge_app(app) if app else "no app"
            elif action == "open":
                # OPEN: launch the application itself (not just folder)
                launched = False
                if app and app in APP_LAUNCH:
                    for cmd in APP_LAUNCH[app]:
                        try:
                            # handle flatpak style with spaces
                            parts = cmd.split() if " " in cmd and not cmd.startswith("/") else [cmd]
                            # expand ~/...
                            parts = [os.path.expanduser(p) for p in parts]
                            # check if binary exists for single cmd
                            if len(parts)==1 and "/" not in parts[0]:
                                if subprocess.run(["which", parts[0]], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode != 0:
                                    continue
                            subprocess.Popen(parts, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
                            launched = True
                            result = f"launched {cmd}"
                            break
                        except: continue
                if not launched:
                    cfg = APPS.get(app) if app else None
                    target = str(cfg["dst"] if cfg and cfg["dst"].exists() else cfg["src"] if cfg else DEVELOPER)
                    try: subprocess.Popen(["xdg-open", target])
                    except: pass
                    result = f"opened {target}" if not launched else result
            elif action == "reveal":
                # REVEAL: highlight file in file manager (ShowItems) distinct from OPEN
                cfg = APPS.get(app) if app else None
                target = str(cfg["dst"] if cfg and cfg["dst"].exists() else cfg["src"] if cfg else DEVELOPER)
                try:
                    uri = Path(target).as_uri()
                    # Try org.freedesktop.FileManager1 ShowItems to highlight
                    subprocess.Popen(["dbus-send","--session","--dest=org.freedesktop.FileManager1","--type=method_call","/org/freedesktop/FileManager1","org.freedesktop.FileManager1.ShowItems",f"array:string:{uri}","string:"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    # fallback also open parent
                    subprocess.Popen(["gio","open", str(Path(target).parent)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                except:
                    subprocess.Popen(["xdg-open", str(Path(target).parent)])
                result = f"revealed {target}"
            elif action == "sync":
                result = sync_models_to_providers()
            elif action == "open_developer":
                subprocess.Popen(["xdg-open", str(DEVELOPER)])
                result = "opened"
            elif action == "close":
                GLib.idle_add(win.hide)
                result = "hidden"
            elif action == "minimize":
                GLib.idle_add(win.iconify)
                result = "minimized"
            elif action == "drag":
                # frameless drag - begin_move_drag
                try:
                    from gi.repository import Gdk
                    # use current event time
                    display = Gdk.Display.get_default()
                    seat = display.get_default_seat() if display else None
                    # fallback simple
                    GLib.idle_add(lambda: win.begin_move_drag(1, int(data.get("x",100)), int(data.get("y",100)), 0))
                except Exception as e:
                    print(f"drag err {e}")
                result = "dragging"
            elif action == "get_settings":
                try:
                    s = load_settings()
                    s["autostart_enabled"] = is_autostart_enabled()
                    s["exe_path"] = get_autostart_exec()
                    s["developer_exists"] = str(DEVELOPER.exists())
                    s["current_developer"] = str(DEVELOPER)
                    result = _json.dumps(s)
                except Exception as e:
                    result = _json.dumps({"error": str(e)})
            elif action == "save_settings":
                try:
                    # data may contain developer_path, run_on_startup, start_minimized
                    new_dev = data.get("developer_path") if isinstance(data, dict) else None
                    run_on = data.get("run_on_startup") if isinstance(data, dict) else None
                    start_min = data.get("start_minimized") if isinstance(data, dict) else None
                    s = load_settings()
                    changed_dev = False
                    if new_dev and isinstance(new_dev, str) and new_dev.strip():
                        s["developer_path"] = new_dev.strip()
                        try:
                            refresh_developer_paths(Path(new_dev.strip()))
                            changed_dev = True
                        except: pass
                    if run_on is not None:
                        s["run_on_startup"] = bool(run_on)
                        set_autostart(bool(run_on))
                    if start_min is not None:
                        s["start_minimized"] = bool(start_min)
                    save_settings(s)
                    result = _json.dumps({"ok": True, "changed_dev": changed_dev, "developer": str(DEVELOPER), "autostart": is_autostart_enabled()})
                except Exception as e:
                    result = _json.dumps({"error": str(e)})
            elif action == "pick_developer":
                # Open Gtk FileChooser and return selected path
                try:
                    import gi
                    gi.require_version('Gtk', '3.0')
                    from gi.repository import Gtk
                    def _pick():
                        dlg = Gtk.FileChooserDialog(title="Pick DEVELOPER folder", action=Gtk.FileChooserAction.SELECT_FOLDER)
                        dlg.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, "Select", Gtk.ResponseType.OK)
                        cur = str(DEVELOPER)
                        try: dlg.set_current_folder(cur)
                        except: pass
                        resp = dlg.run()
                        sel = dlg.get_filename() if resp == Gtk.ResponseType.OK else ""
                        dlg.destroy()
                        return sel
                    # Need to run on main thread
                    sel = ""
                    # Use GLib idle to run dialog? For now run directly if in main thread, else idle
                    try:
                        # If we are in WebKit callback (main thread), run directly
                        sel = _pick()
                    except: sel = ""
                    result = _json.dumps({"path": sel})
                except Exception as e:
                    result = _json.dumps({"error": str(e), "path": ""})
            elif action == "open_settings":
                try:
                    # Open standalone GTK settings dialog (blocks main loop via dialog run in idle)
                    GLib.idle_add(lambda: (show_settings_dialog(win), False)[1])
                    result = "opening"
                except Exception as e:
                    result = f"err {e}"
            elif action == "invoke":
                # generic for pywebview compat: first arg is method
                result = _json.dumps(get_status())
            else:
                result = f"unknown {action}"
        except Exception as e:
            result = f"err {e}"
        # send back via cb
        if cb:
            esc = _json.dumps(result)
            js_code = f"if(window['{cb}']) window['{cb}']({esc}); else if(window._fuse_cb) window._fuse_cb({esc});"
            try: webview.run_javascript(js_code, None, None, None)
            except: 
                try: webview.evaluate_javascript(js_code, -1, None, None, None, None)
                except: pass
        else:
            # for get_status polling, also inject
            pass

    manager.connect("script-message-received::fuse", on_fuse_message)

    # fallback http server for fetch (port 8765)
    def start_http():
        import http.server, socketserver, json as _js, urllib.parse
        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                parsed = urllib.parse.urlparse(self.path)
                qs = urllib.parse.parse_qs(parsed.query)
                try:
                    if parsed.path == "/api/status":
                        self.send_response(200); self.send_header("Content-type","application/json"); self.send_header("Access-Control-Allow-Origin","*"); self.end_headers()
                        self.wfile.write(_js.dumps(get_status()).encode())
                    elif parsed.path.startswith("/api/merge"):
                        app = qs.get("app", [""])[0]
                        res = merge_app(app) if app else "no app"
                        self.send_response(200); self.send_header("Content-type","text/plain"); self.send_header("Access-Control-Allow-Origin","*"); self.end_headers()
                        self.wfile.write(res.encode())
                    elif parsed.path == "/api/sync":
                        res = sync_models_to_providers()
                        self.send_response(200); self.send_header("Content-type","text/plain"); self.send_header("Access-Control-Allow-Origin","*"); self.end_headers()
                        self.wfile.write(res.encode())
                    elif parsed.path == "/api/settings":
                        if self.command == "GET":
                            s = load_settings()
                            s["autostart_enabled"] = is_autostart_enabled()
                            s["exe_path"] = get_autostart_exec()
                            s["current_developer"] = str(DEVELOPER)
                            self.send_response(200); self.send_header("Content-type","application/json"); self.send_header("Access-Control-Allow-Origin","*"); self.end_headers()
                            self.wfile.write(_js.dumps(s).encode())
                        else:  # POST
                            length = int(self.headers.get('Content-Length', 0))
                            body = self.rfile.read(length).decode() if length else "{}"
                            try:
                                data = _js.loads(body)
                                if "developer_path" in data:
                                    s = load_settings()
                                    s["developer_path"] = data["developer_path"]
                                    refresh_developer_paths(Path(data["developer_path"]))
                                    save_settings(s)
                                if "run_on_startup" in data:
                                    set_autostart(bool(data["run_on_startup"]))
                                    s = load_settings(); s["run_on_startup"] = bool(data["run_on_startup"]); save_settings(s)
                                self.send_response(200); self.send_header("Content-type","application/json"); self.send_header("Access-Control-Allow-Origin","*"); self.end_headers()
                                self.wfile.write(b'{"ok":true}')
                            except Exception as e:
                                self.send_response(500); self.end_headers(); self.wfile.write(str(e).encode())
                    elif parsed.path == "/api/open":
                        subprocess.Popen(["xdg-open", str(DEVELOPER)])
                        self.send_response(200); self.end_headers(); self.wfile.write(b"ok")
                    # Handle POST for /api/settings via do_POST
                    else:
                        self.send_response(404); self.end_headers()
                except Exception as e:
                    self.send_response(500); self.end_headers(); self.wfile.write(str(e).encode())
            def do_POST(self):
                parsed = urllib.parse.urlparse(self.path)
                if parsed.path == "/api/settings":
                    length = int(self.headers.get('Content-Length', 0))
                    body = self.rfile.read(length).decode() if length else "{}"
                    try:
                        data = _js.loads(body)
                        s = load_settings()
                        if "developer_path" in data:
                            s["developer_path"] = data["developer_path"]
                            try: refresh_developer_paths(Path(data["developer_path"]))
                            except: pass
                        if "run_on_startup" in data:
                            s["run_on_startup"] = bool(data["run_on_startup"])
                            set_autostart(bool(data["run_on_startup"]))
                        if "start_minimized" in data:
                            s["start_minimized"] = bool(data["start_minimized"])
                        save_settings(s)
                        self.send_response(200); self.send_header("Content-type","application/json"); self.send_header("Access-Control-Allow-Origin","*"); self.end_headers()
                        self.wfile.write(b'{"ok":true}')
                    except Exception as e:
                        self.send_response(500); self.end_headers(); self.wfile.write(str(e).encode())
                else:
                    self.send_response(404); self.end_headers()
            def log_message(self, format, *args): pass
        try:
            with socketserver.TCPServer(("127.0.0.1", 8765), H) as httpd:
                httpd.serve_forever()
        except: pass
    threading.Thread(target=start_http, daemon=True).start()

    # load frontend
    html_path = DEVELOPER / "FUSE/frontend/index.html"
    if not html_path.exists():
        # fallback to old window
        html_path = Path(__file__).parent / "frontend/index.html"
    uri = html_path.as_uri() if html_path.exists() else "about:blank"
    webview.load_uri(uri)

    # header bar for drag (WebKit handles) - direct add, window/WebKit transparent lets HTML rounding show
    win.add(webview)
    def _on_delete(w,e):
        w.hide_on_delete()
        return True
    win.connect("delete-event", _on_delete)
    win.show_all()
    # also try tray in bg
    def try_tray():
        try: run_tray()
        except: pass
    threading.Thread(target=try_tray, daemon=True).start()
    Gtk.main()

def ensure_singleton():
    """Singleton: only one FUSE may run. If already running, focus its window and exit."""
    lock_path = Path("/tmp/nexaura-fuse.lock")
    pid_path = Path("/tmp/nexaura-fuse.pid")
    try:
        fp = open(lock_path, "w")
        fcntl.flock(fp, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # keep lock alive
        fp.write(str(os.getpid()))
        fp.flush()
        # write pid file
        try: pid_path.write_text(str(os.getpid()))
        except: pass
        def _cleanup():
            try:
                fcntl.flock(fp, fcntl.LOCK_UN)
                fp.close()
                lock_path.unlink(missing_ok=True)
                pid_path.unlink(missing_ok=True)
            except: pass
        atexit.register(_cleanup)
        return fp  # keep reference
    except (IOError, OSError, BlockingIOError):
        # another instance holds lock - try to focus its window then exit
        try:
            # try to raise existing window
            for cmd in [["wmctrl","-a","NEXAURA FUSE"], ["xdotool","search","--name","NEXAURA FUSE","windowactivate"], ["gdbus","call","--session","--dest","org.gnome.Shell","--object-path","/org/gnome/Shell","--method","org.gnome.Shell.Eval","Main.activateWindow(null)"]]:
                try:
                    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    break
                except: continue
            # also notify via print
            print("FUSE already running - focused existing window")
        except: pass
        sys.exit(0)

if __name__ == "__main__":
    _lock_fp = ensure_singleton() if "--help" not in sys.argv and "help" not in sys.argv else None
    if len(sys.argv) > 1 and sys.argv[1] in APPS:
        print(merge_app(sys.argv[1]))
        print(sync_models_to_providers())
    elif len(sys.argv) > 1 and sys.argv[1] == "--sync-models":
        print(sync_models_to_providers())
    elif len(sys.argv) > 1 and sys.argv[1] == "--window":
        try: run_dark()
        except Exception as e:
            print(f"dark failed {e}, fallback window")
            run_window()
    elif len(sys.argv) > 1 and sys.argv[1] == "--tray":
        run_tray()
    elif len(sys.argv) > 1 and sys.argv[1] == "--dark":
        run_dark()
    else:
        # Auto: Zorin with single bottom bar (stockgs-keep-top-panel false) has no AppIndicator host in bottom
        # Detect and use dark animated frontend so icon appears in taskbar instead of invisible top tray
        try:
            import subprocess as _sp
            top = _sp.check_output(["gsettings","get","org.gnome.shell.extensions.zorin-taskbar","stockgs-keep-top-panel"], text=True).strip()
            if "false" in top.lower():
                try: run_dark()
                except Exception as e:
                    print(f"dark auto failed {e}, fallback")
                    run_window()
            else:
                run_tray()
        except:
            try: run_dark()
            except: run_tray()
