#!/bin/sh
# Creates hil/.runtime (git-ignored) with the pinned PlatformIO. Nothing is installed outside it.
set -e
PIO_VERSION=6.2.0
HERE="$(cd "$(dirname "$0")" && pwd)"
[ -x "$HERE/.runtime/bin/python" ] || python3 -m venv "$HERE/.runtime"
"$HERE/.runtime/bin/python" -m pip install --quiet "platformio==$PIO_VERSION"
echo "PlatformIO $PIO_VERSION ready in $HERE/.runtime"
