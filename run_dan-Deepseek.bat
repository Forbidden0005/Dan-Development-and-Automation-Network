@echo off
set "DAN_PROVIDER=ollama"
set "DAN_MODEL=deepseek-coder-v2:latest"
set OLLAMA_NUM_CTX=32768

echo Launching Dan terminal with provider %DAN_PROVIDER% and model %DAN_MODEL%
echo Set any hosted-provider API keys in your user environment before launch.

python Dan.py
