@echo off
rem MV Agent web UI: http://127.0.0.1:8700  (set ANTHROPIC_API_KEY first, or paste the key in the page)
cd /d %~dp0
start "" http://127.0.0.1:8700
.venv\Scripts\python -m webagent
