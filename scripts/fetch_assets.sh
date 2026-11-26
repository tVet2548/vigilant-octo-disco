#!/usr/bin/env bash
set -euo pipefail

BUNDLE_DIR="${1:-dist_bundle}"
BIN_DIR="${BUNDLE_DIR}/bin"
SCRCPY_DIR="${BIN_DIR}/scrcpy"
MOD_DIR="${BUNDLE_DIR}/modules"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}"' EXIT

mkdir -p "${BIN_DIR}" "${SCRCPY_DIR}" "${MOD_DIR}"

download_and_verify() {
  local url="$1"
  local out_file="$2"
  local min_bytes="$3"
  local label="$4"

  echo "Downloading ${label}: ${url}"
  if ! curl -fSL --retry 4 --retry-delay 3 -o "${out_file}" "${url}"; then
    echo "ERROR [${label}]: Download failed for URL: ${url}" >&2
    return 1
  fi

  local actual_bytes
  actual_bytes=$(stat -c%s "${out_file}" 2>/dev/null || echo 0)
  local mime_desc
  mime_desc=$(file -b "${out_file}" 2>/dev/null || echo "unknown")

  if [ "${actual_bytes}" -lt "${min_bytes}" ] || echo "${mime_desc}" | grep -qiE 'HTML|text/html|ASCII text'; then
    echo "ERROR [${label}]: Downloaded file failed 3-layer integrity check!" >&2
    echo "  Broken URL   : ${url}" >&2
    echo "  Actual Size  : ${actual_bytes} bytes (Required >= ${min_bytes} bytes)" >&2
    echo "  Detected Type: ${mime_desc}" >&2
    return 1
  fi

  echo "Verified [${label}]: ${actual_bytes} bytes (${mime_desc})"
  return 0
}

echo "=== [1/6] Downloading QEMU for Windows (WHPX + VirGL + ANGLE) ==="
QEMU_URL=""
QEMU_JSON=$(curl -fsSL "https://api.github.com/repos/droidbakers/qemu-virgl-whpx/releases/latest" || true)
if [ -n "${QEMU_JSON}" ]; then
  QEMU_URL=$(echo "${QEMU_JSON}" | jq -r '.assets[] | select(.name | test("\\.(zip|7z|exe)$"; "i")) | .browser_download_url' | head -n1 || true)
fi

if [ -n "${QEMU_URL}" ] && [ "${QEMU_URL}" != "null" ]; then
  if download_and_verify "${QEMU_URL}" "${TMP_DIR}/qemu_virgl.pkg" 5242880 "QEMU-VirGL-WHPX"; then
    7z x "${TMP_DIR}/qemu_virgl.pkg" -o"${TMP_DIR}/qemu_extract" -y >/dev/null
    QEMU_EXE_PATH=$(find "${TMP_DIR}/qemu_extract" -name "qemu-system-x86_64.exe" | head -n1 || true)
    if [ -n "${QEMU_EXE_PATH}" ]; then
      cp -a "$(dirname "${QEMU_EXE_PATH}")/." "${BIN_DIR}/"
    fi
  fi
fi

if [ ! -s "${BIN_DIR}/qemu-system-x86_64.exe" ]; then
  echo "Falling back to official qemu.weilnetz.de/w64/..."
  LATEST_WEILNETZ=$(curl -fsSL "https://qemu.weilnetz.de/w64/" | grep -oE 'qemu-w64-setup-[0-9]+\.exe' | sort -V | tail -n1 || true)
  if [ -z "${LATEST_WEILNETZ}" ]; then
    echo "ERROR: Could not parse latest installer from https://qemu.weilnetz.de/w64/" >&2
    exit 1
  fi
  download_and_verify "https://qemu.weilnetz.de/w64/${LATEST_WEILNETZ}" "${TMP_DIR}/qemu-setup.exe" 52428800 "QEMU-Weilnetz"
  7z x "${TMP_DIR}/qemu-setup.exe" -o"${BIN_DIR}" -y >/dev/null
fi

QEMU_ARCH_DESC=$(file -b "${BIN_DIR}/qemu-system-x86_64.exe" 2>/dev/null || echo "unknown")
echo "Verified [QEMU-Binary]: ${QEMU_ARCH_DESC}"
if ! echo "${QEMU_ARCH_DESC}" | grep -qiE 'PE32\+|x86-64'; then
  echo "WARNING: Expected 64-bit PE32+ QEMU binary; detected: ${QEMU_ARCH_DESC}" >&2
fi

if [ ! -s "${BIN_DIR}/libEGL.dll" ] || [ ! -s "${BIN_DIR}/libGLESv2.dll" ]; then
  echo "Fetching ANGLE DirectX 11 DLLs (mmozeiko/build-angle)..."
  ANGLE_JSON=$(curl -fsSL "https://api.github.com/repos/mmozeiko/build-angle/releases/latest" || true)
  ANGLE_URL=$(echo "${ANGLE_JSON}" | jq -r '.assets[] | select(.name | test("x64.*\\.zip$"; "i")) | .browser_download_url' | head -n1 || true)
  if [ -n "${ANGLE_URL}" ] && [ "${ANGLE_URL}" != "null" ]; then
    download_and_verify "${ANGLE_URL}" "${TMP_DIR}/angle.zip" 1048576 "ANGLE-DX11"
    7z x "${TMP_DIR}/angle.zip" -o"${TMP_DIR}/angle_ext" -y >/dev/null
    find "${TMP_DIR}/angle_ext" -type f \( -name "libEGL.dll" -o -name "libGLESv2.dll" -o -name "d3dcompiler_47.dll" \) -exec cp -f {} "${BIN_DIR}/" \;
  fi
fi

echo "=== [2/6] Downloading Google Android Platform Tools (ADB for Windows) ==="
download_and_verify \
  "https://dl.google.com/android/repository/platform-tools-latest-windows.zip" \
  "${TMP_DIR}/platform-tools.zip" \
  1048576 \
  "Google-ADB-Windows"
7z e "${TMP_DIR}/platform-tools.zip" "platform-tools/adb.exe" "platform-tools/AdbWinApi.dll" "platform-tools/AdbWinUsbApi.dll" -o"${BIN_DIR}" -y >/dev/null

echo "=== [3/6] Downloading Genymobile scrcpy (Windows x64 for Multi-Window Mode) ==="
SCRCPY_URL=$(curl -fsSL "https://api.github.com/repos/Genymobile/scrcpy/releases/latest" | jq -r '.assets[] | select(.name | test("scrcpy-win64-.*\\.zip$"; "i")) | .browser_download_url' | head -n1 || true)
if [ -z "${SCRCPY_URL}" ] || [ "${SCRCPY_URL}" = "null" ]; then
  echo "ERROR: Could not resolve latest Genymobile/scrcpy Windows x64 zip URL." >&2
  exit 1
fi
download_and_verify "${SCRCPY_URL}" "${TMP_DIR}/scrcpy-win64.zip" 1048576 "scrcpy-win64"
7z x "${TMP_DIR}/scrcpy-win64.zip" -o"${TMP_DIR}/scrcpy_ext" -y >/dev/null
SCRCPY_EXE=$(find "${TMP_DIR}/scrcpy_ext" -name "scrcpy.exe" | head -n1 || true)
if [ -z "${SCRCPY_EXE}" ]; then
  echo "ERROR: scrcpy.exe missing inside downloaded scrcpy archive (${SCRCPY_URL})." >&2
  exit 1
fi
cp -a "$(dirname "${SCRCPY_EXE}")/." "${SCRCPY_DIR}/"

echo "=== [4/6] Downloading KernelSU Next Manager APK (KernelSU-Next/KernelSU-Next) ==="
KSU_APK_URL=$(curl -fsSL "https://api.github.com/repos/KernelSU-Next/KernelSU-Next/releases/latest" | jq -r '.assets[] | select(.name | test("\\.apk$"; "i")) | .browser_download_url' | head -n1 || true)
if [ -z "${KSU_APK_URL}" ] || [ "${KSU_APK_URL}" = "null" ]; then
  echo "ERROR: Could not resolve KernelSU Next APK release URL." >&2
  exit 1
fi
download_and_verify "${KSU_APK_URL}" "${MOD_DIR}/KernelSU_Next.apk" 1048576 "KernelSU-Next-APK"

echo "=== [5/6] Downloading Zygisk Next & TrickyStore ==="
ZYGISK_URL=$(curl -fsSL "https://api.github.com/repos/Dr-TSNG/ZygiskNext/releases/latest" | jq -r '.assets[] | select(.name | test("\\.zip$"; "i")) | .browser_download_url' | head -n1 || true)
if [ -n "${ZYGISK_URL}" ] && [ "${ZYGISK_URL}" != "null" ]; then
  download_and_verify "${ZYGISK_URL}" "${MOD_DIR}/ZygiskNext.zip" 102400 "ZygiskNext"
else
  echo "WARNING: Could not resolve ZygiskNext latest release URL."
fi

TRICKY_URL=$(curl -fsSL "https://api.github.com/repos/5ec1cff/TrickyStore/releases/latest" | jq -r '.assets[] | select(.name | test("\\.zip$"; "i")) | .browser_download_url' | head -n1 || true)
if [ -n "${TRICKY_URL}" ] && [ "${TRICKY_URL}" != "null" ]; then
  download_and_verify "${TRICKY_URL}" "${MOD_DIR}/TrickyStore.zip" 51200 "TrickyStore"
else
  echo "WARNING: Could not resolve TrickyStore latest release URL."
fi

echo "=== [6/6] Downloading PlayIntegrityFix (KOWX712 / osm0sis fallback) ==="
PIF_URL=$(curl -fsSL "https://api.github.com/repos/KOWX712/PlayIntegrityFix/releases/latest" | jq -r '.assets[] | select(.name | test("\\.zip$"; "i")) | .browser_download_url' | head -n1 || true)
if [ -z "${PIF_URL}" ] || [ "${PIF_URL}" = "null" ]; then
  PIF_URL=$(curl -fsSL "https://api.github.com/repos/osm0sis/PlayIntegrityFork/releases/latest" | jq -r '.assets[] | select(.name | test("\\.zip$"; "i")) | .browser_download_url' | head -n1 || true)
fi
if [ -n "${PIF_URL}" ] && [ "${PIF_URL}" != "null" ]; then
  download_and_verify "${PIF_URL}" "${MOD_DIR}/PlayIntegrityFix.zip" 10240 "PlayIntegrityFix"
else
  echo "WARNING: Could not resolve PlayIntegrityFix latest release URL."
fi

ls -lh "${SCRCPY_DIR}/scrcpy.exe" "${MOD_DIR}"
