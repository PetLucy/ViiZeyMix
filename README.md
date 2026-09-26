# ViiZeyMix

ViiZeyMix is a VoiceMeeter-style mixer for Linux built around PipeWire,
PySide6, and native C audio helpers.

Version 0.8.2 automatically discovers application playback streams such as
Firefox and removes the previous device display limits. An Arch/AUR package
and a portable AppImage are available.

## Installation

### Arch
`yay -S viizeymix`

### All Other Distros
1) Download the latest AppImage from the releases.
2) `chmod +x AppImage...`
3) `./AppImage...`

## Current features

- PipeWire hardware, microphone, and application-stream discovery
- automatic appearance and removal of application playback streams
- separate Inputs & Sources and Outputs & Buses views
- A1-A3 hardware output assignments
- B1-B3 virtual Stream, Chat, and Record mix buses
- selectable B1-B3 capture devices for voice chat, games, and recording apps
- persistent hardware bus selection
- multi-output source routing
- live -60 to 0 dBFS peak meters
- honest 0-100% volume attenuation plus separate 0 to +12 dB gain
- mute controls
- native stereo-linked noise gate with a compact 0-10 control
- native IntelliPan Color, Modulation, and Position processing
- cleanup of ViiZeyMix filters and meters on explicit exit

## Gate and IntelliPan controls

1. Assign A1-A3 hardware outputs as needed.
2. Route a source to an A or B bus.
3. Move the GATE slider from 0 to 10 for noise reduction; 0 bypasses it.
4. Drag the source's IntelliPan pad.
5. Right-click the pad to cycle Color, Modulation, and Position.
6. Double-click to reset the visible IntelliPan panel.

The effects share one stereo PipeWire filter per active strip and run in the
order Gate, Color, Modulation, Position.

## License

ViiZeyMix is licensed under GPL-3.0-or-later. See `LICENSE`.
