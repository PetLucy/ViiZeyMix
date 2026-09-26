# Changelog

## 0.8.2 - 2026-09-25

- Added automatic discovery of application playback streams such as Firefox.
- Removed the twelve-source and twelve-output display limits.
- Refresh the mixer only when the visible PipeWire node set changes, while
  ignoring ViiZeyMix meter and DSP helper nodes.
- Create non-autoconnecting meter nodes and explicitly link each source by its
  unique PipeWire node ID, preventing every meter from following the default
  capture device.

## 0.8.1 - 2026-09-20

- Replaced the large Gate dial and detail page with a compact horizontal Gate
  slider directly below Gain.
- Removed the empty space caused by the stacked IntelliPan/Gate editor.
- Removed the visible per-strip DSP status label.

## 0.8.0 - 2026-09-20

- Added a native stereo-linked noise gate before IntelliPan processing.
- Added a VoiceMeeter-style 0-10 Gate dial with double-click reset.
- Added a right-click detail panel for threshold, maximum damping, sidechain
  frequency, attack, hold, and release.
- Kept Gate and IntelliPan in one PipeWire processor so existing routes stay
  connected while effects change.

## 0.7.4 - 2026-09-20

- Added selectable B1, B2, and B3 capture devices for Discord, VRChat, OBS,
  and other applications.
- Backed each virtual capture device with its B bus monitor so routed audio is
  available without manual Helvum connections.
- Hid the new ViiZeyMix helper sources from the Inputs & Sources tab.

## 0.7.3 - 2026-09-18

- Moved native PipeWire helpers out of PyInstaller's private `_internal`
  directory and installed them explicitly as executable AppImage payloads.
- Added a clear startup warning with the native discovery failure instead of
  silently presenting demo devices.

## 0.7.2 - 2026-09-18

- Added the complete Qt XCB platform dependency set to the Ubuntu AppImage
  builder, including `libxcb-icccm.so.4`.
- Added early checks for both EGL and XCB ICCCM before linuxdeploy runs.

## 0.7.1 - 2026-09-17

- Fixed the AppImage workflow on the headless Ubuntu runner by installing the
  EGL/OpenGL and Qt platform libraries inspected by linuxdeploy.
- Added an explicit build-time check for `libEGL.so.1`.

## 0.7.0 - 2026-09-17

- Added a system-installable Meson layout.
- Added development, installed, and bundled native-helper discovery.
- Added desktop, icon, and AppStream metadata.
- Added an AppImage build script and tag-driven GitHub Actions release workflow.
- Added an AUR `PKGBUILD` and release checklist.
- Added `viizeymix --version`.
- Added release consistency checks and reproducible archive timestamp guidance.

## 0.6.0

- Added live PipeWire peak meters.
- Separated unity-level volume from optional positive gain.
- Removed routine debug status messages from the interface.
