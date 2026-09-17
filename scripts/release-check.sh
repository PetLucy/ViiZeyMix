#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

PYTHON_VERSION="$(python3 -c 'from pathlib import Path; scope={}; exec(Path("src/version.py").read_text(), scope); print(scope["__version__"])')"
MESON_VERSION="$(sed -n "s/.*version: '\([^']*\)'.*/\1/p" meson.build | head -n1)"
PKGBUILD_VERSION="$(sed -n 's/^pkgver=//p' packaging/aur/PKGBUILD)"

if [[ "$PYTHON_VERSION" != "$MESON_VERSION" || "$PYTHON_VERSION" != "$PKGBUILD_VERSION" ]]; then
    echo "Version mismatch: Python=$PYTHON_VERSION Meson=$MESON_VERSION PKGBUILD=$PKGBUILD_VERSION" >&2
    exit 1
fi

python3 -m compileall -q src tests
python3 -m unittest discover -s tests -p 'test_*.py' -v

if command -v meson >/dev/null && pkg-config --exists libpipewire-0.3; then
    if [[ -d build ]]; then
        meson setup --wipe build
    else
        meson setup build
    fi
    meson compile -C build
    meson test -C build --print-errorlogs
else
    echo "Skipping native build: Meson or libpipewire development files are unavailable."
fi

echo "ViiZeyMix $PYTHON_VERSION release checks passed."
