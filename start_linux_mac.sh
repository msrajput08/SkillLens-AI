#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
source .venv/bin/activate
python -m pip install -r requirements.txt
printf '\n[SkillLens] Open http://127.0.0.1:8000\n'
if [ -f .env ]; then
  exec python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --env-file .env
else
  exec python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
fi
