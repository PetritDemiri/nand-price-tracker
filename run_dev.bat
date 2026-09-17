@echo off
REM Run from source without building - useful while you are editing the code.
setlocal
if not exist .venv python -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install -r requirements.txt --quiet
python run.py
