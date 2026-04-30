@echo off
echo Installing PyInstaller...
pip install pyinstaller --quiet
echo.
echo Generating icons...
python make_icons.py
echo.
echo Building ClaudeTracker.exe...
python -m PyInstaller ClaudeTracker.spec --clean --noconfirm
echo.
if exist dist\ClaudeTracker.exe (
    echo SUCCESS: dist\ClaudeTracker.exe
) else (
    echo FAILED - check output above
)
pause
