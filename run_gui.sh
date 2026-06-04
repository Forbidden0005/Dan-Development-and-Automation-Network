#!/bin/bash
# Launch Dan GUI on Unix/Linux/macOS

echo "Starting Dan v2.0 modern GUI..."
python3 Dan.py --doctor --target gui --provider "${DAN_PROVIDER:-ollama}" || exit 1
python3 dan_gui_modern.py
