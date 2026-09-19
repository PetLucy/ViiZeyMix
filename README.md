# VoiceMix v0.1

A first-pass VoiceMeeter-style mixer UI for Linux, built around:

- **PySide6** for the GUI
- **C + libpipewire** for native PipeWire discovery
- **wpctl** for simple volume/mute control in v0.1

This release is intentionally a prototype. The goal is to establish the UI and
interaction model before we build the full routing engine.

## What works

- Detects PipeWire audio nodes through the C backend
- Groups streams/sources/sinks into mixer strips
- Per-strip volume slider
- Per-strip mute toggle
- A1/A2/A3 + B1/B2/B3 routing buttons in the UI
- Friendly VoiceMeeter-like channel strip layout
- Hardware / virtual bus section
- Refresh button
- Dark pink/purple UI

## Not wired up yet

The routing buttons are UI-only in v0.1. They are meant to establish the layout
and state model before the persistent PipeWire link manager is added.

Meters are animated placeholders in v0.1 rather than true peak meters.

## Dependencies

On Arch / CachyOS:

```bash
sudo pacman -S python-pyside6 pipewire libpipewire meson ninja pkgconf
```

`wpctl` is provided by PipeWire / WirePlumber on a normal CachyOS install.

## Build

```bash
cd voicemix-v0.1
meson setup build
meson compile -C build
```

## Run

```bash
python src/main.py
```

The GUI looks for the backend at:

```text
./build/vm-backend
```

If the backend has not been built yet, the app still opens with demo channels so
the UI can be worked on immediately.

## v0.2 target

The obvious next step is to replace the visual-only routing matrix with a real
PipeWire graph manager:

- persistent app matching
- A1/A2/A3 hardware bus assignment
- B1/B2/B3 virtual sinks/sources
- automatic reconnect when apps or USB devices reappear
- real peak meters
- saved layouts / profiles
