"""Launches claude_tracker.py as a detached, windowless background process."""
import subprocess, sys
from pathlib import Path

script  = Path(__file__).parent / "claude_tracker.py"
pythonw = Path(sys.executable).parent / "pythonw.exe"
exe     = str(pythonw) if pythonw.exists() else sys.executable

subprocess.Popen([exe, str(script)], creationflags=0x08000000)  # CREATE_NO_WINDOW
