#!/system/bin/sh
# Portable Stealth KSU - Virtual Wi-Fi Wrapper (eth0 -> wlan0) & Natural Battery Simulator
MODDIR=${0%/*}
WIFI_FLAG="/data/adb/portable_stealth_wifi_disabled"

# Wait for Android boot completion
while [ "$(getprop sys.boot_completed)" != "1" ]; do
  sleep 2
done
sleep 3

configure_virtual_wifi() {
  if [ -f "$WIFI_FLAG" ]; then
    return 0
  fi

  # Enable kernel-backed mac80211_hwsim / virt_wifi wrapper when available
  if [ -d /sys/class/net/eth0 ] && [ ! -d /sys/class/net/wlan0 ]; then
    ip link add link eth0 name wlan0 type virt_wifi 2>/dev/null || \
      modprobe virt_wifi 2>/dev/null || \
      modprobe mac80211_hwsim radios=2 2>/dev/null || true
  fi

  if [ -d /sys/class/net/wlan0 ]; then
    ip link set wlan0 up 2>/dev/null || true
  fi

  svc wifi enable 2>/dev/null || true
  cmd wifi set-wifi-enabled enabled 2>/dev/null || true
  # Register realistic 5GHz Home Wi-Fi SSID label for apps inspecting Wi-Fi state
  settings put global wifi_on 1 2>/dev/null || true
  cmd wifi connect-network "Home_WiFi_5G" open 2>/dev/null || true
}

configure_virtual_wifi

# Background natural discharging battery simulator (75% - 88%, status = 3 Discharging)
LEVEL=84
DIR=-1
while true; do
  dumpsys battery unplug 2>/dev/null || true
  dumpsys battery set ac 0 2>/dev/null || true
  dumpsys battery set usb 0 2>/dev/null || true
  dumpsys battery set wireless 0 2>/dev/null || true
  dumpsys battery set status 3 2>/dev/null || true
  dumpsys battery set level "$LEVEL" 2>/dev/null || true
  dumpsys battery set temp 315 2>/dev/null || true

  # Slight natural step oscillation between 75 and 88
  RND=$(( $(od -An -N1 -tu1 /dev/urandom 2>/dev/null | tr -d ' ') % 3 ))
  if [ "$RND" -eq 0 ]; then
    LEVEL=$((LEVEL + DIR))
  fi
  if [ "$LEVEL" -le 75 ]; then
    LEVEL=76
    DIR=1
  elif [ "$LEVEL" -ge 88 ]; then
    LEVEL=87
    DIR=-1
  fi

  # Re-assert virtual Wi-Fi periodically unless toggled to LAN mode from Launcher
  if [ ! -f "$WIFI_FLAG" ] && [ -d /sys/class/net/wlan0 ]; then
    ip link set wlan0 up 2>/dev/null || true
  fi

  sleep 45
done
