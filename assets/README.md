# assets/

This directory holds static assets for the Dan desktop application and installer.

## Required: `dan_icon.ico`

The Windows installer (`installer/Dan.iss`) and the packaged GUI bundle both expect an application icon at:

```
assets/dan_icon.ico
```

The `SetupIconFile` line in `Dan.iss` is currently commented out and will use the Inno Setup default icon until this file is created. Uncomment it once the icon is in place:

```ini
; installer/Dan.iss — line ~80
SetupIconFile=..\assets\dan_icon.ico
```

### Icon requirements

| Property | Value |
|---|---|
| Format | `.ico` (Windows icon container) |
| Recommended sizes | 16×16, 32×32, 48×48, 256×256 (all embedded in a single `.ico`) |
| Color depth | 32-bit RGBA |
| Source | Create from a PNG with ImageMagick: `magick convert icon.png -define icon:auto-resize=256,48,32,16 dan_icon.ico` |

Once `dan_icon.ico` is present, also pass it to PyInstaller via `--icon assets/dan_icon.ico` in `scripts/build_windows.py` (the `--icon` flag is already accepted by the build script; the path just needs to exist).
