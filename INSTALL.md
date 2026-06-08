# Dan v2.0 Installation Guide

## Prerequisites

- Python 3.9 or higher
- pip (Python package installer)
- An API key from one of the supported providers

---

## Step-by-Step Installation

### 1. Extract the Files

Unzip the `dan_complete` folder to your desired location.

### 2. Install Python Dependencies

Open a terminal/command prompt in the `dan_complete` directory and run:

```bash
pip install -r requirements.txt
```

**Note**: This will install ~30MB of packages including:
- CustomTkinter (GUI framework)
- Anthropic SDK (for Claude)
- httpx, aiofiles (networking)
- Optional: OpenAI SDK, image processing libraries

### 3. Set Up Your API Key

Choose ONE of the following providers:

#### Option A: Anthropic (Claude) - RECOMMENDED
```bash
# Linux/macOS
export ANTHROPIC_API_KEY="<anthropic-api-key>"

# Windows Command Prompt
set ANTHROPIC_API_KEY=<anthropic-api-key>

# Windows PowerShell
$env:ANTHROPIC_API_KEY="<anthropic-api-key>"
```

Get your key at: https://console.anthropic.com/

#### Option B: OpenAI (GPT)
```bash
# Linux/macOS
export OPENAI_API_KEY="<openai-api-key>"

# Windows Command Prompt
set OPENAI_API_KEY=<openai-api-key>

# Windows PowerShell
$env:OPENAI_API_KEY="<openai-api-key>"
```

Get your key at: https://platform.openai.com/

#### Option C: Venice (Uncensored Models)
```bash
# Linux/macOS
export VENICE_API_KEY="..."

# Windows Command Prompt
set VENICE_API_KEY=...

# Windows PowerShell
$env:VENICE_API_KEY="..."
```

Get your key at: https://venice.ai/

#### Option D: Ollama (Local/Free)
```bash
# First install Ollama from: https://ollama.com/
# Then pull a model:
ollama pull llama3.1

# Start the server:
ollama serve

# No API key needed!
```

### 4. Launch Dan

#### GUI Mode (Recommended)

**Linux/macOS:**
```bash
./run_gui.sh
```

**Windows:**
```
run_gui.bat
```

Or directly:
```bash
python Dan.py --doctor --target gui
python dan_gui_modern.py
```

#### CLI Mode (Classic REPL)

```bash
python Dan.py --doctor --target cli
python Dan.py
```

---

## First Run

When you first launch Dan, you should see:

1. **GUI Mode**: The supported Claude-inspired Dan desktop shell in dark mode,
   with a Settings option and quick toggle for light mode
2. **CLI Mode**: A banner showing your provider, model, and tool count

Try asking:
- "List the files in this directory"
- "What tools do you have?"
- "Create a simple Python script"

---

## Troubleshooting

### "ModuleNotFoundError: No module named 'customtkinter'"

Run: `pip install customtkinter`

### "Provider initialization failed"

Check that:
1. Your API key is set correctly
2. The environment variable name matches your provider
3. Your API key is valid (not expired or revoked)
4. The provider SDK is installed for the provider you selected

### "tkinter not found" (Linux only)

Install tkinter:
```bash
# Ubuntu/Debian
sudo apt-get install python3-tk

# Fedora
sudo dnf install python3-tkinter

# Arch
sudo pacman -S tk
```

### GUI window is blank or frozen

Try:
1. Restart the application
2. Check terminal for error messages
3. Verify your Python version: `python --version` (must be 3.9+)

### Can't install dependencies on Windows

Make sure you're running Command Prompt or PowerShell as Administrator.

### Quick environment audit

Run:

```bash
py -3 Dan.py --doctor --target cli
```

This reports true startup blockers separately from development advisories before launch.

### Full repo health audit

Run:

```bash
py -3 scripts/repo_health.py
```

This combines the environment audit with `compileall`, `pytest` when available, and `ruff` when available.

---

## Optional Dependencies

For advanced features, you can install:

```bash
# Image processing tools
pip install Pillow opencv-python pytesseract easyocr

# Machine learning tools
pip install pandas scikit-learn joblib

# Additional LLM providers
pip install openai  # For GPT models
```

---

## Windows Portable Build

Dan now has a repeatable PyInstaller packaging path for Windows.

Install packaging dependencies:

```powershell
python -m pip install -r requirements-packaging.txt
```

Build the supported desktop shell:

```powershell
python scripts/build_windows.py --target gui
```

Build both desktop and CLI artifacts:

```powershell
python scripts/build_windows.py --target all
```

Print the exact PyInstaller commands without building:

```powershell
python scripts/build_windows.py --target all --dry-run
```

Output layout:

- `dist/windows/Dan/` for the supported GUI build
- `dist/windows/DanCLI/` for the CLI build

Notes:

- The current release path is portable `onedir`, not a Windows installer.
- `--with-vision` and `--with-ml` are opt-in because those bundles depend on optional packages.
- The default core build excludes heavyweight optional ML and vision stacks unless you opt into them.
- Build from the repository root on Windows with the runtime dependencies already installed.
- The CI pipeline now performs a real Windows GUI package build and verifies the packaged output layout.
- The CI pipeline also builds the CLI package and runs a packaged `--doctor --target cli` smoke test.

---

## Updating

To update Dan to a newer version:

1. Download the new version
2. Extract to a new folder
3. Copy your `.dan/` directory (if you have custom actions)
4. Run `pip install -r requirements.txt` to update dependencies

---

## Uninstalling

To completely remove Dan:

```bash
# Remove the folder
rm -rf dan_complete

# Optionally remove Python packages
pip uninstall customtkinter anthropic httpx aiofiles
```

---

## Getting Help

- Check the main [README.md](README.md) for usage examples
- Report bugs at: [GitHub Issues]
- See troubleshooting section above

---

**Ready to go? Run `python dan_gui_modern.py` and start coding!**
