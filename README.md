# ViiZeyMix

ViiZeyMix is a VoiceMeeter-style mixer for Linux built around PipeWire,
PySide6, and native C audio helpers.

Version 0.7.3 is the first packaging-ready release. An Arch/AUR package,
and a portable AppImage are now available.

## Installation

### Arch
`yay -S viizeymix`

### All Other Distros
1) Download the latest AppImage from the releases.
2) `chmod +x AppImage...`
3) `./AppImage...`

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

## IntelliPan controls

1. Assign A1-A3 hardware outputs as needed.
2. Route a source to an A or B bus.
3. Drag the source's IntelliPan pad.
4. Right-click the pad to cycle Color, Modulation, and Position.
5. Double-click to reset the visible panel.

The effects share one stereo PipeWire filter per active strip and run in the
order Color, Modulation, Position.

## License

ViiZeyMix is licensed under GPL-3.0-or-later. See `LICENSE`.
