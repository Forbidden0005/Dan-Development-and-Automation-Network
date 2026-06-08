# Dan v2.0 Installation Guide

## Prerequisites

- **Windows 10 (build 19041+) or Windows 11** — Dan is a Windows-first product.
- **Python 3.11 or higher** — required for `tomllib` (stdlib) and `X | Y` union type hints.
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

## Data Directories

Dan stores persistent state in two locations:

### User-global data — `%APPDATA%\Dan\`

```
C:\Users\<name>\AppData\Roaming\Dan\
```

This directory holds state that persists across installs and is not project-specific:
- **Knowledge** — ingested documents and embeddings
- **Sessions** — saved chat history
- **Auth cache** — provider credential metadata (not API keys)

Dan creates this directory automatically on first run. To find it quickly:

```powershell
explorer %APPDATA%\Dan
```

### Project-local data — `.dan\`

```
<your-project-root>\.dan\
```

This directory holds per-repository state:
- **Project index** — file structure and symbol cache for the open project
- **Auth cache** — per-project credential overrides
- **Local knowledge** — project-specific ingested docs

`.dan\` is listed in `.gitignore` and is never committed. It is recreated automatically if deleted.

### Logs

Dan logs to stderr by default. To redirect to a file:

```powershell
python Dan.py 2> dan.log
```

No log files are written automatically. Startup errors appear in the terminal before the GUI window opens.

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
3. Verify your Python version: `python --version` (must be 3.11+)

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

- `--with-vision` and `--with-ml` are opt-in because those bundles depend on optional packages.
- The default core build excludes heavyweight optional ML and vision stacks unless you opt into them.
- Build from the repository root on Windows with the runtime dependencies already installed.
- The CI pipeline now performs a real Windows GUI package build and verifies the packaged output layout.
- The CI pipeline also builds the CLI package and runs a packaged `--doctor --target cli` smoke test.

---

## Windows Installer Build (Inno Setup)

The repository ships an Inno Setup script at `installer/Dan.iss` that wraps the
PyInstaller portable bundle into a proper Windows installer `.exe`.

### Prerequisites

1. **Build the portable bundle first** (see above).
2. **Install Inno Setup 6.x** — download from <https://jrsoftware.org/isdl.php>.
   The build script auto-detects it at the default install location.

### Build installer + bundle in one step

```powershell
python scripts/build_windows.py --target gui --installer
```

### Build the installer from an existing bundle

```powershell
python scripts/build_windows.py --installer-only
```

### Output

```
dist/installer/Dan-<version>-setup.exe
```

### What the installer does

- Installs to `%LOCALAPPDATA%\Dan\` by default (no admin rights required).
- Creates a Start Menu group with a shortcut and an uninstaller entry.
- Offers an optional Desktop shortcut.
- Offers optional PATH registration for the CLI companion (`DanCLI.exe`).
- Upgrades gracefully — the stable `AppId` GUID in `Dan.iss` lets Windows
  detect previous installs and offer an upgrade rather than a parallel install.

### Icon

The installer references `assets\dan_icon.ico`.  If this file does not exist,
comment out the `SetupIconFile` line in `installer\Dan.iss` before compiling.

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
