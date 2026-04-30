"""
Chrome Native Messaging host.

Chrome launches this script (via native_host.bat) when the extension calls
connectNative(). It:
  1. Starts the widget if it is not already running.
  2. Forwards cookie messages from the extension to the widget's HTTP server.
  3. Stays alive so Chrome keeps the channel open.
"""
import sys, struct, json, subprocess, time
from pathlib import Path


def _read() -> dict | None:
    raw = sys.stdin.buffer.read(4)
    if len(raw) < 4:
        return None
    length = struct.unpack("=I", raw)[0]
    return json.loads(sys.stdin.buffer.read(length).decode("utf-8"))


def _send(data: dict):
    payload = json.dumps(data).encode("utf-8")
    sys.stdout.buffer.write(struct.pack("=I", len(payload)) + payload)
    sys.stdout.buffer.flush()


def _widget_up() -> bool:
    try:
        import requests
        requests.get("http://127.0.0.1:9871/status", timeout=1)
        return True
    except Exception:
        return False


def _launch_widget():
    script  = Path(__file__).parent / "claude_tracker.py"
    pythonw = Path(sys.executable).parent / "pythonw.exe"
    exe     = str(pythonw) if pythonw.exists() else sys.executable
    subprocess.Popen(
        [exe, str(script)],
        creationflags=0x08000000,  # CREATE_NO_WINDOW
        close_fds=True,
    )


# ── Main ──────────────────────────────────────────────────────────────────────

if not _widget_up():
    _launch_widget()
    for _ in range(10):   # wait up to 5 s for widget HTTP server to start
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
