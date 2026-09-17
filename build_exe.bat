@echo off
REM ---------------------------------------------------------------
REM  Builds dist\NANDTrack.exe - a single windowed Windows binary.
REM  Needs Python 3.10+ (64-bit) on PATH. Nothing else.
REM ---------------------------------------------------------------
setlocal

echo.
echo   NANDTrack - building a Windows executable
echo   -----------------------------------------
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo   Python was not found on your PATH.
    echo   Install it from python.org and tick "Add python.exe to PATH".
    pause
    exit /b 1
)

if not exist .venv (
    echo   [1/4] Creating a build environment...
    python -m venv .venv || goto :failed
) else (
    echo   [1/4] Reusing the existing .venv
)

call .venv\Scripts\activate.bat

echo   [2/4] Installing dependencies...
python -m pip install --upgrade pip --quiet || goto :failed
python -m pip install -r requirements.txt pyinstaller --quiet || goto :failed

echo   [3/4] Drawing the application icon...
python make_icon.py

echo   [4/4] Packaging (this takes a couple of minutes)...
pyinstaller nandtrack.spec --noconfirm --clean || goto :failed

echo.
echo   Done. Your app is at:  %CD%\dist\NANDTrack.exe
echo   Copy that one file anywhere - it carries everything it needs.
echo.
pause
exit /b 0

:failed
echo.
echo   The build stopped on an error. The lines above say where.
pause
exit /b 1
