# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['claude_tracker.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'browser_cookie3',
        'rookiepy',
        'pystray._win32',
        'PIL._imagingtk',
        'PIL.ImageTk',
        'requests',
        'winreg',
        'tkinter',
        'tkinter.ttk',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='ClaudeTracker',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    icon='icon.ico',
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
