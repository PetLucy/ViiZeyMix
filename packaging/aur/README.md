# AUR release checklist

This directory is the source for the separate `viizeymix` AUR repository.

1. Push the ViiZeyMix release commit and create the matching `v0.7.1` tag.
2. Copy `PKGBUILD` into the AUR repository.
3. Run `updpkgsums`; never submit the included temporary `SKIP` checksum.
4. Generate metadata with `makepkg --printsrcinfo > .SRCINFO`.
5. Test in a clean Arch chroot or with `makepkg -Ccf`.
6. Commit and push `PKGBUILD` and `.SRCINFO` to the AUR remote.

For later releases, bump `pkgver`, reset `pkgrel=1`, update the checksum, and
regenerate `.SRCINFO`.
