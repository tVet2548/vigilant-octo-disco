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

gh_api_curl() {
  local url="$1"
  local tok="${GITHUB_TOKEN:-${GH_TOKEN:-}}"
  if [ -n "${tok}" ]; then
    curl -fsSL --retry 3 --retry-delay 2 \
      -H "Authorization: Bearer ${tok}" \
      -H "Accept: application/vnd.github+json" \
      -H "X-GitHub-Api-Version: 2022-11-28" \
      "${url}" 2>/dev/null || true
  else
    curl -fsSL --retry 2 --retry-delay 2 \
      -H "Accept: application/vnd.github+json" \
      "${url}" 2>/dev/null || true
  fi
}

resolve_github_asset() {
  local repo="$1"
  local regex="$2"
  local fallback_url="${3:-}"
  local url=""

  # 1) Authenticated GitHub Releases API (uses GITHUB_TOKEN / GH_TOKEN when present)
  local json
  json=$(gh_api_curl "https://api.github.com/repos/${repo}/releases/latest")
  if [ -n "${json}" ]; then
    url=$(printf '%s' "${json}" | jq -r --arg re "${regex}" '.assets[]? | select(.name | test($re; "i")) | .browser_download_url' 2>/dev/null | head -n1 || true)
  fi

  # 2) Fallback without API: resolve /releases/latest HTTP redirect -> scrape /releases/expanded_assets/<tag>
  if [ -z "${url}" ] || [ "${url}" = "null" ]; then
    local latest_eff tag
    latest_eff=$(curl -fsSLI -o /dev/null -w '%{url_effective}' "https://github.com/${repo}/releases/latest" 2>/dev/null || true)
    tag="${latest_eff##*/}"
    if [ -n "${tag}" ] && [ "${tag}" != "latest" ] && [ "${tag}" != "releases" ]; then
      local rel_path
      rel_path=$(curl -fsSL --retry 3 --retry-delay 2 "https://github.com/${repo}/releases/expanded_assets/${tag}" 2>/dev/null | \
        grep -oE "/${repo}/releases/download/[^\"'<> ]+" | grep -iE "${regex}" | head -n1 || true)
      if [ -n "${rel_path}" ]; then
        url="https://github.com${rel_path}"
      fi
    fi
  fi

  # 3) Final fallback: direct pinned stable release URL
  if [ -z "${url}" ] || [ "${url}" = "null" ]; then
    url="${fallback_url}"
  fi

  printf '%s' "${url}"
}

echo "=== [1/6] Downloading QEMU for Windows (WHPX + VirGL + ANGLE) ==="
QEMU_URL=$(resolve_github_asset "droidbakers/qemu-virgl-whpx" '\.(zip|7z|exe)$' "")

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
  ANGLE_URL=$(resolve_github_asset "mmozeiko/build-angle" 'x64.*\.zip$' "")
  if [ -n "${ANGLE_URL}" ] && [ "${ANGLE_URL}" != "null" ]; then
    if download_and_verify "${ANGLE_URL}" "${TMP_DIR}/angle.zip" 1048576 "ANGLE-DX11"; then
      7z x "${TMP_DIR}/angle.zip" -o"${TMP_DIR}/angle_ext" -y >/dev/null
      find "${TMP_DIR}/angle_ext" -type f \( -name "libEGL.dll" -o -name "libGLESv2.dll" -o -name "d3dcompiler_47.dll" \) -exec cp -f {} "${BIN_DIR}/" \;
    fi
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
SCRCPY_FALLBACK_URL="https://github.com/Genymobile/scrcpy/releases/download/v3.1/scrcpy-win64-v3.1.zip"
SCRCPY_URL=$(resolve_github_asset "Genymobile/scrcpy" 'scrcpy-win64-.*\.zip$' "${SCRCPY_FALLBACK_URL}")
if [ -z "${SCRCPY_URL}" ] || [ "${SCRCPY_URL}" = "null" ]; then
  SCRCPY_URL="${SCRCPY_FALLBACK_URL}"
fi
if ! download_and_verify "${SCRCPY_URL}" "${TMP_DIR}/scrcpy-win64.zip" 1048576 "scrcpy-win64"; then
  if [ "${SCRCPY_URL}" != "${SCRCPY_FALLBACK_URL}" ]; then
    echo "Retrying scrcpy with pinned stable release: ${SCRCPY_FALLBACK_URL}"
    SCRCPY_URL="${SCRCPY_FALLBACK_URL}"
    download_and_verify "${SCRCPY_URL}" "${TMP_DIR}/scrcpy-win64.zip" 1048576 "scrcpy-win64-fallback"
  else
    exit 1
  fi
fi
7z x "${TMP_DIR}/scrcpy-win64.zip" -o"${TMP_DIR}/scrcpy_ext" -y >/dev/null
SCRCPY_EXE=$(find "${TMP_DIR}/scrcpy_ext" -name "scrcpy.exe" | head -n1 || true)
if [ -z "${SCRCPY_EXE}" ]; then
  echo "ERROR: scrcpy.exe missing inside downloaded scrcpy archive (${SCRCPY_URL})." >&2
  exit 1
fi
cp -a "$(dirname "${SCRCPY_EXE}")/." "${SCRCPY_DIR}/"

echo "=== [4/6] Downloading KernelSU Next Manager APK (KernelSU-Next/KernelSU-Next) ==="
KSU_APK_URL=$(resolve_github_asset "KernelSU-Next/KernelSU-Next" '\.apk$' "")
if [ -z "${KSU_APK_URL}" ] || [ "${KSU_APK_URL}" = "null" ]; then
  echo "ERROR: Could not resolve KernelSU Next APK release URL." >&2
  exit 1
fi
download_and_verify "${KSU_APK_URL}" "${MOD_DIR}/KernelSU_Next.apk" 1048576 "KernelSU-Next-APK"

echo "=== [5/6] Downloading Zygisk Next & TrickyStore ==="
ZYGISK_URL=$(resolve_github_asset "Dr-TSNG/ZygiskNext" '\.zip$' "")
if [ -n "${ZYGISK_URL}" ] && [ "${ZYGISK_URL}" != "null" ]; then
  download_and_verify "${ZYGISK_URL}" "${MOD_DIR}/ZygiskNext.zip" 102400 "ZygiskNext" || echo "WARNING: ZygiskNext download failed."
else
  echo "WARNING: Could not resolve ZygiskNext latest release URL."
fi

TRICKY_URL=$(resolve_github_asset "5ec1cff/TrickyStore" '\.zip$' "")
if [ -n "${TRICKY_URL}" ] && [ "${TRICKY_URL}" != "null" ]; then
  download_and_verify "${TRICKY_URL}" "${MOD_DIR}/TrickyStore.zip" 51200 "TrickyStore" || echo "WARNING: TrickyStore download failed."
else
  echo "WARNING: Could not resolve TrickyStore latest release URL."
fi

echo "=== [6/6] Downloading PlayIntegrityFix (KOWX712 / osm0sis fallback) ==="
PIF_URL=$(resolve_github_asset "KOWX712/PlayIntegrityFix" '\.zip$' "")
if [ -z "${PIF_URL}" ] || [ "${PIF_URL}" = "null" ]; then
  PIF_URL=$(resolve_github_asset "osm0sis/PlayIntegrityFork" '\.zip$' "")
fi
if [ -n "${PIF_URL}" ] && [ "${PIF_URL}" != "null" ]; then
  download_and_verify "${PIF_URL}" "${MOD_DIR}/PlayIntegrityFix.zip" 10240 "PlayIntegrityFix" || echo "WARNING: PlayIntegrityFix download failed."
else
  echo "WARNING: Could not resolve PlayIntegrityFix latest release URL."
fi

ls -lh "${SCRCPY_DIR}/scrcpy.exe" "${MOD_DIR}"
