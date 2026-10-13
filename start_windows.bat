@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo [SkillLens] Creating Python virtual environment...
    py -3 -m venv .venv
    if errorlevel 1 (
        echo Python 3.11+ required. Install Python and retry.
        pause
        exit /b 1
    )
)
call ".venv\Scripts\activate.bat"
echo [SkillLens] Installing application dependencies...
python -m pip install -r requirements.txt
if errorlevel 1 (pause & exit /b 1)
echo [SkillLens] Starting website at http://127.0.0.1:8000
if exist .env (
    python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --env-file .env
) else (
    python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
)
pause
