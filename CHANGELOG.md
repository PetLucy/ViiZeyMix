# Changelog

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
