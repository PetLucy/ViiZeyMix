#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_ROOT"

VERSION="$(python3 -c 'from pathlib import Path; scope={}; exec(Path("src/version.py").read_text(), scope); print(scope["__version__"])')"
ARCH="${ARCH:-x86_64}"
BUILD_DIR="$PROJECT_ROOT/build-appimage"
PYINSTALLER_DIR="$PROJECT_ROOT/dist"
APPDIR="$PROJECT_ROOT/AppDir"
OUTPUT_DIR="$PROJECT_ROOT/dist-appimage"

for command in meson ninja python3; do
    command -v "$command" >/dev/null || {
        echo "Missing build command: $command" >&2
        exit 1
    }
done
python3 -c 'import PyInstaller, PySide6' 2>/dev/null || {
    echo "PyInstaller and PySide6 must be installed in the build environment." >&2
    exit 1
}

if [[ -d "$BUILD_DIR" ]]; then
    meson setup --wipe "$BUILD_DIR" --buildtype=release
else
    meson setup "$BUILD_DIR" --buildtype=release
fi
meson compile -C "$BUILD_DIR"
meson test -C "$BUILD_DIR" --print-errorlogs
python3 -m unittest discover -s tests -p 'test_*.py' -v

python3 -m PyInstaller \
    --noconfirm \
    --clean \
    --onedir \
    --name viizeymix \
    --paths src \
    src/main.py

rm -rf "$APPDIR"
install -d \
    "$APPDIR/usr/bin" \
    "$APPDIR/usr/lib" \
    "$APPDIR/usr/share/applications" \
    "$APPDIR/usr/share/metainfo" \
    "$APPDIR/usr/share/icons/hicolor/scalable/apps"
cp -a "$PYINSTALLER_DIR/viizeymix" "$APPDIR/usr/lib/viizeymix"
install -m755 "$BUILD_DIR/viizeymix-backend" \
    "$APPDIR/usr/lib/viizeymix/viizeymix-backend"
install -m755 "$BUILD_DIR/viizeymix-dsp" \
    "$APPDIR/usr/lib/viizeymix/viizeymix-dsp"
for helper in viizeymix-backend viizeymix-dsp; do
    if ldd "$APPDIR/usr/lib/viizeymix/$helper" | grep -F 'not found'; then
        echo "$helper has unresolved shared-library dependencies." >&2
        exit 1
    fi
done
ln -s ../lib/viizeymix/viizeymix "$APPDIR/usr/bin/viizeymix"
install -Dm755 packaging/appimage/AppRun "$APPDIR/AppRun"
install -Dm644 data/io.github.petlucy.viizeymix.desktop \
    "$APPDIR/usr/share/applications/io.github.petlucy.viizeymix.desktop"
install -Dm644 data/io.github.petlucy.viizeymix.metainfo.xml \
    "$APPDIR/usr/share/metainfo/io.github.petlucy.viizeymix.metainfo.xml"
install -Dm644 data/icons/io.github.petlucy.viizeymix.svg \
    "$APPDIR/usr/share/icons/hicolor/scalable/apps/io.github.petlucy.viizeymix.svg"
ln -s usr/share/applications/io.github.petlucy.viizeymix.desktop \
    "$APPDIR/io.github.petlucy.viizeymix.desktop"
ln -s usr/share/icons/hicolor/scalable/apps/io.github.petlucy.viizeymix.svg \
    "$APPDIR/io.github.petlucy.viizeymix.svg"
ln -s io.github.petlucy.viizeymix.svg "$APPDIR/.DirIcon"

LINUXDEPLOY="${LINUXDEPLOY:-$(command -v linuxdeploy || true)}"
if [[ -z "$LINUXDEPLOY" || ! -x "$LINUXDEPLOY" ]]; then
    echo "Set LINUXDEPLOY to an executable linuxdeploy AppImage." >&2
    exit 1
fi

install -d "$OUTPUT_DIR"
rm -f \
    "$PROJECT_ROOT/ViiZeyMix-${ARCH}.AppImage" \
    "$PROJECT_ROOT/ViiZeyMix-${VERSION}-${ARCH}.AppImage"
VERSION="$VERSION" ARCH="$ARCH" "$LINUXDEPLOY" \
    --appdir "$APPDIR" \
    --desktop-file data/io.github.petlucy.viizeymix.desktop \
    --icon-file data/icons/io.github.petlucy.viizeymix.svg \
    --output appimage

GENERATED="$(find "$PROJECT_ROOT" -maxdepth 1 -type f -name 'ViiZeyMix*.AppImage' -print -quit)"
if [[ -z "$GENERATED" ]]; then
    echo "linuxdeploy completed without producing a ViiZeyMix AppImage." >&2
    exit 1
fi
FINAL="$OUTPUT_DIR/ViiZeyMix-${VERSION}-${ARCH}.AppImage"
mv "$GENERATED" "$FINAL"
sha256sum "$FINAL" > "$FINAL.sha256"
echo "Created $FINAL"
