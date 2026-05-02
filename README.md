# Claude Usage Tracker

A floating Windows desktop widget that shows your Claude.ai usage limits in real time — no need to open the browser.

## What it does

- Floating pill widget in the corner of your screen — progress bar + % + time until reset
- Click to expand: shows all 4 usage categories (Current Session, This Week, Claude Design, Extra Usage)
- System tray icon with live progress arc
- Starts automatically with Windows
- Chrome extension syncs your session automatically whenever you visit claude.ai

## Installation

1. **Install the Chrome extension** — [Chrome Web Store](https://chromewebstore.google.com/detail/claude-usage-tracker/afmgmecdicfghaeoadoklpddoocpeenj)
2. **Download and run `ClaudeTracker.exe`** — [Download](https://claude-usage-limit-tracker.vercel.app/#download)
   - Windows may show a SmartScreen warning → click **More info** → **Run anyway**
   - The app installs to `C:\Program Files\ClaudeTracker\` and appears in Start Menu search

That's it. The widget will appear in your system tray and the pill will show your usage.

## Requirements

- Windows 10 / 11
- Chrome or Edge browser
- A Claude.ai account

## Building from source

```bash
pip install -r requirements.txt
python make_icons.py
python -m PyInstaller ClaudeTracker.spec --clean --noconfirm
```

The compiled `.exe` will be in `dist/`.

## Project structure

```
claude_tracker.py   — main widget app
extension/          — Chrome extension
setup_host.py       — registers native messaging host
run.bat             — installer/launcher for Python source users
build.bat           — builds the .exe via PyInstaller
make_icons.py       — generates icons (uses claude_logo_source.png if present)
requirements.txt    — Python dependencies
```

## Privacy

The widget reads your Claude.ai session cookies locally and calls the Claude.ai API directly from your machine. No data is sent to any third-party server.

---

*Not affiliated with Anthropic.*
