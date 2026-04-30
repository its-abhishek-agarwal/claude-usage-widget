#!/usr/bin/env python3
"""
Claude Usage Tracker
Floating desktop widget that shows real Claude.ai usage by reading your
browser session cookie and polling the claude.ai usage API.
"""
from __future__ import annotations

import sys


def _run_native_host():
    """Run as Chrome native messaging host (invoked via --native-host flag)."""
    import os, struct, json, subprocess, time

    try:
        _in  = os.fdopen(0, "rb", 0)
        _out = os.fdopen(1, "wb", 0)
    except Exception:
        _in  = sys.stdin.buffer
        _out = sys.stdout.buffer

    def _read():
        raw = _in.read(4)
        if len(raw) < 4:
            return None
        length = struct.unpack("=I", raw)[0]
        return json.loads(_in.read(length).decode("utf-8"))

    def _send(data):
        payload = json.dumps(data).encode("utf-8")
        _out.write(struct.pack("=I", len(payload)) + payload)
        _out.flush()

    def _widget_up():
        try:
            import requests
            requests.get("http://127.0.0.1:9871/status", timeout=1)
            return True
        except Exception:
            return False

    def _launch_widget():
        subprocess.Popen([sys.executable], creationflags=0x08000000, close_fds=True)

    if not _widget_up():
        _launch_widget()
        for _ in range(10):
            time.sleep(0.5)
            if _widget_up():
                break

    _send({"status": "ok"})

    while True:
        msg = _read()
        if msg is None:
            break
        if msg.get("type") == "cookies":
            try:
                import requests
                requests.post("http://127.0.0.1:9871/cookies",
                              json=msg.get("data", {}), timeout=2)
                _send({"status": "ok"})
            except Exception as exc:
                _send({"status": "error", "msg": str(exc)})
        else:
            _send({"status": "ok"})


if len(sys.argv) > 1 and sys.argv[1] == "--native-host":
    _run_native_host()
    sys.exit(0)


import tkinter as tk
import os
import threading
import time
import json
import requests
from datetime import datetime, timezone
from pathlib import Path

APPDATA_DIR  = Path(os.environ.get("APPDATA", str(Path.home()))) / "ClaudeTracker"
INSTALL_DIR  = Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / "ClaudeTracker"


def _make_shortcut(lnk_path: Path, target: Path):
    try:
        import subprocess
        ps = (
            f'$s=(New-Object -COM WScript.Shell).CreateShortcut("{lnk_path}");'
            f'$s.TargetPath="{target}";'
            f'$s.WorkingDirectory="{target.parent}";'
            f'$s.IconLocation="{target}";'
            f'$s.Description="Claude Usage Tracker";'
            f'$s.Save()'
        )
        subprocess.run(
            ["powershell", "-WindowStyle", "Hidden", "-Command", ps],
            creationflags=0x08000000, timeout=10,
        )
    except Exception as exc:
        print(f"[Install] Shortcut {lnk_path.name}: {exc}", flush=True)


def _ensure_shortcuts(target: Path):
    desktop     = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Desktop"
    start_menu  = (Path(os.environ.get("APPDATA", str(Path.home())))
                   / "Microsoft" / "Windows" / "Start Menu" / "Programs")
    for folder in (desktop, start_menu):
        lnk = folder / "Claude Usage Tracker.lnk"
        if not lnk.exists():
            _make_shortcut(lnk, target)
            print(f"[Install] Shortcut created: {lnk}", flush=True)


def _self_install():
    """On first run outside Program Files, copy .exe there with UAC elevation and relaunch."""
    if not getattr(sys, "frozen", False):
        return
    src = Path(sys.executable)
    dst = INSTALL_DIR / "ClaudeTracker.exe"
    if src.resolve() == dst.resolve():
        _ensure_shortcuts(dst)
        return
    import shutil, subprocess
    try:
        INSTALL_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    except PermissionError:
        import ctypes
        ctypes.windll.shell32.ShellExecuteW(None, "runas", str(src), "", None, 1)
        sys.exit(0)
    _ensure_shortcuts(dst)
    subprocess.Popen([str(dst)], creationflags=0x08000000)
    sys.exit(0)

import pystray
from PIL import Image, ImageDraw, ImageTk

try:
    import browser_cookie3
    HAS_COOKIE_LIB = True
except ImportError:
    HAS_COOKIE_LIB = False

# ── Config ───────────────────────────────────────────────────────────────────

CONFIG_PATH = Path.home() / ".claude_tracker" / "config.json"
POLL_INTERVAL = 120          # seconds between API calls
API_BASE      = "https://claude.ai"

# ── Theme ────────────────────────────────────────────────────────────────────

PILL_KEY = "#000002"  # transparent chroma-key for rounded pill window

BG       = "#1a1a1a"
BG_TITLE = "#111111"
BG_CARD  = "#252525"
BG_BAR   = "#383838"
FG       = "#e0e0e0"
FG_DIM   = "#666666"
FG_LABEL = "#999999"

C_GREEN  = "#4ade80"
C_YELLOW = "#facc15"
C_ORANGE = "#fb923c"
C_RED    = "#f87171"

def pct_color(pct: float) -> str:
    if pct < 60:  return C_GREEN
    if pct < 80:  return C_YELLOW
    if pct < 95:  return C_ORANGE
    return C_RED


# ── Main App ─────────────────────────────────────────────────────────────────

class ClaudeTracker:

    def __init__(self):
        # Single-instance guard — Windows named mutex is atomic and survives port timing races
        import ctypes, sys as _sys
        _MUTEX_NAME = "ClaudeTrackerWidget_SingleInstance"
        self._mutex = ctypes.windll.kernel32.CreateMutexW(None, True, _MUTEX_NAME)
        if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
            _sys.exit(0)

        self.org_id: str | None = None
        self.usage: dict        = {}
        self.last_updated: datetime | None = None
        self.auth_ok: bool      = False

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Referer": "https://claude.ai/settings/usage",
            "Accept":  "application/json, text/plain, */*",
        })

        self.config  = self._load_config()
        self.org_id  = self.config.get("org_id")

        # Drag state
        self._drag_x = self._drag_y = 0
        self._pdrag_x = self._pdrag_y = 0
        self._click_x = self._click_y = 0
        self._did_drag = False

        # Build UI
        self.root = tk.Tk()
        self.root.withdraw()

        self._build_pill()
        self._build_panel()
        self.root.after(100, self._keep_on_top)
        self.root.after(100, self._start_topmost_hook)
        self.root.after(200, self._set_pill_no_activate)

        # Background threads
        threading.Thread(target=self._init_worker,    daemon=True).start()
        threading.Thread(target=self._run_tray,       daemon=True).start()
        threading.Thread(target=self._start_server,   daemon=True).start()

        self._register_startup()
        self._setup_native_host()
        self.root.mainloop()

    # ── Persistence ──────────────────────────────────────────────────────────

    def _load_config(self) -> dict:
        try:
            if CONFIG_PATH.exists():
                return json.loads(CONFIG_PATH.read_text())
        except Exception:
            pass
        return {}

    def _save_config(self):
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(json.dumps(self.config, indent=2))

    # ── Auth / Polling ───────────────────────────────────────────────────────

    def _init_worker(self):
        self._load_cookies()
        self._poll_loop()

    # ── Cookie loading ────────────────────────────────────────────────────────

    def _load_cookies(self):
        """Try every browser (rookiepy → browser_cookie3 → saved credentials)."""
        jar = self._read_browser_cookies()
        if jar is not None:
            self.session.cookies = jar
            self.auth_ok = True
            return

        # Fall back to manually saved session key
        if self.org_id and self.config.get("session_key"):
            self.session.cookies.set(
                "sessionKey", self.config["session_key"], domain=".claude.ai"
            )
            self.auth_ok = True
            print("[Auth] Using saved session key", flush=True)
            return

        print("[Auth] No credentials found — prompting setup", flush=True)
        self.root.after(0, lambda: self._set_status("Setup needed — click Setup →"))

    def _read_browser_cookies(self) -> "requests.cookies.RequestsCookieJar | None":
        """Return a fresh cookie jar from any readable browser, or None."""
        import traceback

        # rookiepy handles Chrome 127+ App-Bound Encryption better than browser_cookie3
        try:
            import rookiepy as rp
            for name, loader in [
                ("Chrome",  lambda: rp.chrome(["claude.ai"])),
                ("Edge",    lambda: rp.edge(["claude.ai"])),
                ("Firefox", lambda: rp.firefox(["claude.ai"])),
            ]:
                try:
                    jar, org_id = self._jar_from_rookiepy(loader())
                    if org_id:
                        self.org_id = org_id
                        self.config["org_id"] = org_id
                        self._save_config()
                        print(f"[Auth] rookiepy/{name}: org_id={org_id}", flush=True)
                        return jar
                    print(f"[Auth] rookiepy/{name}: no lastActiveOrg", flush=True)
                except Exception as exc:
                    print(f"[Auth] rookiepy/{name}: {exc}", flush=True)
        except ImportError:
            pass

        # browser_cookie3 as fallback (works for Firefox, Edge, older Chrome)
        if HAS_COOKIE_LIB:
            for name, loader in [
                ("Chrome",  lambda: browser_cookie3.chrome(domain_name=".claude.ai")),
                ("Edge",    lambda: browser_cookie3.edge(domain_name=".claude.ai")),
                ("Firefox", lambda: browser_cookie3.firefox(domain_name=".claude.ai")),
            ]:
                try:
                    jar = requests.cookies.RequestsCookieJar()
                    for c in loader():
                        jar.set(c.name, c.value, domain=c.domain, path=c.path)
                    org_id = next(
                        (c.value for c in jar if c.name == "lastActiveOrg"), None
                    )
                    if org_id:
                        self.org_id = org_id
                        self.config["org_id"] = org_id
                        self._save_config()
                        print(f"[Auth] browser_cookie3/{name}: org_id={org_id}", flush=True)
                        return jar
                    print(f"[Auth] browser_cookie3/{name}: cookies={[c.name for c in jar]}", flush=True)
                except Exception as exc:
                    print(f"[Auth] browser_cookie3/{name}: {exc}", flush=True)
                    traceback.print_exc()

        return None

    def _jar_from_rookiepy(self, cookies: list):
        """Convert rookiepy cookie list → (RequestsCookieJar, org_id)."""
        jar = requests.cookies.RequestsCookieJar()
        org_id = None
        for c in cookies:
            name  = c.get("name", "")
            value = c.get("value", "")
            dom   = c.get("host") or c.get("domain") or ".claude.ai"
            jar.set(name, value, domain=dom, path=c.get("path", "/"))
            if name == "lastActiveOrg":
                org_id = value
        return jar, org_id

    # ── API calls ─────────────────────────────────────────────────────────────

    def _fetch_usage(self):
        if not self.org_id:
            self.root.after(0, lambda: self._set_status("Setup needed — click Setup →"))
            return
        try:
            r = self.session.get(
                f"{API_BASE}/api/organizations/{self.org_id}/usage",
                timeout=8,
            )
            if r.status_code == 200:
                self.usage        = r.json()
                self.last_updated = datetime.now()
                self.auth_ok      = True
                self.root.after(0, self._refresh_ui)
            elif r.status_code == 401:
                print("[Auth] 401 — session expired, re-reading browser cookies", flush=True)
                self.auth_ok = False
                self.config.pop("session_key", None)  # clear stale saved key
                self._save_config()
                threading.Thread(target=self._reload_auth, daemon=True).start()
            else:
                self.root.after(0, lambda: self._set_status(f"API error {r.status_code}"))
        except Exception as exc:
            self.root.after(0, lambda: self._set_status(f"Error: {exc}"))

    def _reload_auth(self):
        """Re-read browser cookies after expiry; show expired UI if that fails."""
        self._load_cookies()
        if self.auth_ok:
            self._fetch_usage()
        else:
            self.root.after(0, self._show_expired_ui)

    def _show_expired_ui(self):
        self._set_status("Session expired — click Setup →")
        if hasattr(self, "_dot"):
            self._dot.config(fg=C_ORANGE)
        self._show_setup_btn(True)

    def _show_setup_btn(self, visible: bool):
        if not hasattr(self, "_setup_btn"):
            return
        if visible:
            self._setup_btn.pack(side="right", padx=(4, 0))
        else:
            self._setup_btn.pack_forget()

    def _poll_loop(self):
        while True:
            self._fetch_usage()
            time.sleep(POLL_INTERVAL)

    # ── Windows startup registration ──────────────────────────────────────────

    def _register_startup(self):
        """Add widget to Windows startup registry (runs silently on every boot)."""
        try:
            import winreg
            if getattr(sys, "frozen", False):
                cmd = f'"{sys.executable}"'
            else:
                pythonw = Path(sys.executable).parent / "pythonw.exe"
                exe     = str(pythonw) if pythonw.exists() else sys.executable
                script  = str(Path(__file__).resolve())
                cmd     = f'"{exe}" "{script}"'
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0, winreg.KEY_SET_VALUE,
            )
            winreg.SetValueEx(key, "ClaudeTracker", 0, winreg.REG_SZ, cmd)
            winreg.CloseKey(key)
            print("[Startup] Registered in Windows startup", flush=True)
        except Exception as exc:
            print(f"[Startup] {exc}", flush=True)

    def _setup_native_host(self, ext_id: str = None):
        """Write native_host.bat + manifest to AppData and register in registry."""
        import winreg, json as _json
        APPDATA_DIR.mkdir(parents=True, exist_ok=True)

        if ext_id is None:
            id_file = APPDATA_DIR / ".extension_id"
            ext_id  = id_file.read_text().strip() if id_file.exists() else "EXTENSION_ID_PLACEHOLDER"

        bat_path = APPDATA_DIR / "native_host.bat"
        bat_path.write_text(f'@echo off\n"{sys.executable}" --native-host\n')

        manifest_path = APPDATA_DIR / "com.claude.tracker.json"
        manifest_path.write_text(_json.dumps({
            "name":        "com.claude.tracker",
            "description": "Claude Usage Tracker native host",
            "path":        str(bat_path),
            "type":        "stdio",
            "allowed_origins": [f"chrome-extension://{ext_id}/"],
        }, indent=2))

        for browser_key in [
            r"Software\Google\Chrome\NativeMessagingHosts",
            r"Software\Microsoft\Edge\NativeMessagingHosts",
        ]:
            try:
                key = winreg.CreateKey(
                    winreg.HKEY_CURRENT_USER, f"{browser_key}\\com.claude.tracker"
                )
                winreg.SetValueEx(key, "", 0, winreg.REG_SZ, str(manifest_path))
                winreg.CloseKey(key)
            except Exception:
                pass
        print("[Setup] Native messaging host registered", flush=True)

    def _remove_startup(self):
        """Remove widget from Windows startup registry."""
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0, winreg.KEY_SET_VALUE,
            )
            winreg.DeleteValue(key, "ClaudeTracker")
            winreg.CloseKey(key)
            print("[Startup] Removed from Windows startup", flush=True)
        except Exception as exc:
            print(f"[Startup] {exc}", flush=True)

    # ── Local HTTP server (receives cookies from browser extension) ────────────

    def _start_server(self):
        """Run a tiny HTTP server so the Chrome extension can push fresh cookies."""
        from http.server import HTTPServer, BaseHTTPRequestHandler
        import json as _json, functools

        tracker = self

        class Handler(BaseHTTPRequestHandler):
            def do_OPTIONS(self):
                self.send_response(200); self._cors(); self.end_headers()

            def do_POST(self):
                if self.path != "/cookies":
                    self.send_response(404); self.end_headers(); return
                length = int(self.headers.get("Content-Length", 0))
                try:
                    data = _json.loads(self.rfile.read(length))
                    tracker._on_extension_update(data)
                    self.send_response(200); self._cors()
                    self.end_headers()
                    self.wfile.write(b'{"ok":true}')
                except Exception as exc:
                    self.send_response(400); self.end_headers()
                    print(f"[Server] POST error: {exc}", flush=True)

            def do_GET(self):
                if self.path == "/status":
                    fh  = tracker.usage.get("five_hour") or {}
                    pct = float(fh.get("utilization") or 0)
                    body = _json.dumps({"pct": pct, "auth": tracker.auth_ok}).encode()
                    self.send_response(200); self._cors()
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", len(body))
                    self.end_headers()
                    self.wfile.write(body)
                elif self.path.startswith("/register?id="):
                    ext_id = self.path.split("=", 1)[1].strip()
                    if ext_id:
                        tracker._register_extension_id(ext_id)
                    self.send_response(200); self._cors()
                    self.end_headers()
                    self.wfile.write(b'{"ok":true}')
                else:
                    self.send_response(404); self.end_headers()

            def _cors(self):
                self.send_header("Access-Control-Allow-Origin",  "*")
                self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")

            def log_message(self, *a): pass  # silence HTTP logs

        try:
            srv = HTTPServer(("127.0.0.1", 9871), Handler)
            print("[Server] Listening on port 9871", flush=True)
            srv.serve_forever()
        except OSError:
            print("[Server] Port 9871 busy — another instance may be running", flush=True)

    def _on_extension_update(self, data: dict):
        """Handle fresh cookies pushed by the browser extension."""
        session_key = data.get("sessionKey", "").strip()
        org_id      = data.get("lastActiveOrg", "").strip()
        if not session_key or not org_id:
            return
        self.org_id = org_id
        self.config["org_id"]      = org_id
        self.config["session_key"] = session_key
        self.session.cookies.set("sessionKey", session_key, domain=".claude.ai")
        self.auth_ok = True
        self._save_config()
        print(f"[Server] Extension sent fresh cookies (org: {org_id})", flush=True)
        threading.Thread(target=self._fetch_usage, daemon=True).start()

    def _register_extension_id(self, ext_id: str):
        """Save extension ID and regenerate native messaging manifest."""
        id_file = APPDATA_DIR / ".extension_id"
        if id_file.exists() and id_file.read_text().strip() == ext_id:
            return
        APPDATA_DIR.mkdir(parents=True, exist_ok=True)
        id_file.write_text(ext_id)
        print(f"[Server] Extension registered: {ext_id}", flush=True)
        try:
            self._setup_native_host(ext_id)
        except Exception as exc:
            print(f"[Server] Could not update native host manifest: {exc}", flush=True)

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _time_until(self, iso: str) -> str:
        if not iso:
            return "—"
        try:
            dt = datetime.fromisoformat(iso)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            secs = int((dt - datetime.now(timezone.utc)).total_seconds())
            if secs <= 0:
                return "resetting…"
            h, rem = divmod(secs // 60, 60)
            return f"{h}h {rem}m" if h else f"{rem}m"
        except Exception:
            return "—"

    def _local_time(self, iso: str) -> str:
        if not iso:
            return ""
        try:
            dt = datetime.fromisoformat(iso)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone().strftime("%b %d · %I:%M %p")
        except Exception:
            return ""

    def _draw_bar(self, canvas: tk.Canvas, pct: float, color: str):
        canvas.update_idletasks()
        w  = canvas.winfo_width()
        if w < 4:
            w = 200
        h  = canvas.winfo_height() or 2
        fw = max(0, int(w * pct / 100))
        canvas.delete("all")

        def _cap(x1, x2, clr):
            if x2 - x1 < h:
                return
            canvas.create_arc(x1,     0, x1 + h, h, start=90,  extent=180,
                              fill=clr, outline="", style="chord")
            if x2 - x1 > h:
                canvas.create_rectangle(x1 + h//2, 0, x2 - h//2, h,
                                        fill=clr, outline="")
            canvas.create_arc(x2 - h, 0, x2,     h, start=270, extent=180,
                              fill=clr, outline="", style="chord")

        _cap(0, w,  BG_BAR)
        _cap(0, fw, color)

    def _rrect(self, canvas: tk.Canvas, x1, y1, x2, y2, r, color):
        """Draw a filled rounded rectangle on canvas."""
        pts = [x1+r,y1, x2-r,y1, x2,y1, x2,y1+r, x2,y2-r, x2,y2,
               x2-r,y2, x1+r,y2, x1,y2, x1,y2-r, x1,y1+r, x1,y1]
        canvas.create_polygon(pts, smooth=True, fill=color, outline="")

    def _rrect_pts(self, x1, y1, x2, y2, r):
        return [x1+r,y1, x2-r,y1, x2,y1, x2,y1+r, x2,y2-r, x2,y2,
                x2-r,y2, x1+r,y2, x1,y2, x1,y2-r, x1,y1+r, x1,y1]

    # ── Pill (collapsed widget) ───────────────────────────────────────────────

    def _build_pill(self):
        pill = tk.Toplevel(self.root)
        pill.overrideredirect(True)
        pill.wm_attributes("-topmost", True)
        pill.configure(bg=PILL_KEY)
        pill.wm_attributes("-transparentcolor", PILL_KEY)

        sw = pill.winfo_screenwidth()
        W, H = 175, 28
        import ctypes as _ct, ctypes.wintypes as _wt
        _work = _wt.RECT()
        _ct.windll.user32.SystemParametersInfoW(0x30, 0, _ct.byref(_work), 0)
        pill.geometry(f"{W}x{H}+{sw - W - 20}+{_work.bottom - H - 8}")

        c = tk.Canvas(pill, bg=PILL_KEY, highlightthickness=0, width=W, height=H)
        c.pack(fill="both", expand=True)

        self._pill_canvas = c
        self._pill_W, self._pill_H = W, H
        PX, BW, BH = 10, 52, 6
        by = (H - BH) // 2
        self._pill_bx, self._pill_by = PX, by
        self._pill_bw, self._pill_bh = BW, BH

        self._redraw_pill_image(0.0, C_GREEN)
        self._pill_img_id = c.create_image(0, 0, anchor="nw", image=self._pill_photo)

        self._pill_text_id = c.create_text(
            PX + BW + 8, H // 2, text="connecting...",
            fill="white", anchor="w", font=("Segoe UI", 9))
        c.create_text(W - PX - 2, H // 2 - 1, text="×",
                      fill="#999", anchor="e", font=("Segoe UI", 11))

        c.bind("<ButtonPress-1>",   self._on_pill_press)
        c.bind("<B1-Motion>",       self._on_pill_drag)
        c.bind("<ButtonRelease-1>", self._on_pill_release)
        c.bind("<Button-3>",        self._show_ctx_menu)

        self.pill = pill
        pill.after(200, lambda: pill.wm_attributes("-topmost", True))

    def _redraw_pill_image(self, pct: float, color: str):
        W, H  = self._pill_W, self._pill_H
        SCALE = 4
        WS, HS = W * SCALE, H * SCALE

        # Draw at 4x in RGBA, downsample with LANCZOS, then threshold alpha
        # so edge pixels are exactly PILL_KEY (transparent) or BG (opaque).
        img = Image.new("RGBA", (WS, HS), (0, 0, 0, 0))
        d   = ImageDraw.Draw(img)

        bg  = self._hex_to_rgb(BG) + (255,)
        r   = HS // 2
        d.rounded_rectangle([0, 0, WS - 1, HS - 1], radius=r, fill=bg)
        d.rounded_rectangle([0, 0, WS - 1, HS - 1], radius=r,
                             outline=(42, 42, 42, 255), width=SCALE)

        PX = self._pill_bx * SCALE
        BW = self._pill_bw * SCALE
        BH = self._pill_bh * SCALE
        by = self._pill_by * SCALE
        d.rounded_rectangle([PX, by, PX + BW - 1, by + BH - 1],
                             radius=BH // 2,
                             fill=self._hex_to_rgb(BG_BAR) + (255,))
        fw = max(0, int(BW * pct / 100))
        if fw >= 2 * SCALE:
            d.rounded_rectangle([PX, by, PX + fw - 1, by + BH - 1],
                                 radius=min(BH // 2, fw // 2),
                                 fill=self._hex_to_rgb(color) + (255,))

        img   = img.resize((W, H), Image.LANCZOS)
        alpha = img.split()[3]
        mask  = alpha.point(lambda a: 255 if a >= 128 else 0)
        result = Image.new("RGB", (W, H), self._hex_to_rgb(PILL_KEY))
        result.paste(img.convert("RGB"), mask=mask)

        self._pill_photo = ImageTk.PhotoImage(result)
        if hasattr(self, "_pill_img_id"):
            self._pill_canvas.itemconfig(self._pill_img_id, image=self._pill_photo)

    def _hex_to_rgb(self, h: str):
        h = h.lstrip("#")
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))

    def _keep_on_top(self):
        import ctypes
        from ctypes import wintypes
        u32 = ctypes.windll.user32
        u32.SetWindowPos.argtypes = [
            wintypes.HWND, wintypes.HWND,
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            wintypes.UINT,
        ]
        u32.SetWindowPos.restype = wintypes.BOOL
        IsVis = u32.IsWindowVisible
        GA    = u32.GetAncestor
        for win in [self.pill, getattr(self, "panel", None)]:
            if win:
                hwnd = GA(win.winfo_id(), 2) or win.winfo_id()  # GA_ROOT=2: wrapper HWND
                if hwnd and IsVis(hwnd):
                    u32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0013)
        self.root.after(50, self._keep_on_top)

    def _set_pill_no_activate(self):
        import ctypes
        u32 = ctypes.windll.user32
        hwnd = u32.GetAncestor(self.pill.winfo_id(), 2) or self.pill.winfo_id()
        GWL_EXSTYLE      = -20
        WS_EX_TOOLWINDOW = 0x00000080
        WS_EX_NOACTIVATE = 0x08000000
        style = u32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        u32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE)

    def _start_topmost_hook(self):
        import ctypes
        GA = ctypes.windll.user32.GetAncestor
        def _wrap(win):
            inner = win.winfo_id()
            return GA(inner, 2) or inner  # GA_ROOT=2: true top-level wrapper HWND
        self._pill_hwnd  = _wrap(self.pill)
        self._panel_hwnd = _wrap(self.panel)
        threading.Thread(target=self._run_topmost_hook, daemon=True).start()

    def _run_topmost_hook(self):
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        user32.SetWindowPos.argtypes = [
            wintypes.HWND, wintypes.HWND,
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            wintypes.UINT,
        ]
        user32.SetWindowPos.restype = wintypes.BOOL
        IsVis = user32.IsWindowVisible
        Sleep = ctypes.windll.kernel32.Sleep
        pill_h  = self._pill_hwnd
        panel_h = self._panel_hwnd
        GWL_EXSTYLE      = -20
        WS_EX_TOOLWINDOW = 0x00000080
        WS_EX_NOACTIVATE = 0x08000000
        for hwnd in [pill_h, panel_h]:
            try:
                s = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                user32.SetWindowLongW(hwnd, GWL_EXSTYLE, s | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE)
            except Exception:
                pass
        while True:
            Sleep(16)
            try:
                if IsVis(pill_h):
                    user32.SetWindowPos(pill_h,  -1, 0, 0, 0, 0, 0x0013)
                if IsVis(panel_h):
                    user32.SetWindowPos(panel_h, -1, 0, 0, 0, 0, 0x0013)
            except Exception:
                pass

    def _hide_pill(self):
        """Hide pill and panel — widget stays alive in tray."""
        self.pill.withdraw()
        if hasattr(self, "panel"):
            self.panel.withdraw()

    def _on_pill_press(self, e):
        self._click_x  = e.x_root
        self._click_y  = e.y_root
        self._drag_x   = e.x_root - self.pill.winfo_x()
        self._drag_y   = e.y_root - self.pill.winfo_y()
        self._did_drag = False

    def _on_pill_drag(self, e):
        if abs(e.x_root - self._click_x) > 3 or abs(e.y_root - self._click_y) > 3:
            self._did_drag = True
        if self._did_drag:
            self.pill.geometry(f"+{e.x_root - self._drag_x}+{e.y_root - self._drag_y}")

    def _on_pill_release(self, e):
        if not self._did_drag:
            if e.x > self._pill_W - 30:   # right 30px = close button area
                self._hide_pill()
                return
            if self.auth_ok:
                self._toggle_panel()
            else:
                self._show_setup_dialog()

    def _update_pill(self):
        fh    = self.usage.get("five_hour") or {}
        pct   = float(fh.get("utilization") or 0)
        color = pct_color(pct)
        countdown = self._time_until(fh.get("resets_at", ""))

        self._pill_canvas.itemconfig(self._pill_text_id, text=f"{pct:.0f}% · {countdown}")
        self._redraw_pill_image(pct, color)

    # ── Panel (expanded details) ──────────────────────────────────────────────

    def _build_panel(self):
        panel = tk.Toplevel(self.root)
        panel.overrideredirect(True)
        panel.wm_attributes("-topmost", True)
        panel.configure(bg=BG, highlightthickness=0, bd=0)
        panel.withdraw()

        # Title bar
        tbar = tk.Frame(panel, bg=BG_TITLE, padx=8, pady=5, highlightthickness=0, bd=0)
        tbar.pack(fill="x")
        tbar.bind("<ButtonPress-1>", self._on_panel_press)
        tbar.bind("<B1-Motion>",     self._on_panel_drag)

        tk.Label(tbar, text="Claude Usage Tracker", fg=FG, bg=BG_TITLE,
                 font=("Segoe UI", 9, "bold")).pack(side="left")

        btns = tk.Frame(tbar, bg=BG_TITLE, highlightthickness=0, bd=0)
        btns.pack(side="right")
        self._btn(btns, "—", self._minimize_panel)
        self._btn(btns, "✕", self._hide_pill)

        # Body
        body = tk.Frame(panel, bg=BG, padx=8, pady=5, highlightthickness=0, bd=0)
        body.pack(fill="both")

        self._cards: dict[str, dict] = {}
        self._cards["five_hour"]          = self._make_card(body, "CURRENT SESSION")
        self._cards["seven_day"]          = self._make_card(body, "THIS WEEK")
        self._cards["seven_day_omelette"] = self._make_card(body, "CLAUDE DESIGN")
        self._cards["extra_usage"]        = self._make_card(body, "EXTRA USAGE")

        # Footer
        foot = tk.Frame(panel, bg=BG, padx=8, highlightthickness=0, bd=0)
        foot.pack(fill="x", pady=(0, 5))

        self._status_lbl = tk.Label(foot, text="Connecting…", fg=FG_DIM, bg=BG,
                                     font=("Segoe UI", 8))
        self._status_lbl.pack(side="left")

        # Setup button — hidden by default, shown only when auth fails
        self._setup_btn = tk.Button(
            foot, text="⚙ Setup", fg=FG_DIM, bg=BG,
            activebackground=BG_CARD, relief="flat",
            font=("Segoe UI", 8), bd=0, cursor="hand2",
            command=self._show_setup_dialog,
        )

        tk.Button(
            foot, text="↺  Refresh", fg=C_ORANGE, bg=BG,
            activebackground=BG_CARD, relief="flat",
            font=("Segoe UI", 10, "bold"), bd=0, cursor="hand2",
            command=lambda: threading.Thread(
                target=self._fetch_usage, daemon=True
            ).start(),
        ).pack(side="right")

        self.panel = panel

    def _btn(self, parent, text, cmd):
        b = tk.Button(
            parent, text=text, command=cmd,
            fg=FG_DIM, bg=parent.cget("bg"),
            activeforeground=FG, activebackground=parent.cget("bg"),
            relief="flat", font=("Segoe UI", 9), bd=0, padx=6,
            cursor="hand2",
        )
        b.pack(side="left")
        return b

    def _make_card(self, parent, title: str) -> dict:
        PAD, R, BAR_H = 8, 10, 2
        Y_HDR, Y_BAR, Y_SUB, CARD_H = 7, 31, 42, 66

        cvs = tk.Canvas(parent, bg=BG, height=CARD_H, highlightthickness=0)
        cvs.pack(fill="x", pady=(0, 4))

        title_lbl = tk.Label(cvs, text=title, fg=FG_LABEL, bg=BG_CARD,
                             font=("Segoe UI", 7, "bold"))
        pct_lbl   = tk.Label(cvs, text="—", fg=FG, bg=BG_CARD,
                             font=("Segoe UI", 10, "bold"))
        bar       = tk.Canvas(cvs, height=BAR_H, bg=BG_CARD, highlightthickness=0)
        sub_lbl   = tk.Label(cvs, text="—", fg=FG_DIM, bg=BG_CARD,
                             font=("Segoe UI", 8))

        cvs.create_window(PAD, Y_HDR, window=title_lbl, anchor="nw")
        pct_win = cvs.create_window(0,   Y_HDR, window=pct_lbl,   anchor="ne")
        bar_win = cvs.create_window(PAD, Y_BAR, window=bar,        anchor="nw")
        cvs.create_window(PAD, Y_SUB, window=sub_lbl, anchor="nw")

        def _layout(*_):
            cw = cvs.winfo_width()
            if cw < 4:
                return
            cvs.delete("bg")
            pts = self._rrect_pts(0, 0, cw, CARD_H, R)
            cvs.create_polygon(pts, smooth=True, fill=BG_CARD, outline="", tags="bg")
            cvs.tag_lower("bg")
            cvs.coords(pct_win, cw - PAD, Y_HDR)
            cvs.itemconfig(bar_win, width=cw - 2 * PAD)

        cvs.bind("<Configure>", _layout)
        cvs.after(30, _layout)

        return {"pct": pct_lbl, "bar": bar, "sub": sub_lbl}

    def _on_panel_press(self, e):
        self._pdrag_x = e.x_root - self.panel.winfo_x()
        self._pdrag_y = e.y_root - self.panel.winfo_y()

    def _on_panel_drag(self, e):
        self.panel.geometry(
            f"+{e.x_root - self._pdrag_x}+{e.y_root - self._pdrag_y}"
        )

    def _minimize_panel(self):
        self.panel.withdraw()
        self.pill.deiconify()

    def _show_pill(self):
        self.panel.withdraw()
        self.pill.deiconify()

    def _toggle_panel(self):
        if self.panel.winfo_viewable():
            self.panel.withdraw()
            self.pill.deiconify()
        else:
            px = self.pill.winfo_x()
            py = self.pill.winfo_y()
            self.panel.update_idletasks()
            pw = 300
            ph = self.panel.winfo_reqheight()
            self.panel.geometry(f"{pw}x{ph}+{px}+{py - ph - 4}")
            self.panel.deiconify()
            self.panel.lift()
            self.pill.withdraw()
            self.panel.after(100, self._round_panel_corners)
            self.panel.after(80,  self._update_panel_cards)

    def _round_panel_corners(self):
        import ctypes
        inner   = self.panel.winfo_id()
        wrapper = ctypes.windll.user32.GetAncestor(inner, 2) or inner
        dwm = ctypes.windll.dwmapi
        DWMWA_WINDOW_CORNER_PREFERENCE = 33
        DWMWA_BORDER_COLOR             = 34
        DWMWCP_ROUND                   = 2
        DWMWA_COLOR_NONE               = 0xFFFFFFFE
        dwm.DwmSetWindowAttribute(wrapper, DWMWA_WINDOW_CORNER_PREFERENCE,
                                  ctypes.byref(ctypes.c_uint(DWMWCP_ROUND)),
                                  ctypes.sizeof(ctypes.c_uint))
        dwm.DwmSetWindowAttribute(wrapper, DWMWA_BORDER_COLOR,
                                  ctypes.byref(ctypes.c_uint(DWMWA_COLOR_NONE)),
                                  ctypes.sizeof(ctypes.c_uint))

    # ── UI Refresh ────────────────────────────────────────────────────────────

    def _refresh_ui(self):
        self._update_pill()
        self._update_panel_cards()
        self._update_tray()

    def _update_panel_cards(self):
        def fill(key, resets_prefix="Resets in"):
            data  = self.usage.get(key) or {}
            pct   = float(data.get("utilization") or 0)
            iso   = data.get("resets_at", "")
            color = pct_color(pct)
            card  = self._cards[key]

            card["pct"].config(text=f"{pct:.0f}%", fg=color)
            self._draw_bar(card["bar"], pct, color)

            if iso:
                until = self._time_until(iso)
                local = self._local_time(iso)
                card["sub"].config(text=f"{resets_prefix} {until}  ·  {local}")
            elif pct == 0:
                card["sub"].config(text="No usage yet")
            else:
                card["sub"].config(text="—")

        fill("five_hour")
        fill("seven_day", resets_prefix="Resets")
        fill("seven_day_omelette")

        ex      = self.usage.get("extra_usage") or {}
        enabled = ex.get("is_enabled", False)
        used    = ex.get("used_credits")
        limit   = ex.get("monthly_limit")
        cur     = ex.get("currency") or "$"
        card    = self._cards["extra_usage"]
        if enabled and used is not None and limit:
            pct   = min(100.0, (used / limit * 100) if limit > 0 else 0)
            color = pct_color(pct)
            card["pct"].config(text=f"{cur}{used:.2f}", fg=color)
            self._draw_bar(card["bar"], pct, color)
            card["sub"].config(text=f"of {cur}{limit:.2f} monthly limit")
        elif enabled:
            card["pct"].config(text="On", fg=C_GREEN)
            self._draw_bar(card["bar"], 0, C_GREEN)
            card["sub"].config(text="No usage data")
        else:
            card["pct"].config(text="Off", fg=FG_DIM)
            self._draw_bar(card["bar"], 0, BG_BAR)
            card["sub"].config(text="Not enabled")

        if self.last_updated:
            ts = self.last_updated.strftime("%H:%M:%S")
            self._status_lbl.config(text=f"Updated {ts}")
            self._show_setup_btn(False)

    def _set_status(self, msg: str):
        self._status_lbl.config(text=msg)
        if hasattr(self, "_pill_text_id"):
            self._pill_canvas.itemconfig(self._pill_text_id, text=msg[:22])
        needs_setup = "Setup" in msg or "expired" in msg
        self._show_setup_btn(needs_setup)

    # ── System Tray ───────────────────────────────────────────────────────────

    def _make_tray_img(self, pct: float = 0) -> Image.Image:
        size = 64
        img  = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Background ring
        draw.ellipse([6, 6, size - 6, size - 6],
                     outline=(55, 55, 55, 220), width=7)

        # Colored progress arc
        if pct > 0:
            h = pct_color(pct).lstrip("#")
            r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
            end = -90 + (360 * pct / 100)
            draw.arc([6, 6, size - 6, size - 6],
                     start=-90, end=end,
                     fill=(r, g, b, 255), width=7)

        # Percentage label in center
        draw.text(
            (size // 2, size // 2),
            f"{pct:.0f}",
            fill=(220, 220, 220, 255),
            anchor="mm",
        )
        return img

    def _tray_left_click(self, icon, item):
        """Left-click on tray icon: show widget if hidden, hide if visible."""
        self.root.after(0, self._tray_toggle)

    def _tray_toggle(self):
        if self.pill.winfo_viewable() or self.panel.winfo_viewable():
            self.pill.withdraw()
            self.panel.withdraw()
        else:
            self._show_pill()

    def _run_tray(self):
        menu = pystray.Menu(
            pystray.MenuItem(
                "Show / Hide Widget",
                self._tray_left_click,
                default=True,
            ),
            pystray.MenuItem(
                "Open Detailed View",
                lambda icon, item: self.root.after(0, self._toggle_panel),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Uninstall",
                lambda icon, item: self.root.after(0, self._uninstall),
            ),
            pystray.MenuItem(
                "Exit",
                lambda icon, item: self.root.after(0, self._quit),
            ),
        )
        self._tray = pystray.Icon(
            "claude_tracker",
            self._make_tray_img(0),
            "Claude Usage Tracker",
            menu,
        )
        self._tray.run()

    def _update_tray(self):
        if not hasattr(self, "_tray"):
            return
        fh  = self.usage.get("five_hour") or {}
        pct = float(fh.get("utilization") or 0)
        self._tray.icon  = self._make_tray_img(pct)
        self._tray.title = f"Claude: {pct:.0f}% used this session"

    # ── Setup Dialog ──────────────────────────────────────────────────────────

    def _show_setup_dialog(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("Claude Usage Tracker — Connect Account")
        dlg.configure(bg=BG)
        dlg.resizable(False, False)
        dlg.wm_attributes("-topmost", True)
        dlg.geometry("430x310")

        pad = dict(padx=16, pady=4)

        tk.Label(dlg, text="Connect to Claude.ai", fg=FG, bg=BG,
                 font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=16, pady=(14, 2))

        hint_var = tk.StringVar(value="Step 1 — click Auto-Detect to try reading from your browser.")
        hint_lbl = tk.Label(dlg, textvariable=hint_var, fg=FG_DIM, bg=BG,
                             font=("Segoe UI", 8), wraplength=400, justify="left")
        hint_lbl.pack(anchor="w", padx=16, pady=(0, 8))

        def try_auto():
            hint_var.set("Scanning browsers…")
            dlg.update()
            jar = self._read_browser_cookies()
            if jar is not None:
                self.session.cookies = jar
                self.auth_ok = True
                hint_var.set("✓ Connected automatically!")
                dlg.after(1200, dlg.destroy)
                threading.Thread(target=self._fetch_usage, daemon=True).start()
            else:
                hint_var.set(
                    "Auto-detect failed (Chrome 127+ limitation). "
                    "Use Firefox or Edge for automatic mode, or paste your credentials below."
                )

        tk.Button(dlg, text="⟳  Auto-Detect from Browser", command=try_auto,
                  bg=BG_CARD, fg=FG, activebackground="#3a3a3a",
                  relief="flat", font=("Segoe UI", 9),
                  padx=10, pady=4, cursor="hand2").pack(padx=16, anchor="w", pady=(0, 12))

        tk.Label(dlg, text="— or enter manually —", fg=FG_DIM, bg=BG,
                 font=("Segoe UI", 8)).pack()

        tk.Label(dlg, text="Organization ID  (Settings → Account, or lastActiveOrg cookie)",
                 fg=FG_LABEL, bg=BG, font=("Segoe UI", 8)).pack(anchor="w", **pad)
        org_var = tk.StringVar(value=self.config.get("org_id", ""))
        tk.Entry(dlg, textvariable=org_var, bg=BG_CARD, fg=FG, insertbackground=FG,
                 relief="flat", font=("Segoe UI", 9), width=54).pack(padx=16, pady=(0, 6))

        tk.Label(dlg, text="Session Key  (DevTools → Application → Cookies → sessionKey)",
                 fg=FG_LABEL, bg=BG, font=("Segoe UI", 8)).pack(anchor="w", **pad)
        key_var = tk.StringVar(value=self.config.get("session_key", ""))
        tk.Entry(dlg, textvariable=key_var, bg=BG_CARD, fg=FG, insertbackground=FG,
                 relief="flat", font=("Segoe UI", 9), width=54, show="*").pack(padx=16, pady=(0, 10))

        def save():
            org = org_var.get().strip()
            key = key_var.get().strip()
            if not org or not key:
                hint_var.set("Both fields are required for manual setup.")
                return
            self.org_id = org
            self.config["org_id"] = org
            self.config["session_key"] = key
            self.session.cookies.set("sessionKey", key, domain=".claude.ai")
            self.auth_ok = True
            self._save_config()
            dlg.destroy()
            threading.Thread(target=self._fetch_usage, daemon=True).start()

        tk.Button(dlg, text="Save & Connect", command=save,
                  bg=C_GREEN, fg="#000", activebackground="#22c55e",
                  relief="flat", font=("Segoe UI", 9, "bold"),
                  padx=12, pady=4, cursor="hand2").pack(pady=2)

    # ── Context Menu / Quit ───────────────────────────────────────────────────

    def _show_ctx_menu(self, e):
        m = tk.Menu(self.root, tearoff=0, bg=BG_CARD, fg=FG,
                    font=("Segoe UI", 9), relief="flat",
                    activebackground="#3a3a3a", activeforeground=FG)
        m.add_command(label="Toggle Details",  command=self._toggle_panel)
        m.add_separator()
        m.add_command(label="Exit",            command=self._quit)
        m.post(e.x_root, e.y_root)

    def _uninstall(self):
        import winreg, shutil, subprocess
        self._remove_startup()
        for browser_key in [
            r"Software\Google\Chrome\NativeMessagingHosts",
            r"Software\Microsoft\Edge\NativeMessagingHosts",
        ]:
            try:
                k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, browser_key, 0, winreg.KEY_SET_VALUE)
                winreg.DeleteKey(k, "com.claude.tracker")
                winreg.CloseKey(k)
            except Exception:
                pass
        for lnk_dir in [
            Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Desktop",
            Path(os.environ.get("APPDATA", str(Path.home()))) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
        ]:
            try:
                (lnk_dir / "Claude Usage Tracker.lnk").unlink(missing_ok=True)
            except Exception:
                pass
        try:
            bat = Path(os.environ.get("TEMP", str(Path.home()))) / "claude_uninstall.bat"
            bat.write_text(
                "@echo off\r\n"
                "timeout /t 2 /nobreak >nul\r\n"
                f'rmdir /s /q "{INSTALL_DIR}"\r\n'
                f'rmdir /s /q "{APPDATA_DIR}"\r\n'
                'del "%~f0"\r\n'
            )
            import ctypes
            ctypes.windll.shell32.ShellExecuteW(
                None, "runas", "cmd", f'/c "{bat}"', None, 0
            )
        except Exception as exc:
            print(f"[Uninstall] {exc}", flush=True)
        self._quit()

    def _quit(self):
        if hasattr(self, "_tray"):
            self._tray.stop()
        self.root.quit()


# ── Entry Point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    _self_install()
    ClaudeTracker()
