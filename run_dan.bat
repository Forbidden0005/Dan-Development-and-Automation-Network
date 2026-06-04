@echo off
setlocal

set "DAN_PROVIDER=ollama"
set "DAN_MODEL=qwen2.5-coder:7b"
set "OLLAMA_NUM_CTX=32768"

py Dan.py --doctor --target cli --provider %DAN_PROVIDER%
if errorlevel 1 goto end

py Dan.py

:end
endlocal
