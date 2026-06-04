@echo off
setlocal

if not defined DAN_PROVIDER set "DAN_PROVIDER=ollama"
if not defined DAN_MODEL set "DAN_MODEL=qwen2.5-coder:7b"
if not defined OLLAMA_NUM_CTX set "OLLAMA_NUM_CTX=32768"

echo Launching Dan GUI with provider %DAN_PROVIDER% and model %DAN_MODEL%
echo.
echo Set API keys in your user environment before launching if you want hosted providers.
echo Example:
echo   setx ANTHROPIC_API_KEY_1 "your-key-here"
echo   setx OPENAI_API_KEY "your-key-here"
echo.

py Dan.py --doctor --target gui --provider %DAN_PROVIDER%
if errorlevel 1 goto end

py dan_gui_modern.py

:end
endlocal
pause
