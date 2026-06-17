# Dan Installation Guide

This guide covers the supported local setup path for Dan on Windows.

Dan is a local-first Windows development assistant. The supported desktop shell is `dan_gui_modern.py`. The CLI entry point is `Dan.py`.

## Requirements

- Windows 10 (build 19041+) or Windows 11
- Python 3.11+
- `pip`
- At least one provider configured:
  - Anthropic
  - OpenAI
  - Venice
  - Ollama

## Local Development Install

From the repository root:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
```

Optional extras:

```powershell
python -m pip install -r requirements-vision.txt
python -m pip install -r requirements-ml.txt
```

## Provider Configuration

Set environment variables in the current shell or a local `.env`.

Examples:

```powershell
$env:ANTHROPIC_API_KEY = "<anthropic-api-key>"
$env:OPENAI_API_KEY = "<openai-api-key>"
$env:VENICE_API_KEY = "<venice-api-key>"
$env:DAN_PROVIDER = "ollama"
$env:DAN_MODEL = "qwen2.5-coder:7b"
```

For Ollama:

```powershell
ollama pull qwen2.5-coder:7b
ollama serve
```

## Verify The Environment

Run these before you trust the local setup:

```powershell
python -m pytest -q
python -m ruff check .
python Dan.py --doctor --target cli
python Dan.py --doctor --target gui
python scripts/repo_health.py
```

## Run Dan

CLI:

```powershell
python Dan.py
```

GUI:

```powershell
python dan_gui_modern.py
```

## Data Locations

User-global state:

```text
%APPDATA%\Dan\
```

This holds persistent sessions, knowledge state, and auth metadata.

Project-local state:

```text
<repo>\.dan\
```

This holds per-project index and local project state.

## Windows Packaging

Install packaging dependencies:

```powershell
python -m pip install -r requirements-packaging.txt
```

Preview the packaging commands:

```powershell
python scripts/build_windows.py --target all --dry-run
```

Build the portable bundles:

```powershell
python scripts/build_windows.py --target all
python scripts/verify_windows_build.py --target gui
python scripts/verify_windows_build.py --target cli
python scripts/smoke_windows_cli.py
```

Outputs:

- `dist/windows/Dan/`
- `dist/windows/DanCLI/`

## Windows Installer

Dan also ships an Inno Setup installer path through `installer/Dan.iss`.

Prerequisites:

- Inno Setup 6.x installed from [jrsoftware.org/isdl.php](https://jrsoftware.org/isdl.php)
- GUI bundle available

Build it:

```powershell
python scripts/build_windows.py --target gui --installer
```

Or from an existing GUI bundle:

```powershell
python scripts/build_windows.py --installer-only
```

Output:

- `dist/installer/Dan-<version>-setup.exe`

## Signed Windows Builds

Signed artifacts require:

- `signtool.exe`
- a `.pfx` certificate
- the certificate password

Session example:

```powershell
$env:DAN_SIGN_PFX = "C:\secure\dan-signing.pfx"
$env:DAN_SIGN_PFX_PASSWORD = "<pfx-password>"
$env:DAN_SIGN_TIMESTAMP_URL = "http://timestamp.digicert.com"
```

Then build with signing enabled:

```powershell
python scripts/build_windows.py --target all --sign
```

If `signtool.exe` is not on `PATH`, pass it explicitly:

```powershell
python scripts/build_windows.py --target gui --sign --sign-tool "C:\path\to\signtool.exe"
```

## Local Ship Gate

Run the release gate before claiming the machine is ready to ship:

```powershell
python scripts/release_readiness.py
```

That script reports whether the workstation has:

- synchronized versions
- valid packaged outputs
- a passing packaged CLI smoke test
- Inno Setup
- `signtool.exe`
- signing certificate material

## Troubleshooting

Common checks:

```powershell
python --version
python Dan.py --doctor --target cli
python Dan.py --doctor --target gui
python scripts/repo_health.py
python scripts/release_readiness.py
```

Typical failure causes:

- missing provider API key
- Ollama not running for local model use
- missing `customtkinter` or other Python dependencies
- missing Inno Setup for installer compilation
- missing `signtool.exe` or `.pfx` material for signed releases
