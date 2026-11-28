#!/usr/bin/env bash
set -euo pipefail

echo "=== Initial Disk Usage ==="
df -h /

AVAIL_KB=$(df -k --output=avail / | tail -n1 | tr -d ' ')
AVAIL_GB=$((AVAIL_KB / 1024 / 1024))
echo "Available root disk space before cleanup: ${AVAIL_GB} GB"
if [ "${AVAIL_GB}" -ge 45 ]; then
  echo "Disk budget already satisfied (>= 45 GB); skipping destructive toolchain cleanup."
  exit 0
fi

echo "=== Removing bulky preinstalled toolchains on ubuntu-latest ==="
rm -rf /usr/share/dotnet || true
rm -rf /usr/local/lib/android || true
rm -rf /opt/ghc || true
rm -rf /opt/hostedtoolcache || true
rm -rf /usr/local/.ghcup || true
rm -rf /usr/local/share/powershell || true
rm -rf /usr/local/share/chromium || true
rm -rf /usr/local/lib/node_modules || true
rm -rf /usr/share/swift || true
rm -rf /usr/share/miniconda || true
rm -rf /usr/local/julia* || true

echo "=== Pruning Docker images and apt cache ==="
if command -v docker >/dev/null 2>&1; then
  docker system prune -af --volumes || true
fi
apt-get clean || true
rm -rf /var/lib/apt/lists/* || true

echo "=== Final Disk Usage ==="
df -h /

AVAIL_KB=$(df -k --output=avail / | tail -n1 | tr -d ' ')
AVAIL_GB=$((AVAIL_KB / 1024 / 1024))
echo "Available root disk space: ${AVAIL_GB} GB"
if [ "${AVAIL_GB}" -lt 40 ]; then
  echo "WARNING: Available disk space (${AVAIL_GB} GB) is below 40 GB; attempting swap/journal cleanup..."
  journalctl --vacuum-size=50M || true
  rm -rf /var/cache/* || true
  df -h /
fi
