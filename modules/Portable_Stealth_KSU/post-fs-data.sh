#!/system/bin/sh
# Portable Stealth KSU - Early Boot Trace Scrubber (post-fs-data)
MODDIR=${0%/*}

RESETPROP=""
for BIN in /data/adb/ksu/bin/resetprop /data/adb/ksud /system/bin/resetprop resetprop; do
  if command -v "$BIN" >/dev/null 2>&1 || [ -x "$BIN" ]; then
    if [ "$BIN" = "/data/adb/ksud" ]; then
      RESETPROP="/data/adb/ksu/bin/resetprop"
    else
      RESETPROP="$BIN"
    fi
    break
  fi
done

if [ -z "$RESETPROP" ] || [ ! -x "$RESETPROP" ]; then
  exit 0
fi

# 1. Remove explicit QEMU / VirtIO / Android-x86 / Bliss / Lineage property traces
KNOWN_TRACES="
ro.kernel.qemu
ro.kernel.qemu.gles
ro.kernel.android.qemud
ro.boot.qemu
qemu.hw.mainkeys
qemu.sf.fake_camera
qemu.sf.lcd_density
init.svc.qemu-props
ro.hardware.virtual_device
ro.lineage.version
ro.lineage.display.version
ro.lineage.build.version
ro.lineage.device
ro.lineage.releasetype
ro.lineagelegal.url
ro.modversion
ro.bliss.version
ro.bliss.display.version
ro.bliss.device
ro.bliss.releasetype
ro.android_x86.version
"

for PROP in $KNOWN_TRACES; do
  "$RESETPROP" --delete "$PROP" 2>/dev/null || true
done

# 2. Dynamically scrub any remaining props leaking qemu/virtio/bliss/lineage/x86_emu traces
# (Preserve ro.product.cpu.abilist* so x86_64 + arm64 libndk_translation keeps running)
getprop | while IFS= read -r LINE; do
  NAME=$(echo "$LINE" | sed -n 's/^\[\([^]]*\)\]:.*$/\1/p')
  VAL=$(echo "$LINE" | sed -n 's/^\[[^]]*\]: \[\(.*\)\]$/\1/p')
  case "$NAME" in
    ro.product.cpu.abi*|ro.dalvik.vm.native.bridge|dalvik.vm.*|ro.boot.selinux)
      continue
      ;;
  esac
  if echo "$NAME $VAL" | grep -qiE 'qemu|virtio|android_x86|bliss|lineage'; then
    "$RESETPROP" --delete "$NAME" 2>/dev/null || true
  fi
done

# 3. Mask x86 / virtual hardware identifiers cleanly
"$RESETPROP" -n "ro.boot.verifiedbootstate" "green"
"$RESETPROP" -n "ro.boot.flash.locked" "1"
"$RESETPROP" -n "ro.boot.vbmeta.device_state" "locked"
"$RESETPROP" -n "ro.debuggable" "0"
"$RESETPROP" -n "ro.secure" "1"
"$RESETPROP" -n "ro.build.type" "user"
"$RESETPROP" -n "ro.build.tags" "release-keys"
