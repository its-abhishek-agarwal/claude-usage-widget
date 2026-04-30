"""
Registers the Chrome / Edge native messaging host so the browser extension
can launch the widget automatically.

Called by run.bat on first install. Safe to re-run at any time.
"""
import json, sys, winreg
from pathlib import Path

HOST_NAME    = "com.claude.tracker"
WIDGET_DIR   = Path(__file__).parent.resolve()
BAT_PATH     = WIDGET_DIR / "native_host.bat"
MANIFEST_PATH = WIDGET_DIR / "com.claude.tracker.json"

# Placeholder — updated automatically when the extension first connects.
# For a Chrome Web Store extension, replace with the stable ID.
EXTENSION_ID = "EXTENSION_ID_PLACEHOLDER"

def read_saved_id() -> str:
    id_file = WIDGET_DIR / ".extension_id"
    if id_file.exists():
        return id_file.read_text().strip()
    return EXTENSION_ID


def write_manifest(ext_id: str):
    manifest = {
        "name":        HOST_NAME,
        "description": "Claude Usage Tracker native host",
        "path":        str(BAT_PATH),
        "type":        "stdio",
        "allowed_origins": [f"chrome-extension://{ext_id}/"],
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2))
    print(f"[Setup] Manifest written: {MANIFEST_PATH}", flush=True)


def register_chrome(manifest_path: str):
    for browser_key in [
        r"Software\Google\Chrome\NativeMessagingHosts",
        r"Software\Microsoft\Edge\NativeMessagingHosts",
    ]:
        try:
            key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, f"{browser_key}\\{HOST_NAME}")
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, manifest_path)
            winreg.CloseKey(key)
            print(f"[Setup] Registered in {browser_key}", flush=True)
        except Exception as exc:
            print(f"[Setup] Could not register {browser_key}: {exc}", flush=True)


if __name__ == "__main__":
    ext_id = read_saved_id()
    write_manifest(ext_id)
    register_chrome(str(MANIFEST_PATH))
    print("[Setup] Native messaging host registered.", flush=True)
