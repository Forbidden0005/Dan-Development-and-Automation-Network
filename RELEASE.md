# Dan Release Process

This document defines the version scheme, where version numbers live, and the steps to cut a release.

---

## Version Scheme

Dan uses **Semantic Versioning** (`MAJOR.MINOR.PATCH`):

- **MAJOR** — breaking change to the CLI interface, config format, or tool API
- **MINOR** — new feature that is backward compatible (new tool family, new provider, new GUI capability)
- **PATCH** — bug fix, documentation fix, or internal refactor with no behavior change

Current version: **2.5.1**

Latest published release: **[v2.5.1](https://github.com/Forbidden0005/Dan-Development-and-Automation-Network/releases/tag/v2.5.1)** (2026-06-17) — first published release; portable GUI + CLI Windows bundles, built and smoke-tested by the automated release workflow. No installer/signed binaries yet.

---

## Single Source of Truth

The version string lives in **two places** that must stay synchronized:

| File | Location |
|---|---|
| `config.py` | `APP_VERSION = "2.5.1"` |
| `pyproject.toml` | `version = "2.5.1"` |

`config.py` is the runtime source — the GUI title bar, CLI banner, and `--version` flag all read from it. `pyproject.toml` is the packaging and tooling source. Keep them identical.

---

## Pre-Release Checklist

Before cutting any release, verify the repository is in a releasable state:

```powershell
# 1. Tests pass
python -m pytest -q

# 2. Lint passes
python -m ruff check .

# 3. Startup health passes (CLI)
python Dan.py --doctor --target cli

# 4. Startup health passes (GUI — verify on Windows)
python Dan.py --doctor --target gui

# 5. Repo health
python scripts/repo_health.py
```

All five must pass cleanly. Do not proceed if any check fails.

---

## Version Bump Steps

1. **Update `config.py`**

   ```python
   APP_VERSION = "X.Y.Z"
   ```

2. **Update `pyproject.toml`**

   ```toml
   version = "X.Y.Z"
   ```

3. **Commit the version bump**

   ```powershell
   git add config.py pyproject.toml
   git commit -m "chore: bump version to X.Y.Z"
   ```

4. **Tag the release**

   ```powershell
   git tag -a "vX.Y.Z" -m "Dan vX.Y.Z"
   git push origin main --tags
   ```

---

## Build The Windows Portable Artifacts

```powershell
# Install packaging dependencies (first time only)
python -m pip install -r requirements-packaging.txt

# Build GUI and CLI portable bundles
python scripts/build_windows.py --target all

# Verify the output shape
python scripts/verify_windows_build.py

# Run the packaged CLI smoke test
python scripts/smoke_windows_cli.py
```

Outputs land in:

```
dist/windows/Dan/       # Supported GUI build (onedir)
dist/windows/DanCLI/    # CLI build (onedir)
```

Both are portable — no installer required. Users unzip and run.

---

## Release Artifact Checklist

Before distributing a build:

- [ ] `python -m pytest -q` passes on the build machine
- [ ] `python -m ruff check .` passes
- [ ] `python scripts/verify_windows_build.py` passes
- [ ] `python scripts/smoke_windows_cli.py` passes (packaged CLI boots cleanly)
- [ ] `config.py` and `pyproject.toml` both show the release version
- [ ] Git tag `vX.Y.Z` is pushed to the remote
- [ ] `ROADMAP.md` reflects the release state

---

## Automated Release Workflow

Pushing a version tag publishes the portable Windows artifacts automatically:

```powershell
git tag -a "vX.Y.Z" -m "Dan vX.Y.Z"
git push origin main --tags
```

This triggers `.github/workflows/release.yml`, which:

1. Builds the portable GUI (`Dan`) and CLI (`DanCLI`) bundles via `scripts/build_windows.py`
2. Verifies each bundle's shape and runs the packaged CLI smoke test
3. Zips them as `Dan-<version>-windows-gui.zip` and `Dan-<version>-windows-cli.zip`
4. Creates a GitHub Release (auto-generated notes) and uploads both archives as downloadable assets

The `prerelease` flag is set automatically when the tag contains a hyphen (e.g. `v2.6.0-rc1`).

---

## What Is Not Yet Done

- **No Windows installer on this branch** — the release path here is portable `onedir` only. An Inno Setup installer exists on the `codex/claude-inspired-ui` branch but has not been merged to this line; once merged, `release.yml` extends to upload the installer `.exe`.
- **No signed executables** — the portable builds are unsigned. Windows SmartScreen may warn on first launch.
