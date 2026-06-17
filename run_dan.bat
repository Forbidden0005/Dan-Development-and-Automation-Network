@echo off
setlocal

set "DAN_PROVIDER=ollama"
set "DAN_MODEL=qwen2.5-coder:7b"
set "OLLAMA_NUM_CTX=32768"

if exist "%~dp0.venv\Scripts\python.exe" (
    set "PYTHON=%~dp0.venv\Scripts\python.exe"
) else (
    set "PYTHON=py"
)

%PYTHON% dan_gui_modern.py

:end
endlocal
