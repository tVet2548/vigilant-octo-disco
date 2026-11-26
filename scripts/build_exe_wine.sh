#!/usr/bin/env bash
set -euo pipefail

BUNDLE_DIR="${1:-dist_bundle}"
WINEPREFIX="${HOME}/.wine-py311"
export WINEPREFIX
export WINEARCH=win64
export WINEDEBUG=-all

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}"' EXIT

if [ ! -s "assets/app.ico" ]; then
  echo "assets/app.ico missing before build; generating default icon..."
  python3 scripts/generate_icon.py assets/app.ico
fi

resolve_wine_bin() {
  for cand in \
    "$(command -v wine 2>/dev/null || true)" \
    "$(command -v wine64 2>/dev/null || true)" \
    "/opt/wine-stable/bin/wine" \
    "/opt/wine-stable/bin/wine64" \
    "/usr/lib/wine/wine64" \
    "/usr/lib/wine/wine"; do
    if [ -n "${cand}" ] && [ -x "${cand}" ]; then
      echo "${cand}"
      return 0
    fi
  done
  return 1
}

ensure_wine_installed() {
  local wbin=""
  wbin="$(resolve_wine_bin || true)"

  if [ -z "${wbin}" ] || ! command -v wineboot >/dev/null 2>&1; then
    echo "Wine or wineboot missing on PATH; repairing Ubuntu multi-arch Wine packages..."
    if command -v sudo >/dev/null 2>&1; then
      sudo dpkg --add-architecture i386 || true
      sudo apt-get update -qq || true
      sudo DEBIAN_FRONTEND=noninteractive apt-get install -y --install-recommends \
        wine wine64 wine32 xvfb cabextract || true
    fi
    wbin="$(resolve_wine_bin || true)"
  fi

  if [ -z "${wbin}" ]; then
    echo "ERROR: Could not locate wine or wine64 binary after repair." >&2
    exit 127
  fi

  # Ensure /usr/bin/wine and /usr/bin/wineboot symlinks exist when only wine64/opt-wine is present
  if ! command -v wine >/dev/null 2>&1 && [ -x "${wbin}" ] && command -v sudo >/dev/null 2>&1; then
    sudo ln -sf "${wbin}" /usr/bin/wine || true
  fi
  if ! command -v wineboot >/dev/null 2>&1 && command -v sudo >/dev/null 2>&1; then
    for wb in /opt/wine-stable/bin/wineboot /usr/lib/wine/wineboot /usr/bin/wineboot-stable; do
      if [ -x "${wb}" ]; then
        sudo ln -sf "${wb}" /usr/bin/wineboot || true
        break
      fi
    done
  fi

  WINE_BIN="$(resolve_wine_bin)"
  echo "Using Wine binary: ${WINE_BIN} ($("${WINE_BIN}" --version 2>/dev/null || echo 'version unknown'))"
}

run_wine() {
  if command -v xvfb-run >/dev/null 2>&1; then
    xvfb-run -a "${WINE_BIN}" "$@"
  else
    DISPLAY="" "${WINE_BIN}" "$@"
  fi
}

ensure_wine_installed

echo "=== [1/4] Initializing 64-bit Wine Prefix ==="
if command -v wineboot >/dev/null 2>&1; then
  if command -v xvfb-run >/dev/null 2>&1; then
    xvfb-run -a wineboot --init || true
  else
    wineboot --init || true
  fi
else
  run_wine wineboot --init || run_wine cmd /c "echo prefix_ready" || true
fi
sleep 2

PY_INSTALLER_URL="https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe"
echo "Downloading Python 3.11.9 (Windows amd64)..."
if command -v aria2c >/dev/null 2>&1; then
  aria2c -x 8 -s 8 -k 1M -d "${TMP_DIR}" -o "python-3.11.9-amd64.exe" "${PY_INSTALLER_URL}" \
    || curl -fSL --retry 3 -o "${TMP_DIR}/python-3.11.9-amd64.exe" "${PY_INSTALLER_URL}"
else
  curl -fSL --retry 3 -o "${TMP_DIR}/python-3.11.9-amd64.exe" "${PY_INSTALLER_URL}"
fi

PY_SIZE=$(stat -c%s "${TMP_DIR}/python-3.11.9-amd64.exe" 2>/dev/null || echo 0)
if [ "${PY_SIZE}" -lt 10485760 ]; then
  echo "ERROR: Windows Python installer failed size check (${PY_SIZE} bytes): ${PY_INSTALLER_URL}" >&2
  exit 1
fi

echo "=== [2/4] Installing Windows Python 3.11.9 inside Wine ==="
run_wine "${TMP_DIR}/python-3.11.9-amd64.exe" /quiet InstallAllUsers=1 PrependPath=1 Include_test=0
if command -v wineserver >/dev/null 2>&1; then
  wineserver -w || true
fi

WIN_PYTHON='C:\Program Files\Python311\python.exe'
if [ ! -f "${WINEPREFIX}/drive_c/Program Files/Python311/python.exe" ] && \
   [ -f "${WINEPREFIX}/drive_c/Program Files (x86)/Python311/python.exe" ]; then
  WIN_PYTHON='C:\Program Files (x86)\Python311\python.exe'
fi

echo "=== [3/4] Installing CustomTkinter, TkinterDnD2, Pillow, and PyInstaller ==="
run_wine "${WIN_PYTHON}" -m pip install --upgrade pip
run_wine "${WIN_PYTHON}" -m pip install -r requirements-win.txt

echo "=== [4/4] Packaging AndroidLauncher.exe (Console Attached + GUI + DnD) ==="
run_wine "${WIN_PYTHON}" -m PyInstaller \
  --noconfirm \
  --clean \
  --onefile \
  --console \
  --icon=assets/app.ico \
  --name AndroidLauncher \
  --collect-all customtkinter \
  --collect-all tkinterdnd2 \
  --add-data "src/spoof_device.py;." \
  src/launcher.py

mkdir -p "${BUNDLE_DIR}"
cp -f "dist/AndroidLauncher.exe" "${BUNDLE_DIR}/AndroidLauncher.exe"
ls -lh "${BUNDLE_DIR}/AndroidLauncher.exe"
