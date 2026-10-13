#!/bin/sh
# Linux entry point of the SRM benchmark: checks the platform, fetches the pinned uv,
# builds the private environment under .runtime/ and runs "python -m srmbench "$@"".
# Exit codes: 2 unsupported platform, 3 setup failure, otherwise the exit code of srmbench.
set -eu

BENCH=$(cd "$(dirname "$0")" && pwd)
REPO=$(dirname "$BENCH")
RT="$BENCH/.runtime"
UV="$RT/uv/uv"
PY="$RT/venv/bin/python"

unsupported() {
    echo "This machine is not supported: $1. Supported: Windows 10 1803+ or 11 on x64, Linux x86_64 with glibc 2.28+." >&2
    exit 2
}

setup_failed() {
    echo "$1" >&2
    echo "Setup failed. Delete $RT and run this script again; if it keeps failing, see bench/README.md." >&2
    exit 3
}

sha256_of() {
    sha256sum "$1" | cut -d ' ' -f 1
}

# ---- 1. Platform gate ----------------------------------------------------------------------
OS=$(uname -s)
[ "$OS" = "Linux" ] || unsupported "the operating system is $OS"
ARCH=$(uname -m)
[ "$ARCH" = "x86_64" ] || unsupported "the CPU architecture is $ARCH"
if [ "$(getconf LONG_BIT 2>/dev/null || echo 64)" != "64" ]; then
    unsupported "the user space is 32-bit"
fi
command -v ldd >/dev/null 2>&1 || unsupported "ldd is missing, so the C library cannot be identified"
LDD_OUT=$(ldd --version 2>&1 || true)
case "$LDD_OUT" in
    *musl*) unsupported "the C library is musl (Alpine)" ;;
esac
GLIBC=$(printf '%s\n' "$LDD_OUT" | head -n 1 | awk '{print $NF}')
GLIBC_MAJOR=${GLIBC%%.*}
GLIBC_REST=${GLIBC#*.}
GLIBC_MINOR=${GLIBC_REST%%[!0-9]*}
case "$GLIBC_MAJOR" in ''|*[!0-9]*) unsupported "the glibc version cannot be read" ;; esac
case "$GLIBC_MINOR" in ''|*[!0-9]*) unsupported "the glibc version cannot be read" ;; esac
if [ "$GLIBC_MAJOR" -lt 2 ] || { [ "$GLIBC_MAJOR" -eq 2 ] && [ "$GLIBC_MINOR" -lt 28 ]; }; then
    unsupported "glibc $GLIBC is older than 2.28"
fi

# ---- 2. uv -------------------------------------------------------------------------------
UV_VER=$(sed -n 's/^version=//p' "$BENCH/uv.version" | tr -d '\r')
LINUX_SHA=$(sed -n 's/^linux_sha256=//p' "$BENCH/uv.version" | tr -d '\r')
[ -n "$UV_VER" ] && [ -n "$LINUX_SHA" ] || setup_failed "uv.version lacks the version or linux_sha256 line."

if [ ! -x "$UV" ]; then
    echo "Downloading uv $UV_VER ..."
    URL="https://github.com/astral-sh/uv/releases/download/$UV_VER/uv-x86_64-unknown-linux-gnu.tar.gz"
    mkdir -p "$RT"
    rm -rf "$RT/uv"
    mkdir -p "$RT/uv"
    if command -v curl >/dev/null 2>&1; then
        curl -fL --retry 3 -o "$RT/uv.tar.gz" "$URL" || setup_failed "Could not download uv from GitHub. Check the network connection."
    elif command -v wget >/dev/null 2>&1; then
        wget -O "$RT/uv.tar.gz" "$URL" || setup_failed "Could not download uv from GitHub. Check the network connection."
    else
        setup_failed "Neither curl nor wget is installed; install one of them."
    fi
    GOT=$(sha256_of "$RT/uv.tar.gz")
    if [ "$GOT" != "$LINUX_SHA" ]; then
        rm -f "$RT/uv.tar.gz"
        setup_failed "The downloaded uv archive failed its SHA-256 check (got $GOT)."
    fi
    tar -xzf "$RT/uv.tar.gz" --strip-components=1 -C "$RT/uv" || setup_failed "Could not unpack the uv archive."
    rm -f "$RT/uv.tar.gz"
    [ -x "$UV" ] || setup_failed "The uv archive did not contain the uv binary."
fi

# ---- 3. Everything uv writes stays under .runtime ----------------------------------------------
UV_CACHE_DIR="$RT/cache"
UV_PYTHON_INSTALL_DIR="$RT/python"
UV_PYTHON_PREFERENCE=only-managed
export UV_CACHE_DIR UV_PYTHON_INSTALL_DIR UV_PYTHON_PREFERENCE

# ---- 4. Is the environment current? ----------------------------------------------------------
STAMP="$(sha256_of "$BENCH/requirements.lock") $(sha256_of "$REPO/pyproject.toml")"
CURRENT=0
if [ -x "$PY" ] && [ -f "$RT/stamp" ]; then
    OLD=$(cat "$RT/stamp")
    if [ "$OLD" = "$STAMP" ]; then
        CURRENT=1
    fi
fi

# ---- 5. Python, venv, packages -------------------------------------------------------------
if [ "$CURRENT" -eq 0 ]; then
    rm -f "$RT/stamp"
    echo "Setting up the benchmark environment in $RT ..."
    "$UV" venv "$RT/venv" --python 3.12 --clear || setup_failed "Creating the Python environment failed."
    "$UV" pip sync --python "$PY" "$BENCH/requirements.lock" || setup_failed "Installing the pinned packages failed."
    "$UV" pip install --python "$PY" --no-deps -e "$REPO" || setup_failed "Installing the SRM design tool from this checkout failed."
    printf '%s\n' "$STAMP" > "$RT/stamp"
fi

# ---- Gmsh needs a few system libraries on Linux -------------------------------------------
if ! "$PY" -c "import gmsh" 2>"$RT/gmsh-import.err"; then
    echo "Gmsh cannot be loaded (missing system libraries):" >&2
    cat "$RT/gmsh-import.err" >&2
    SUDO=""
    if [ "$(id -u)" -ne 0 ] && command -v sudo >/dev/null 2>&1; then
        SUDO="sudo"
    fi
    if command -v apt-get >/dev/null 2>&1; then
        UPDATE_CMD="apt-get update"
        INSTALL_CMD="apt-get install -y libglu1-mesa libxcursor1 libxft2 libxinerama1"
    elif command -v dnf >/dev/null 2>&1; then
        UPDATE_CMD=""
        INSTALL_CMD="dnf install -y mesa-libGLU libXcursor libXft libXinerama"
    elif command -v yum >/dev/null 2>&1; then
        UPDATE_CMD=""
        INSTALL_CMD="yum install -y mesa-libGLU libXcursor libXft libXinerama"
    else
        setup_failed "No known package manager. Install the OpenGL/X11 libraries libGLU, libXcursor, libXft and libXinerama, then run this script again."
    fi
    if [ "$(id -u)" -ne 0 ] && [ -z "$SUDO" ]; then
        setup_failed "Run this as root, then run this script again: $INSTALL_CMD"
    fi
    if [ -n "$UPDATE_CMD" ]; then
        # shellcheck disable=SC2086
        $SUDO $UPDATE_CMD || echo "Package index update failed; trying the install anyway." >&2
    fi
    # shellcheck disable=SC2086
    $SUDO $INSTALL_CMD || setup_failed "Installing the system libraries failed. Run: ${SUDO:+$SUDO }$INSTALL_CMD"
    "$PY" -c "import gmsh" || setup_failed "Gmsh still cannot be loaded after installing the system libraries."
fi

# ---- 6. Run ----------------------------------------------------------------------------
# Ctrl+C reaches Python (which handles it); this shell stays alive for the finish step.
# A flag left by an interrupted earlier run must not be acted on.
rm -f "$RT/finish"
trap : INT
set +e
PYTHONPATH="$BENCH" "$PY" -m srmbench "$@"
RC=$?
set -e
trap - INT

# ---- 7. Finish: srmbench leaves the user's choice in .runtime/finish -----------------------------
FIN=""
if [ -f "$RT/finish" ]; then
    FIN=$(tr -d '\r\n' < "$RT/finish")
fi
case "$FIN" in
    delete)
        cd "$BENCH"
        rm -rf "$RT"
        ;;
    keep-full)
        rm -f "$RT/finish"
        "$UV" pip install --python "$PY" -e "$REPO[web]" || echo "Installing the web extra failed; the benchmark environment is unchanged otherwise." >&2
        echo "Web frontend: cd web, npm ci, npm run build (needs Node 22)."
        ;;
    *)
        rm -f "$RT/finish"
        ;;
esac
exit "$RC"
