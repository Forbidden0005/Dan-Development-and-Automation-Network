# Dan Release Process

This document is the operator path for cutting a Dan release on Windows.

Dan is only ready to ship when the code, packaging outputs, and release prerequisites are all verified. Do not infer readiness from a passing CI badge alone.

## Version Rule

Dan uses semantic versioning: `MAJOR.MINOR.PATCH`.

- `MAJOR`: breaking CLI, config, or tool API change
- `MINOR`: backward-compatible feature work
- `PATCH`: bug fix, documentation fix, or internal refactor with no intended behavior change

Current version: `2.5.1`

## Version Sources Of Truth

The release version must match in all three files below before any artifact is built:

| File | Expected field |
| --- | --- |
| `config.py` | `APP_VERSION = "2.5.1"` |
| `pyproject.toml` | `version = "2.5.1"` |
| `installer/Dan.iss` | `#define MyAppVersion "2.5.1"` |

Why all three matter:

- `config.py` drives runtime version display
- `pyproject.toml` drives packaging/tooling metadata
- `installer/Dan.iss` drives installer metadata and output naming

`python scripts/build_windows.py --target gui --dry-run` enforces this sync before any real build work starts.

## Pre-Release Verification

Run these from the repository root on a real Windows machine:

```powershell
python -m pytest -q
python -m ruff check .
python Dan.py --doctor --target cli
python Dan.py --doctor --target gui
python scripts/repo_health.py
python scripts/build_windows.py --target gui --dry-run
python scripts/release_readiness.py
```

Do not proceed if any of those fail.

## Version Bump

1. Update `config.py`.
2. Update `pyproject.toml`.
3. Update `installer/Dan.iss`.
4. Commit the bump.
5. Tag and push the release.

Example:

```powershell
git add config.py pyproject.toml installer/Dan.iss
git commit -m "chore: bump version to 2.5.2"
git tag -a "v2.5.2" -m "Dan v2.5.2"
git push origin main --tags
```

## Build Portable Windows Artifacts

Install packaging dependencies first:

```powershell
python -m pip install -r requirements-packaging.txt
```

Build both portable bundles:

```powershell
python scripts/build_windows.py --target all
```

Verify them:

```powershell
python scripts/verify_windows_build.py --target gui
python scripts/verify_windows_build.py --target cli
python scripts/smoke_windows_cli.py
```

Outputs:

- `dist/windows/Dan/` for the GUI bundle
- `dist/windows/DanCLI/` for the CLI bundle

## Build The Installer

The repository ships `installer/Dan.iss` for a per-user Windows installer.

Prerequisites:

- Inno Setup 6.x installed from [jrsoftware.org/isdl.php](https://jrsoftware.org/isdl.php)
- GUI portable bundle already built, unless you use the combined command below

Build bundle plus installer:

```powershell
python scripts/build_windows.py --target gui --installer
```

Build installer only from an existing GUI bundle:

```powershell
python scripts/build_windows.py --installer-only
```

Output:

- `dist/installer/Dan-<version>-setup.exe`

## Signed Release Prerequisites

Dan can sign the GUI exe, CLI exe, and installer, but the machine must have both the signing tool and certificate material.

Local requirements:

- `signtool.exe` available from the Windows SDK, or supplied explicitly with `--sign-tool`
- a real `.pfx` certificate file
- the certificate password

Session-scoped environment setup:

```powershell
$env:DAN_SIGN_PFX = "C:\secure\dan-signing.pfx"
$env:DAN_SIGN_PFX_PASSWORD = "<pfx-password>"
$env:DAN_SIGN_TIMESTAMP_URL = "http://timestamp.digicert.com"
```

Optional explicit tool override:

```powershell
python scripts/build_windows.py --target gui --sign --sign-tool "C:\path\to\signtool.exe"
```

## Local Release Gate

`python scripts/release_readiness.py` is the authoritative local ship gate.

It checks:

- version synchronization
- packaged GUI presence
- packaged CLI presence
- packaged CLI smoke health
- local `ISCC.exe` availability
- expected installer artifact presence
- release checksum and manifest artifact presence
- local `signtool.exe` availability
- local signing certificate configuration

If it reports blockers, clear them before claiming local ship readiness.

## GitHub Release Workflow

Pushing a tag that matches `v*.*.*` triggers `.github/workflows/release.yml`.

That workflow:

1. verifies release version sync
2. builds the GUI bundle
3. builds the CLI bundle
4. verifies both package shapes
5. runs the packaged CLI smoke test
6. installs Inno Setup and builds the installer
7. generates `dist/release/SHA256SUMS.txt` and `dist/release/release-manifest.json`
8. verifies the pushed tag version matches the synchronized repo version
9. creates a GitHub Release and uploads the installer plus release integrity artifacts

If these repository secrets exist, the workflow also signs artifacts before publishing:

- `DAN_SIGN_PFX_BASE64`
- `DAN_SIGN_PFX_PASSWORD`

PowerShell helper to generate the base64 secret from a local `.pfx`:

```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes("C:\secure\dan-signing.pfx"))
```

Without those secrets, the release remains unsigned.

## Release Artifact Checklist

Before distributing a release:

- [ ] `python -m pytest -q` passes on the build machine
- [ ] `python -m ruff check .` passes
- [ ] `python scripts/verify_windows_build.py --target gui` passes
- [ ] `python scripts/verify_windows_build.py --target cli` passes
- [ ] `python scripts/smoke_windows_cli.py` passes
- [ ] `python scripts/release_artifacts.py` succeeds
- [ ] `python scripts/release_readiness.py` reports zero blocking items
- [ ] `config.py`, `pyproject.toml`, and `installer/Dan.iss` match on version
- [ ] the release tag `vX.Y.Z` is pushed
- [ ] `ROADMAP.md` reflects the current release state

## Current Known External Blockers

As of `2026-06-16`, the verified local blockers on this workstation are:

- signing certificate material is not configured locally

Verified local release evidence on this workstation now includes:

- Inno Setup 6.7.3 installed under `%LOCALAPPDATA%\Programs\Inno Setup 6\`
- `signtool.exe` detected from the Windows SDK
- `python scripts/build_windows.py --installer-only` successfully producing `dist/installer/Dan-2.5.1-setup.exe`
- `python scripts/release_artifacts.py` generating `dist/release/SHA256SUMS.txt` and `dist/release/release-manifest.json`

The repo-side release path is wired. The remaining missing input is the real signing certificate material.
