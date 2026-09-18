# ViiZeyMix

ViiZeyMix is a VoiceMeeter-style mixer for Linux built around PipeWire,
PySide6, and native C audio helpers.

Version 0.7.2 is the first packaging-ready release. The same source tree now
supports development builds, normal system installation, an Arch/AUR package,
and a portable AppImage.

## Current features

- PipeWire hardware, microphone, and application-stream discovery
- separate Inputs & Sources and Outputs & Buses views
- A1-A3 hardware output assignments
- B1-B3 virtual Stream, Chat, and Record mix buses
- persistent hardware bus selection
- multi-output source routing
- live -60 to 0 dBFS peak meters
- honest 0-100% volume attenuation plus separate 0 to +12 dB gain
- mute controls
- native IntelliPan Color, Modulation, and Position processing
- cleanup of ViiZeyMix filters and meters on explicit exit

## Dependencies

### Arch Linux and CachyOS

```bash
sudo pacman -S python pyside6 pipewire pipewire-pulse libpipewire libpulse wireplumber meson ninja pkgconf
```

The `pipewire` package supplies `pw-cat`, `pw-link`, and `pw-dump`.
WirePlumber supplies `wpctl`, while `libpulse` supplies `pactl`.

## Development build

```bash
meson setup build
meson compile -C build
python src/main.py
```

If a build directory already exists:

```bash
meson setup --reconfigure build
meson compile -C build
```

The native build produces:

- `build/viizeymix-backend` for PipeWire discovery
- `build/viizeymix-dsp` for live IntelliPan processing

## System installation

Meson now installs the complete application:

```bash
meson setup build --prefix=/usr
meson compile -C build
sudo meson install -C build
viizeymix
```

Installed files include the launcher, Python frontend, native helpers, desktop
entry, scalable icon, AppStream metadata, and license.

For a staged package installation:

```bash
meson install -C build --destdir /path/to/package-root
```

Native helper lookup supports:

1. `VIIZEYMIX_LIBEXEC_DIR`, for packaging and diagnostics
2. a PyInstaller/AppImage bundle
3. the development `build/` directory
4. normal `/usr/lib/viizeymix` and `/usr/local/lib/viizeymix` installs

## AppImage

Install PySide6 and PyInstaller in the build environment, provide a
`linuxdeploy` executable, then run:

```bash
export LINUXDEPLOY=/path/to/linuxdeploy-x86_64.AppImage
bash packaging/appimage/build-appimage.sh
```

The output is written to:

```text
dist-appimage/ViiZeyMix-0.7.2-x86_64.AppImage
dist-appimage/ViiZeyMix-0.7.2-x86_64.AppImage.sha256
```

The AppImage bundles the ViiZeyMix frontend, PySide6/Qt, and both native
helpers. The host still needs a functioning PipeWire/WirePlumber audio stack
and the PipeWire command-line tools.

The GitHub workflow in `.github/workflows/release.yml` builds this AppImage on
Ubuntu 22.04. A pushed version tag attaches the AppImage and checksum to the
matching GitHub Release. The workflow can also be run manually without
publishing a release.

## AUR

`packaging/aur/PKGBUILD` builds the native Arch package directly from a
versioned GitHub source tag. The included checksum is deliberately `SKIP`
until the first public tag exists.

Before publishing to the AUR:

```bash
cp packaging/aur/PKGBUILD /path/to/aur/viizeymix/
cd /path/to/aur/viizeymix
updpkgsums
makepkg --printsrcinfo > .SRCINFO
makepkg -Ccf
```

Do not submit the temporary `SKIP` checksum. More details are in
`packaging/aur/README.md`.

## Release process

1. Update the version in `src/version.py`, `meson.build`, and the AUR files.
2. Update `CHANGELOG.md` and the AppStream release entry.
3. Run `scripts/release-check.sh`.
4. Commit and push the source.
5. Create and push the matching tag, for example `v0.7.2`.
6. Let GitHub Actions create or update the release and attach the AppImage.
7. Run `updpkgsums`, regenerate `.SRCINFO`, test, and push the AUR package.

When creating any additional downloadable source archive, use a fixed
`SOURCE_DATE_EPOCH` or normalize its entries to a past UTC timestamp. This
prevents the clock-skew failures seen in early test archives.

## Command-line information

```bash
viizeymix --version
```

## Tests

```bash
meson test -C build --print-errorlogs
python -m unittest discover -s tests -p 'test_*.py' -v
```

The release-check script runs the Python checks everywhere and adds the native
build and DSP test when Meson and the PipeWire development files are present.

## IntelliPan controls

1. Assign A1-A3 hardware outputs as needed.
2. Route a source to an A or B bus.
3. Drag the source's IntelliPan pad.
4. Right-click the pad to cycle Color, Modulation, and Position.
5. Double-click to reset the visible panel.

The effects share one stereo PipeWire filter per active strip and run in the
order Color, Modulation, Position.

## Remaining work

- automatic route reattachment when an application returns with a new node ID
- close-to-tray behavior with a distinct explicit Exit cleanup path
- presets and broader configuration persistence
- replacing remaining command-line PipeWire operations with native backend APIs

## License

ViiZeyMix is licensed under GPL-3.0-or-later. See `LICENSE`.
