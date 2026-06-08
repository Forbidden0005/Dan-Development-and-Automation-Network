@echo off
setlocal

set "DAN_PROVIDER=ollama"
set "DAN_MODEL=qwen2.5-coder:7b"
set "OLLAMA_NUM_CTX=32768"

py dan_gui_modern.py

:end
endlocal
