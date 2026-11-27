#!/usr/bin/env bash
set -euo pipefail

BUNDLE_DIR="$(realpath -m "${1:-dist_bundle}")"
IMG_DIR="${BUNDLE_DIR}/images"
WORK_DIR="/tmp/lineage_work"
cleanup_mounts() {
  umount -lf "${WORK_DIR}/mnt" 2>/dev/null || true
  umount -lf "${WORK_DIR}/vendor_mnt" 2>/dev/null || true
  umount -lf "${WORK_DIR}/bliss_mnt" 2>/dev/null || true
  umount -lf "${WORK_DIR}/ext4_tmp" 2>/dev/null || true
}
trap cleanup_mounts EXIT
mkdir -p "${IMG_DIR}" "${WORK_DIR}/mnt" "${WORK_DIR}/vendor_mnt" "${WORK_DIR}/bliss_mnt"

RAW_SYS="${WORK_DIR}/system_raw.img"
GSI_URL="${LINEAGE_GSI_URL:-}"
GSI_SOURCE_LABEL="User Override"

echo "=== [1/5] Acquiring VM-Bootable Android 13 (API 33) x86_64 GApps System Image ==="
if [ -z "${GSI_URL}" ]; then
  # 1) Check AndyYan LineageOS 20 GSI SourceForge RSS strictly for genuine x86_64 + GApps (NO arm64/vanilla/waydroid-LXC)
  for SF_DIR in "/lineage-20-td" "/lineage-20-light" "/lineage-20"; do
    SF_XML=$(curl -fsSL "https://sourceforge.net/projects/andyyan-gsi/rss?path=${SF_DIR}" 2>/dev/null || true)
    CANDIDATE=$(echo "${SF_XML}" | grep -oE 'https://sourceforge\.net/projects/andyyan-gsi/files/[^"<]+\.(img\.xz|img\.gz|zip|7z|img)/download' | \
      grep -iE 'lineage[-_]?20' | grep -iE 'x86_64' | grep -iE '(_bgN|_bgS|_gN|_gS|gapps)' | \
      grep -ivE '(arm64|a64|arm32|bvN|bvS|vanilla|waydroid)' | head -n1 || true)
    if [ -n "${CANDIDATE}" ]; then
      GSI_URL="${CANDIDATE}"
      GSI_SOURCE_LABEL="AndyYan GSI (${SF_DIR})"
      break
    fi
  done
fi

if [ -z "${GSI_URL}" ]; then
  # 2) Check GitHub Treble/GSI releases strictly matching non-Waydroid Android 13 x86_64 GApps
  for REPO in "AndyYan/lineage_build_config" "MisterZtr/LineageOS_gsi" "TrebleDroid/treble_experimentations"; do
    CANDIDATE=$(curl -fsSL "https://api.github.com/repos/${REPO}/releases?per_page=15" 2>/dev/null | \
      jq -r '.[].assets[] | select((.name | test("(lineage[-_]?20|android[-_]?13)"; "i")) and (.name | test("x86_64"; "i")) and (.name | test("(bgN|bgS|gapps)"; "i")) and (.name | test("(arm64|a64|arm32|bvN|bvS|vanilla|waydroid)"; "i") | not) and (.name | test("\\.(img\\.xz|img\\.gz|zip|7z|img)$"; "i"))) | .browser_download_url' | head -n1 || true)
    if [ -n "${CANDIDATE}" ] && [ "${CANDIDATE}" != "null" ]; then
      GSI_URL="${CANDIDATE}"
      GSI_SOURCE_LABEL="GitHub ${REPO}"
      break
    fi
  done
fi

if [ -n "${GSI_URL}" ]; then
  echo "Downloading LineageOS 20.0 x86_64 GApps [${GSI_SOURCE_LABEL}] via aria2c (16 connections): ${GSI_URL}"
  if aria2c -x 16 -s 16 -k 1M --user-agent="Wget/1.21.4" --max-tries=4 --retry-wait=5 -d "${WORK_DIR}" -o "lineage20_dl" "${GSI_URL}"; then
    GSI_BYTES=$(stat -c%s "${WORK_DIR}/lineage20_dl" 2>/dev/null || echo 0)
    GSI_TYPE=$(file -b "${WORK_DIR}/lineage20_dl" 2>/dev/null || echo "unknown")
    if [ "${GSI_BYTES}" -lt 104857600 ] || echo "${GSI_TYPE}" | grep -qiE 'HTML|ASCII text'; then
      echo "WARNING [LineageOS-20]: Downloaded file failed integrity check (> 100MB required for GApps build)!" >&2
      echo "  Broken URL   : ${GSI_URL}" >&2
      echo "  Actual Size  : ${GSI_BYTES} bytes" >&2
      echo "  Detected Type: ${GSI_TYPE}" >&2
      rm -f "${WORK_DIR}/lineage20_dl"
    else
      echo "Verified [LineageOS-20 GApps]: ${GSI_BYTES} bytes (${GSI_TYPE})"
    fi
  else
    echo "WARNING [LineageOS-20]: aria2c failed for URL: ${GSI_URL}" >&2
    rm -f "${WORK_DIR}/lineage20_dl"
  fi
fi

if [ -f "${WORK_DIR}/lineage20_dl" ]; then
  FILE_MAGIC=$(file -b "${WORK_DIR}/lineage20_dl")
  if echo "${FILE_MAGIC}" | grep -qiE 'Zip|7-zip'; then
    7z x "${WORK_DIR}/lineage20_dl" -o"${WORK_DIR}/ext" -y >/dev/null
    FOUND_IMG=$(find "${WORK_DIR}/ext" -type f \( -name "system.img" -o -name "*.img" \) | sort | head -n1)
    if [ -z "${FOUND_IMG}" ]; then
      echo "ERROR: Archive did not contain a system .img file." >&2
      exit 1
    fi
    mv "${FOUND_IMG}" "${RAW_SYS}"
    rm -rf "${WORK_DIR}/ext" "${WORK_DIR}/lineage20_dl"
  elif echo "${FILE_MAGIC}" | grep -qi 'XZ'; then
    xz -dc "${WORK_DIR}/lineage20_dl" > "${RAW_SYS}"
    rm -f "${WORK_DIR}/lineage20_dl"
  elif echo "${FILE_MAGIC}" | grep -qi 'gzip'; then
    gzip -dc "${WORK_DIR}/lineage20_dl" > "${RAW_SYS}"
    rm -f "${WORK_DIR}/lineage20_dl"
  else
    mv "${WORK_DIR}/lineage20_dl" "${RAW_SYS}"
  fi
elif [ -f "/tmp/bliss_system_fallback.img" ]; then
  echo "Notice: Using genuine VM-bootable Bliss OS 16.9 (Android 13 / API 33) x86_64 GApps system.img."
  cp -f "/tmp/bliss_system_fallback.img" "${RAW_SYS}"
else
  echo "ERROR: No valid Android 13 (API 33) x86_64 system.img source available." >&2
  exit 1
fi

echo "=== [2/5] Converting Sparse / EROFS Image & Preparing ext4 (+512MB GApps Headroom) ==="
if file -b "${RAW_SYS}" | grep -qi "Android sparse image"; then
  echo "Converting Android sparse image to raw filesystem image..."
  simg2img "${RAW_SYS}" "${RAW_SYS}.unsparse"
  mv -f "${RAW_SYS}.unsparse" "${RAW_SYS}"
fi

if file -b "${RAW_SYS}" | grep -qi "EROFS" || blkid -o value -s TYPE "${RAW_SYS}" 2>/dev/null | grep -qi "erofs"; then
  echo "Detected read-only EROFS system.img; extracting with fsck.erofs and repacking as writable ext4..."
  rm -rf "${WORK_DIR}/erofs_root" "${WORK_DIR}/ext4_tmp"
  fsck.erofs --extract="${WORK_DIR}/erofs_root" "${RAW_SYS}"
  EXT_MB=$(du -sm "${WORK_DIR}/erofs_root" | awk '{print $1 + 768}')
  dd if=/dev/zero of="${RAW_SYS}.ext4" bs=1M count="${EXT_MB}" status=none
  mkfs.ext4 -F -L system "${RAW_SYS}.ext4" >/dev/null
  mkdir -p "${WORK_DIR}/ext4_tmp"
  mount -o loop,rw "${RAW_SYS}.ext4" "${WORK_DIR}/ext4_tmp"
  cp -a "${WORK_DIR}/erofs_root/." "${WORK_DIR}/ext4_tmp/"
  sync
  umount "${WORK_DIR}/ext4_tmp"
  mv -f "${RAW_SYS}.ext4" "${RAW_SYS}"
  rm -rf "${WORK_DIR}/erofs_root" "${WORK_DIR}/ext4_tmp"
fi

e2fsck -f -y "${RAW_SYS}" || true
CURRENT_BYTES=$(stat -c%s "${RAW_SYS}")
NEW_SIZE_MB=$(( (CURRENT_BYTES / 1024 / 1024) + 512 ))
truncate -s "${NEW_SIZE_MB}M" "${RAW_SYS}"
resize2fs "${RAW_SYS}"
e2fsck -f -y "${RAW_SYS}" || true

echo "=== [3/5] Mounting system.img, Verifying x86_64 API 33 + GApps, Bridging Bliss 16.9 HALs & PID-1 Wrapper ==="
mount -o loop,rw "${RAW_SYS}" "${WORK_DIR}/mnt"

SYS_ROOT="${WORK_DIR}/mnt"
if [ -d "${WORK_DIR}/mnt/system/bin" ] && [ -f "${WORK_DIR}/mnt/system/build.prop" ]; then
  SYS_ROOT="${WORK_DIR}/mnt/system"
  echo "Detected System-as-Root (SAR) layout at ${WORK_DIR}/mnt (SYS_ROOT=${SYS_ROOT})"
else
  echo "Detected non-SAR layout at ${WORK_DIR}/mnt (creating SAR /system compatibility view if needed)"
fi

if [ ! -e "${SYS_ROOT}/bin/init" ]; then
  echo "ERROR: ${SYS_ROOT}/bin/init not found inside system.img!" >&2
  exit 1
fi
INIT_ARCH=$(file -b "${SYS_ROOT}/bin/init" || echo "unknown")
echo "Verified system /bin/init architecture: ${INIT_ARCH}"
if ! echo "${INIT_ARCH}" | grep -qiE 'ELF 64-bit.*x86-64' || echo "${INIT_ARCH}" | grep -qiE 'ARM|aarch64'; then
  echo "ERROR: system.img /bin/init is NOT x86-64 ELF (${INIT_ARCH})! Rejecting non-x86_64 image." >&2
  exit 1
fi
if command -v readelf >/dev/null 2>&1; then
  echo "Inspecting /bin/init ELF PT_INTERP:"
  readelf -l "${SYS_ROOT}/bin/init" 2>/dev/null | grep -E 'ELF file type|Requesting program interpreter' || echo "  (static ELF or no PT_INTERP)"
fi
ls -ld "${SYS_ROOT}/bin/linker"* "${SYS_ROOT}/bin/bootstrap/linker"* 2>/dev/null || true

PROP_FILE=""
for CANDIDATE_PROP in "${WORK_DIR}/mnt/system/build.prop" "${WORK_DIR}/mnt/build.prop"; do
  if [ -f "${CANDIDATE_PROP}" ]; then
    PROP_FILE="${CANDIDATE_PROP}"
    break
  fi
done

if [ -z "${PROP_FILE}" ]; then
  echo "ERROR: Could not locate build.prop inside mounted system.img" >&2
  exit 1
fi

SYS_SDK=$(grep -E '^ro\.build\.version\.sdk=' "${PROP_FILE}" | head -n1 | cut -d= -f2 | tr -d '[:space:]' || true)
SYS_REL=$(grep -E '^ro\.build\.version\.release=' "${PROP_FILE}" | head -n1 | cut -d= -f2 | tr -d '[:space:]' || true)
echo "Detected system.img Android version=${SYS_REL:-unknown}, SDK API=${SYS_SDK:-unknown}"
if [ -n "${SYS_SDK}" ] && [ "${SYS_SDK}" != "33" ]; then
  echo "WARNING: Expected API 33 (Android 13) for 1:1 Bliss OS 16.9 parity, detected API ${SYS_SDK}." >&2
fi

if [ -z "${LINEAGE_GSI_URL:-}" ]; then
  if [ -f "${SYS_ROOT}/etc/init/waydroid.rc" ] || grep -qiE 'waydroid' "${PROP_FILE}" 2>/dev/null; then
    echo "ERROR: Rejected Waydroid LXC-container system.img (its /system/bin/init omits /proc, /dev, ueventd, and binderfs mounts and cannot boot a real QEMU VM)." >&2
    exit 1
  fi
fi

GAPPS_LIST=$(find "${WORK_DIR}/mnt" -maxdepth 6 \( -iname "*Phonesky*.apk" -o -iname "*GmsCore*.apk" -o -iname "*GoogleServicesFramework*.apk" \) 2>/dev/null || true)
if [ -n "${GAPPS_LIST}" ]; then
  echo "Verified GApps packages present inside system.img:"
  echo "${GAPPS_LIST}" | sed 's/^/  - /'
else
  echo "WARNING: Standard GApps APKs not detected by filename under ${WORK_DIR}/mnt (continuing)." >&2
fi

echo "Patching ${PROP_FILE} for Intel HD 4000 OpenGL 4.0 / DirectX 11 ANGLE (No Vulkan)..."
sed -i '/^debug\.hwui\.renderer=/d' "${PROP_FILE}"
sed -i '/^ro\.hwui\.use_vulkan=/d' "${PROP_FILE}"
sed -i '/^persist\.sys\.ui\.hw=/d' "${PROP_FILE}"
sed -i '/^debug\.sf\.hw=/d' "${PROP_FILE}"
sed -i '/^ro\.hardware\.egl=/d' "${PROP_FILE}"
sed -i '/^ro\.opengles\.version=/d' "${PROP_FILE}"
sed -i '/^ro\.product\.cpu\.abilist=/d' "${PROP_FILE}"
sed -i '/^ro\.product\.cpu\.abilist64=/d' "${PROP_FILE}"
sed -i '/^ro\.dalvik\.vm\.native\.bridge=/d' "${PROP_FILE}"

cat <<'EOF' >> "${PROP_FILE}"

# Intel HD Graphics 4000 (Ivy Bridge) OpenGL ES / ANGLE Optimization (No Vulkan)
debug.hwui.renderer=opengl
ro.hwui.use_vulkan=false
persist.sys.ui.hw=1
debug.sf.hw=1
ro.hardware.egl=mesa
ro.opengles.version=196608

# Enable ARM64-v8a / ARMv7a Native Bridge Translation on x86_64
ro.product.cpu.abilist=x86_64,x86,arm64-v8a,armeabi-v7a,armeabi
ro.product.cpu.abilist64=x86_64,arm64-v8a
ro.dalvik.vm.native.bridge=libndk_translation.so
EOF

# Ensure all required Android root directories, real /sbin dir, and /init symlink exist
for ROOT_SUB in dev proc sys mnt vendor data metadata apex linkerconfig debug_ramdisk first_stage_ramdisk tmp; do
  if [ -L "${WORK_DIR}/mnt/${ROOT_SUB}" ] || { [ -e "${WORK_DIR}/mnt/${ROOT_SUB}" ] && [ ! -d "${WORK_DIR}/mnt/${ROOT_SUB}" ]; }; then
    rm -f "${WORK_DIR}/mnt/${ROOT_SUB}"
  fi
  mkdir -p "${WORK_DIR}/mnt/${ROOT_SUB}"
done
if [ -L "${WORK_DIR}/mnt/sbin" ]; then
  rm -f "${WORK_DIR}/mnt/sbin"
fi
mkdir -p "${WORK_DIR}/mnt/sbin"
if [ "${SYS_ROOT}" = "${WORK_DIR}/mnt" ] && [ -d "${WORK_DIR}/mnt/bin" ] && [ ! -e "${WORK_DIR}/mnt/system/bin" ]; then
  rmdir "${WORK_DIR}/mnt/system" 2>/dev/null || true
  [ -e "${WORK_DIR}/mnt/system" ] || ln -sfn . "${WORK_DIR}/mnt/system"
fi
if [ ! -e "${WORK_DIR}/mnt/init" ] && [ -x "${SYS_ROOT}/bin/init" ]; then
  ln -sf /system/bin/init "${WORK_DIR}/mnt/init"
fi

# Mount Bliss 16.9 fallback system.img (ro) & vendor.img (rw) to bridge fstab/HAL/SELinux
BLISS_SYS_ROOT=""
if [ -s "/tmp/bliss_system_fallback.img" ]; then
  if file -b "/tmp/bliss_system_fallback.img" | grep -qi "Android sparse image"; then
    simg2img "/tmp/bliss_system_fallback.img" "${WORK_DIR}/bliss_unsparse.img"
    mv -f "${WORK_DIR}/bliss_unsparse.img" "/tmp/bliss_system_fallback.img"
  fi
  if mount -o loop,ro "/tmp/bliss_system_fallback.img" "${WORK_DIR}/bliss_mnt" 2>/dev/null; then
    if [ -d "${WORK_DIR}/bliss_mnt/system/etc" ]; then
      BLISS_SYS_ROOT="${WORK_DIR}/bliss_mnt/system"
    elif [ -d "${WORK_DIR}/bliss_mnt/etc" ]; then
      BLISS_SYS_ROOT="${WORK_DIR}/bliss_mnt"
    fi
    echo "Mounted Bliss OS 16.9 fallback reference (BLISS_SYS_ROOT=${BLISS_SYS_ROOT})"
  fi
fi

VENDOR_RAW="${WORK_DIR}/vendor_raw.img"
HAS_VENDOR_RW=0
if [ -s "${IMG_DIR}/vendor.img" ]; then
  qemu-img convert -O raw "${IMG_DIR}/vendor.img" "${VENDOR_RAW}"
  e2fsck -f -y "${VENDOR_RAW}" || true
  V_BYTES=$(stat -c%s "${VENDOR_RAW}")
  V_NEW_MB=$(( (V_BYTES / 1024 / 1024) + 64 ))
  truncate -s "${V_NEW_MB}M" "${VENDOR_RAW}"
  resize2fs "${VENDOR_RAW}" >/dev/null 2>&1 || true
  if mount -o loop,rw "${VENDOR_RAW}" "${WORK_DIR}/vendor_mnt"; then
    HAS_VENDOR_RW=1
    echo "Mounted Bliss 16.9 vendor.img read-write for VirtIO fstab & API-33 SELinux reconciliation."
  fi
fi

# Bridge Bliss x86_64 fstab & hardware init scripts (no nomblk_io_submit on Linux 6.1 ext4)
FSTAB_CONTENT='# VirtIO Portable Android 13 (API 33) fstab (bridged for Bliss initrd pre-mounts)
/dev/block/vdc /data ext4 noatime,nosuid,nodev,errors=remount-ro wait,latemount
'
mkdir -p "${SYS_ROOT}/etc/init/hw" "${WORK_DIR}/mnt/first_stage_ramdisk"
printf '%s' "${FSTAB_CONTENT}" > "${WORK_DIR}/mnt/fstab.android_x86_64"
printf '%s' "${FSTAB_CONTENT}" > "${SYS_ROOT}/etc/fstab.android_x86_64"
printf '%s' "${FSTAB_CONTENT}" > "${WORK_DIR}/mnt/first_stage_ramdisk/fstab.android_x86_64"
chmod 0644 "${WORK_DIR}/mnt/fstab.android_x86_64" "${SYS_ROOT}/etc/fstab.android_x86_64" "${WORK_DIR}/mnt/first_stage_ramdisk/fstab.android_x86_64" 2>/dev/null || true

# Ensure no stray first_stage_mount entries remain in first_stage_ramdisk fstab files
for FSTAB_EXTRA in "${WORK_DIR}/mnt/first_stage_ramdisk"/fstab.*; do
  [ -f "${FSTAB_EXTRA}" ] || continue
  sed -i '/first_stage_mount/d' "${FSTAB_EXTRA}" 2>/dev/null || true
done

if [ "${HAS_VENDOR_RW}" -eq 1 ]; then
  mkdir -p "${WORK_DIR}/vendor_mnt/etc/init/hw"
  printf '%s' "${FSTAB_CONTENT}" > "${WORK_DIR}/vendor_mnt/etc/fstab.android_x86_64"
  for V_FSTAB in "${WORK_DIR}/vendor_mnt/etc"/fstab.*; do
    [ -f "${V_FSTAB}" ] || continue
    if [ "$(basename "${V_FSTAB}")" != "fstab.android_x86_64" ]; then
      sed -i '/first_stage_mount/d' "${V_FSTAB}" 2>/dev/null || true
    fi
  done
  for RC_CAND in \
    "/tmp/bliss_donor_meta/init.android_x86_64.rc" \
    "${WORK_DIR}/bliss_mnt/init.android_x86_64.rc" \
    "${BLISS_SYS_ROOT:+${BLISS_SYS_ROOT}/etc/init/hw/init.android_x86_64.rc}" \
    "${BLISS_SYS_ROOT:+${BLISS_SYS_ROOT}/vendor/etc/init/hw/init.android_x86_64.rc}"; do
    if [ -n "${RC_CAND}" ] && [ -f "${RC_CAND}" ] && [ ! -f "${WORK_DIR}/vendor_mnt/etc/init/hw/init.android_x86_64.rc" ]; then
      cp -f "${RC_CAND}" "${WORK_DIR}/vendor_mnt/etc/init/hw/init.android_x86_64.rc"
      echo "Bridged Bliss 16.9 init.android_x86_64.rc -> vendor/etc/init/hw/"
      break
    fi
  done
  if [ -f "/tmp/bliss_donor_meta/ueventd.android_x86_64.rc" ] && [ ! -f "${WORK_DIR}/vendor_mnt/etc/ueventd.rc" ]; then
    cp -f "/tmp/bliss_donor_meta/ueventd.android_x86_64.rc" "${WORK_DIR}/vendor_mnt/etc/ueventd.rc"
  fi
  if [ ! -f "${WORK_DIR}/vendor_mnt/etc/init/hw/init.android_x86_64.rc" ]; then
    cat <<'EOF' > "${WORK_DIR}/vendor_mnt/etc/init/hw/init.android_x86_64.rc"
on early-init
    chmod 0666 /dev/binder
    chmod 0666 /dev/hwbinder
    chmod 0666 /dev/vndbinder
    chmod 0666 /dev/binderfs/binder
    chmod 0666 /dev/binderfs/hwbinder
    chmod 0666 /dev/binderfs/vndbinder

on fs
    mount_all /vendor/etc/fstab.android_x86_64 --early

on late-fs
    mount_all /vendor/etc/fstab.android_x86_64 --late

on boot
    setprop ro.hardware.egl mesa
    setprop debug.hwui.renderer opengl
    setprop ro.hwui.use_vulkan false
    setprop persist.sys.usb.config adb
EOF
  fi
  chmod 0644 "${WORK_DIR}/vendor_mnt/etc/fstab.android_x86_64" "${WORK_DIR}/vendor_mnt/etc/init/hw/init.android_x86_64.rc" 2>/dev/null || true

  # SELinux CIL Compatibility Reconciliation (LineageOS 20.0 API 33 system + Bliss 16.9 API 33 vendor)
  SYS_SE_DIR="${SYS_ROOT}/etc/selinux"
  VEN_SE_DIR="${WORK_DIR}/vendor_mnt/etc/selinux"
  if [ -d "${SYS_SE_DIR}" ] && [ -d "${VEN_SE_DIR}" ]; then
    PLAT_VER=$(cat "${VEN_SE_DIR}/plat_sepolicy_vers.txt" 2>/dev/null | tr -d '[:space:]' || echo "")
    LATEST_MAP=$(ls -1 "${SYS_SE_DIR}/mapping/"*.cil 2>/dev/null | grep -v '\.compat\.' | sort -V | tail -n1 | xargs -r basename | sed 's/\.cil$//' || echo "")
    echo "SELinux versions: vendor plat_sepolicy_vers=${PLAT_VER:-none}, system latest mapping=${LATEST_MAP:-none}"
    if [ -n "${PLAT_VER}" ] && [ -n "${LATEST_MAP}" ] && [ ! -f "${SYS_SE_DIR}/mapping/${PLAT_VER}.cil" ]; then
      echo "Reconciling missing mapping/${PLAT_VER}.cil -> ${LATEST_MAP}.cil"
      cp -f "${SYS_SE_DIR}/mapping/${LATEST_MAP}.cil" "${SYS_SE_DIR}/mapping/${PLAT_VER}.cil"
      if [ -f "${SYS_SE_DIR}/mapping/${LATEST_MAP}.compat.cil" ]; then
        cp -f "${SYS_SE_DIR}/mapping/${LATEST_MAP}.compat.cil" "${SYS_SE_DIR}/mapping/${PLAT_VER}.compat.cil"
      fi
    fi
    if [ -n "${PLAT_VER}" ]; then
      for PART_SE in \
        "${WORK_DIR}/mnt/system_ext/etc/selinux" \
        "${SYS_ROOT}/system_ext/etc/selinux" \
        "${WORK_DIR}/mnt/product/etc/selinux" \
        "${SYS_ROOT}/product/etc/selinux"; do
        if [ -d "${PART_SE}/mapping" ] && [ ! -f "${PART_SE}/mapping/${PLAT_VER}.cil" ]; then
          PART_LATEST=$(ls -1 "${PART_SE}/mapping/"*.cil 2>/dev/null | grep -v '\.compat\.' | sort -V | tail -n1 | xargs -r basename | sed 's/\.cil$//' || echo "")
          if [ -n "${PART_LATEST}" ] && [ -f "${PART_SE}/mapping/${PART_LATEST}.cil" ]; then
            cp -f "${PART_SE}/mapping/${PART_LATEST}.cil" "${PART_SE}/mapping/${PLAT_VER}.cil"
            echo "Reconciled ${PART_SE}/mapping/${PLAT_VER}.cil -> ${PART_LATEST}.cil"
          fi
        fi
      done
    fi

    # Remove Bliss precompiled_sepolicy so Android SetupSelinux compiles cleanly with LineageOS 20 system CILs
    rm -f "${VEN_SE_DIR}/precompiled_sepolicy"*

    if command -v secilc >/dev/null 2>&1; then
      CIL_LIST=()
      [ -f "${SYS_SE_DIR}/plat_sepolicy.cil" ] && CIL_LIST+=("${SYS_SE_DIR}/plat_sepolicy.cil")
      [ -n "${PLAT_VER}" ] && [ -f "${SYS_SE_DIR}/mapping/${PLAT_VER}.cil" ] && CIL_LIST+=("${SYS_SE_DIR}/mapping/${PLAT_VER}.cil")
      [ -n "${PLAT_VER}" ] && [ -f "${SYS_SE_DIR}/mapping/${PLAT_VER}.compat.cil" ] && CIL_LIST+=("${SYS_SE_DIR}/mapping/${PLAT_VER}.compat.cil")
      for SE_CAND in \
        "${WORK_DIR}/mnt/system_ext/etc/selinux/system_ext_sepolicy.cil" \
        "${SYS_ROOT}/system_ext/etc/selinux/system_ext_sepolicy.cil" \
        "${WORK_DIR}/mnt/system_ext/etc/selinux/mapping/${PLAT_VER}.cil" \
        "${SYS_ROOT}/system_ext/etc/selinux/mapping/${PLAT_VER}.cil" \
        "${WORK_DIR}/mnt/product/etc/selinux/product_sepolicy.cil" \
        "${SYS_ROOT}/product/etc/selinux/product_sepolicy.cil" \
        "${WORK_DIR}/mnt/product/etc/selinux/mapping/${PLAT_VER}.cil" \
        "${SYS_ROOT}/product/etc/selinux/mapping/${PLAT_VER}.cil"; do
        [ -n "${PLAT_VER}" ] && [ -f "${SE_CAND}" ] && CIL_LIST+=("${SE_CAND}")
      done
      [ -f "${VEN_SE_DIR}/plat_pub_versioned.cil" ] && CIL_LIST+=("${VEN_SE_DIR}/plat_pub_versioned.cil")
      [ -f "${VEN_SE_DIR}/vendor_sepolicy.cil" ] && CIL_LIST+=("${VEN_SE_DIR}/vendor_sepolicy.cil")

      if [ "${#CIL_LIST[@]}" -gt 0 ]; then
        echo "Validating combined API-33 SELinux CIL policy with secilc -m (${#CIL_LIST[@]} files)..."
        if secilc -m -M true -G -N -c 30 "${CIL_LIST[@]}" -o "${WORK_DIR}/test_policy" -f /dev/null 2>"${WORK_DIR}/secilc.err"; then
          echo "Verified SELinux CIL compilation succeeded cleanly!"
          rm -f "${WORK_DIR}/test_policy"
        else
          echo "WARNING: secilc -m reported issues on mixed LineageOS 20 + Bliss 16.9 CIL files:"
          head -n 25 "${WORK_DIR}/secilc.err" || true
          echo "Running intelligent CIL conflict healer (deduplicating conflicting symbols while preserving vendor types)..."
          python3 - "${VEN_SE_DIR}" "${WORK_DIR}/secilc.err" "${SYS_SE_DIR}" "${PLAT_VER}" "${WORK_DIR}/mnt" "${SYS_ROOT}" <<'CILPY'
import pathlib, re, subprocess, sys

ven_dir = pathlib.Path(sys.argv[1])
err_file = pathlib.Path(sys.argv[2])
sys_se_dir = pathlib.Path(sys.argv[3])
plat_ver = sys.argv[4]
mnt_root = pathlib.Path(sys.argv[5])
sys_root = pathlib.Path(sys.argv[6])

cil_files = []
for cand in [
    sys_se_dir / "plat_sepolicy.cil",
    sys_se_dir / "mapping" / f"{plat_ver}.cil" if plat_ver else None,
    sys_se_dir / "mapping" / f"{plat_ver}.compat.cil" if plat_ver else None,
    mnt_root / "system_ext/etc/selinux/system_ext_sepolicy.cil",
    sys_root / "system_ext/etc/selinux/system_ext_sepolicy.cil",
    mnt_root / f"system_ext/etc/selinux/mapping/{plat_ver}.cil" if plat_ver else None,
    sys_root / f"system_ext/etc/selinux/mapping/{plat_ver}.cil" if plat_ver else None,
    mnt_root / "product/etc/selinux/product_sepolicy.cil",
    sys_root / "product/etc/selinux/product_sepolicy.cil",
    mnt_root / f"product/etc/selinux/mapping/{plat_ver}.cil" if plat_ver else None,
    sys_root / f"product/etc/selinux/mapping/{plat_ver}.cil" if plat_ver else None,
    ven_dir / "plat_pub_versioned.cil",
    ven_dir / "vendor_sepolicy.cil",
]:
    if cand and cand.is_file() and str(cand) not in cil_files:
        cil_files.append(str(cand))

ven_targets = [p for p in (ven_dir / "plat_pub_versioned.cil", ven_dir / "vendor_sepolicy.cil") if p.is_file()]

def comment_line(path: pathlib.Path, line_no: int) -> bool:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
    idx = line_no - 1
    if 0 <= idx < len(lines) and not lines[idx].lstrip().startswith(";"):
        # Only comment standalone single-line statements cleanly; for multi-line blocks, balance parens
        depth = lines[idx].count("(") - lines[idx].count(")")
        end = idx
        while depth > 0 and end + 1 < len(lines):
            end += 1
            depth += lines[end].count("(") - lines[end].count(")")
        for j in range(idx, end + 1):
            if not lines[j].lstrip().startswith(";"):
                lines[j] = "; healed: " + lines[j]
        path.write_text("".join(lines), encoding="utf-8")
        return True
    return False

for attempt in range(150):
    proc = subprocess.run(
        ["secilc", "-m", "-M", "true", "-G", "-N", "-c", "30", *cil_files, "-o", "/tmp/healed_policy.bin", "-f", "/dev/null"],
        capture_output=True, text=True
    )
    if proc.returncode == 0:
        print(f"SELinux CIL healed cleanly after {attempt} iteration(s)!")
        pathlib.Path("/tmp/healed_policy.bin").unlink(missing_ok=True)
        sys.exit(0)
    err_txt = (proc.stderr or "") + "\n" + (proc.stdout or "")
    changed = False
    for m in re.finditer(r"([^\s:]+\.cil):(\d+):", err_txt):
        fpath = pathlib.Path(m.group(1))
        lno = int(m.group(2))
        if fpath in ven_targets:
            if comment_line(fpath, lno):
                changed = True
                break
    if not changed:
        # Handle 'Duplicate declaration' where first/second location is on vendor CIL
        dup = re.search(r"(?:Duplicate|Multiple) declaration.*?at ([^\s:]+\.cil):(\d+)", err_txt, re.S)
        if dup:
            fpath = pathlib.Path(dup.group(1))
            lno = int(dup.group(2))
            if fpath in ven_targets and comment_line(fpath, lno):
                changed = True
    if not changed:
        print("CIL healer could not isolate further lines; preserving vendor CILs.")
        break
CILPY
        fi
      fi
    fi
  fi
fi

# Compile pure -nostdlib static x86_64 PID-1 /init diagnostic wrapper (zero glibc/AVX/IFUNC overhead)
echo "Compiling pure -nostdlib static PID-1 /init wrapper (/sbin/droidport_init_wrapper)..."
cat <<'CEOF' > "${WORK_DIR}/droidport_init_wrapper.c"
#define _GNU_SOURCE
#include <fcntl.h>
#include <stddef.h>
#include <stdint.h>
#include <sys/stat.h>
#include <sys/syscall.h>

#ifndef F_OK
#define F_OK 0
#define X_OK 1
#endif
#ifndef SEEK_END
#define SEEK_END 2
#endif
#ifndef EAGAIN
#define EAGAIN 11
#define EWOULDBLOCK 11
#define EINTR 4
#define EPIPE 32
#endif

struct dp_timespec {
    long tv_sec;
    long tv_nsec;
};

static inline long sc0(long n) {
    long ret;
    __asm__ volatile("syscall" : "=a"(ret) : "a"(n) : "rcx", "r11", "memory");
    return ret;
}
static inline long sc1(long n, long a1) {
    long ret;
    __asm__ volatile("syscall" : "=a"(ret) : "a"(n), "D"(a1) : "rcx", "r11", "memory");
    return ret;
}
static inline long sc2(long n, long a1, long a2) {
    long ret;
    __asm__ volatile("syscall" : "=a"(ret) : "a"(n), "D"(a1), "S"(a2) : "rcx", "r11", "memory");
    return ret;
}
static inline long sc3(long n, long a1, long a2, long a3) {
    long ret;
    __asm__ volatile("syscall" : "=a"(ret) : "a"(n), "D"(a1), "S"(a2), "d"(a3) : "rcx", "r11", "memory");
    return ret;
}
static inline long sc5(long n, long a1, long a2, long a3, long a4, long a5) {
    long ret;
    register long r10 __asm__("r10") = a4;
    register long r8 __asm__("r8") = a5;
    __asm__ volatile("syscall" : "=a"(ret) : "a"(n), "D"(a1), "S"(a2), "d"(a3), "r"(r10), "r"(r8) : "rcx", "r11", "memory");
    return ret;
}

static size_t dp_strlen(const char *s) {
    size_t n = 0;
    while (s[n]) n++;
    return n;
}

static char *dp_strchr(const char *s, int c) {
    while (*s) {
        if (*s == (char)c) return (char *)s;
        s++;
    }
    return NULL;
}

static int dp_strstr(const char *hay, const char *needle) {
    size_t nlen = dp_strlen(needle);
    if (!nlen) return 1;
    for (; *hay; hay++) {
        size_t i = 0;
        while (i < nlen && hay[i] && hay[i] == needle[i]) i++;
        if (i == nlen) return 1;
    }
    return 0;
}

static size_t dp_push_str(char *dst, size_t off, size_t cap, const char *s) {
    while (*s && off + 1 < cap) dst[off++] = *s++;
    dst[off] = '\0';
    return off;
}

static size_t dp_push_num(char *dst, size_t off, size_t cap, long val, int base) {
    char tmp[32];
    int i = 0;
    unsigned long uv;
    if (val < 0 && base == 10) {
        if (off + 1 < cap) dst[off++] = '-';
        uv = (unsigned long)(-val);
    } else {
        uv = (unsigned long)val;
    }
    if (uv == 0) tmp[i++] = '0';
    while (uv > 0 && i < 31) {
        tmp[i++] = (char)('0' + (uv % (unsigned long)base));
        uv /= (unsigned long)base;
    }
    while (i > 0 && off + 1 < cap) dst[off++] = tmp[--i];
    dst[off] = '\0';
    return off;
}

static void dp_usleep(long usec) {
    struct dp_timespec ts;
    ts.tv_sec = usec / 1000000L;
    ts.tv_nsec = (usec % 1000000L) * 1000L;
    sc2(SYS_nanosleep, (long)&ts, 0);
}

static int g_tty = -1;
static int g_kmsg = -1;

static void safe_write_all(int fd, const char *buf, size_t len) {
    size_t off = 0;
    int retries = 0;
    while (off < len && retries < 200) {
        long n = sc3(SYS_write, fd, (long)(buf + off), (long)(len - off));
        if (n > 0) {
            off += (size_t)n;
            continue;
        }
        long err = -n;
        if (n < 0 && (err == EAGAIN || err == EWOULDBLOCK || err == EINTR)) {
            dp_usleep(1000);
            retries++;
            continue;
        }
        break;
    }
}

static void write_line(const char *msg) {
    size_t len = dp_strlen(msg);
    int out_fd = (g_tty >= 0) ? g_tty : 2;
    safe_write_all(out_fd, msg, len);
    safe_write_all(out_fd, "\n", 1);
    if (g_kmsg >= 0) {
        char kbuf[512];
        size_t o = 0;
        o = dp_push_str(kbuf, o, sizeof(kbuf), "<6>");
        o = dp_push_str(kbuf, o, sizeof(kbuf), msg);
        o = dp_push_str(kbuf, o, sizeof(kbuf), "\n");
        safe_write_all(g_kmsg, kbuf, o);
    }
}

static void check_path(const char *label, const char *path) {
    struct stat st;
    char buf[384];
    size_t o = 0;
    long r = sc2(SYS_lstat, (long)path, (long)&st);
    if (r == 0) {
        long xok = (sc2(SYS_access, (long)path, X_OK) == 0) ? 1 : 0;
        unsigned long fmt = (unsigned long)(st.st_mode & 0170000);
        const char *kind = (fmt == 0120000UL) ? "lnk" : ((fmt == 0040000UL) ? "dir" : "reg");
        o = dp_push_str(buf, o, sizeof(buf), "[INIT-WRAPPER] OK   ");
        o = dp_push_str(buf, o, sizeof(buf), label);
        o = dp_push_str(buf, o, sizeof(buf), " -> ");
        o = dp_push_str(buf, o, sizeof(buf), path);
        o = dp_push_str(buf, o, sizeof(buf), " (type=");
        o = dp_push_str(buf, o, sizeof(buf), kind);
        o = dp_push_str(buf, o, sizeof(buf), ", mode=");
        o = dp_push_num(buf, o, sizeof(buf), (long)(st.st_mode & 0777), 8);
        o = dp_push_str(buf, o, sizeof(buf), ", x=");
        o = dp_push_num(buf, o, sizeof(buf), xok, 10);
        o = dp_push_str(buf, o, sizeof(buf), ")");
    } else {
        o = dp_push_str(buf, o, sizeof(buf), "[INIT-WRAPPER] MISS ");
        o = dp_push_str(buf, o, sizeof(buf), label);
        o = dp_push_str(buf, o, sizeof(buf), " -> ");
        o = dp_push_str(buf, o, sizeof(buf), path);
        o = dp_push_str(buf, o, sizeof(buf), " (errno=");
        o = dp_push_num(buf, o, sizeof(buf), -r, 10);
        o = dp_push_str(buf, o, sizeof(buf), ")");
    }
    write_line(buf);
}

static void ensure_byname_link(const char *name, const char *dev_a, const char *dev_b) {
    const char *target = (sc2(SYS_access, (long)dev_a, F_OK) == 0)
                             ? dev_a
                             : ((sc2(SYS_access, (long)dev_b, F_OK) == 0) ? dev_b : NULL);
    if (!target) return;
    char path[128];
    size_t o = 0;
    o = dp_push_str(path, o, sizeof(path), "/dev/block/by-name/");
    dp_push_str(path, o, sizeof(path), name);
    sc1(SYS_unlink, (long)path);
    sc2(SYS_symlink, (long)target, (long)path);
}

static void stream_kmsg_child(int kfd, int tty_fd) {
    if (kfd < 0 || tty_fd < 0) sc1(SYS_exit, 0);
    int loops = 0;
    char buf[2048];
    while (loops < 18000) {
        long n = sc3(SYS_read, kfd, (long)buf, (long)(sizeof(buf) - 1));
        if (n > 0) {
            buf[n] = '\0';
            char *semi = dp_strchr(buf, ';');
            char *msg = semi ? (semi + 1) : buf;
            if (dp_strstr(msg, "[INITRD]") || dp_strstr(msg, "[INIT-WRAPPER]")) continue;
            size_t mlen = dp_strlen(msg);
            safe_write_all(tty_fd, "[ANDROID/KMSG] ", 15);
            safe_write_all(tty_fd, msg, mlen);
            if (mlen == 0 || msg[mlen - 1] != '\n') {
                safe_write_all(tty_fd, "\n", 1);
            }
            continue;
        }
        long err = -n;
        if (n < 0 && (err == EPIPE || err == EINTR)) {
            dp_usleep(1000);
            loops++;
            continue;
        }
        dp_usleep(10000);
        loops++;
    }
    sc1(SYS_close, kfd);
    sc1(SYS_close, tty_fd);
    sc1(SYS_exit, 0);
}

int c_main(int argc, char **argv, char **envp) {
    /* First heartbeat over inherited stdout/stderr before touching /dev */
    safe_write_all(1, "[INIT-WRAPPER] _start alive (nostdlib)\n", 39);

    long m_dev = 0;
    if (sc2(SYS_access, (long)"/dev/ttyS0", F_OK) != 0) {
        long mr = sc5(SYS_mount, (long)"devtmpfs", (long)"/dev", (long)"devtmpfs", 0, 0);
        if (mr < 0) m_dev = -mr;
    }

    sc2(SYS_mkdir, (long)"/dev/block", 0755);
    sc2(SYS_mkdir, (long)"/dev/block/by-name", 0755);
    ensure_byname_link("system", "/dev/block/vda", "/dev/vda");
    ensure_byname_link("vendor", "/dev/block/vdb", "/dev/vdb");
    ensure_byname_link("userdata", "/dev/block/vdc", "/dev/vdc");
    ensure_byname_link("data", "/dev/block/vdc", "/dev/vdc");

    g_tty = (int)sc3(SYS_open, (long)"/dev/ttyS0", O_WRONLY | O_NOCTTY | O_NONBLOCK, 0);
    if (g_tty < 0) g_tty = (int)sc3(SYS_open, (long)"/dev/console", O_WRONLY | O_NOCTTY | O_NONBLOCK, 0);
    if (g_tty < 0) g_tty = 1;
    g_kmsg = (int)sc3(SYS_open, (long)"/dev/kmsg", O_WRONLY | O_NOCTTY | O_NONBLOCK, 0);

    char msg[256];
    size_t o = 0;
    o = dp_push_str(msg, o, sizeof(msg), "[INIT-WRAPPER] PID=");
    o = dp_push_num(msg, o, sizeof(msg), sc0(SYS_getpid), 10);
    o = dp_push_str(msg, o, sizeof(msg), " entered /android rootfs (tty=");
    o = dp_push_num(msg, o, sizeof(msg), (long)g_tty, 10);
    o = dp_push_str(msg, o, sizeof(msg), ", kmsg=");
    o = dp_push_num(msg, o, sizeof(msg), (long)g_kmsg, 10);
    o = dp_push_str(msg, o, sizeof(msg), ", dev_err=");
    o = dp_push_num(msg, o, sizeof(msg), m_dev, 10);
    dp_push_str(msg, o, sizeof(msg), ")");
    write_line(msg);

    check_path("/init", "/init");
    check_path("/system/bin/init", "/system/bin/init");
    check_path("/system/bin/bootstrap/linker64", "/system/bin/bootstrap/linker64");
    check_path("/system/bin/linker64", "/system/bin/linker64");
    check_path("root fstab", "/fstab.android_x86_64");
    check_path("vendor fstab", "/vendor/etc/fstab.android_x86_64");
    check_path("plat_sepolicy.cil", "/system/etc/selinux/plat_sepolicy.cil");
    check_path("vendor_sepolicy.cil", "/vendor/etc/selinux/vendor_sepolicy.cil");
    check_path("/metadata", "/metadata");
    check_path("/linkerconfig", "/linkerconfig");
    check_path("/data/adb/ksud", "/data/adb/ksud");

    /* Note: /system/bin/linker64 is a symlink to /apex/com.android.runtime/bin/linker64
     * which does not exist until Android init mounts bootstrap APEXes; /system/bin/init
     * uses either static linkage or /system/bin/bootstrap/linker64. */
    const char *init_exec = NULL;
    if (sc2(SYS_access, (long)"/init", X_OK) == 0) {
        init_exec = "/init";
    } else if (sc2(SYS_access, (long)"/system/bin/init", X_OK) == 0) {
        init_exec = "/system/bin/init";
    }
    if (!init_exec) {
        write_line("[INIT-WRAPPER] FATAL: /init and /system/bin/init missing/not executable; stalling 25s for log flush...");
        dp_usleep(25000000L);
        return 1;
    }

    int kmsg_read_fd = (int)sc3(SYS_open, (long)"/dev/kmsg", O_RDONLY | O_NONBLOCK, 0);
    if (kmsg_read_fd >= 0) {
        sc3(SYS_lseek, kmsg_read_fd, 0, SEEK_END);
    }
    int child_tty = (int)sc1(SYS_dup, g_tty);
    if (child_tty < 0) child_tty = 1;

    write_line("[INIT-WRAPPER] Handing off PID 1 via execve(\"/init\")...");
    long pid = sc0(SYS_fork);
    if (pid == 0) {
        if (g_tty > 2) sc1(SYS_close, g_tty);
        if (g_kmsg >= 0) sc1(SYS_close, g_kmsg);
        stream_kmsg_child(kmsg_read_fd, child_tty);
    }
    if (kmsg_read_fd >= 0) sc1(SYS_close, kmsg_read_fd);
    if (child_tty > 2) sc1(SYS_close, child_tty);
    if (g_tty > 2) sc1(SYS_close, g_tty);
    if (g_kmsg >= 0) sc1(SYS_close, g_kmsg);

    char *init_argv[16];
    init_argv[0] = (char *)init_exec;
    int copy_cnt = (argc > 1) ? ((argc < 15) ? argc : 15) : 1;
    for (int i = 1; i < copy_cnt; i++) {
        init_argv[i] = argv[i];
    }
    init_argv[copy_cnt] = NULL;
    long ex = sc3(SYS_execve, (long)init_exec, (long)init_argv, (long)envp);
    if (ex < 0 && init_exec[1] == 'i') {
        init_argv[0] = "/system/bin/init";
        ex = sc3(SYS_execve, (long)"/system/bin/init", (long)init_argv, (long)envp);
    }

    g_tty = (int)sc3(SYS_open, (long)"/dev/ttyS0", O_WRONLY | O_NOCTTY | O_NONBLOCK, 0);
    if (g_tty < 0) g_tty = 1;
    o = 0;
    o = dp_push_str(msg, o, sizeof(msg), "[INIT-WRAPPER] FATAL: execve(\"/init\") failed errno=");
    o = dp_push_num(msg, o, sizeof(msg), -ex, 10);
    dp_push_str(msg, o, sizeof(msg), "; stalling 25s...");
    write_line(msg);
    dp_usleep(25000000L);
    return 1;
}

__asm__(
    ".global _start\n"
    "_start:\n"
    "  xor %rbp, %rbp\n"
    "  mov (%rsp), %rdi\n"
    "  lea 8(%rsp), %rsi\n"
    "  lea 16(%rsp,%rdi,8), %rdx\n"
    "  and $-16, %rsp\n"
    "  call c_main\n"
    "  mov %eax, %edi\n"
    "  mov $60, %eax\n"
    "  syscall\n"
);
CEOF

gcc -nostdlib -ffreestanding -fno-builtin -static -Os -march=x86-64 -mno-sse -mno-avx -fno-stack-protector -fno-asynchronous-unwind-tables -Wall -Werror "${WORK_DIR}/droidport_init_wrapper.c" -o "${WORK_DIR}/mnt/sbin/droidport_init_wrapper"
chmod 0755 "${WORK_DIR}/mnt/sbin/droidport_init_wrapper"
WRAP_INFO=$(file -b "${WORK_DIR}/mnt/sbin/droidport_init_wrapper" || echo "unknown")
echo "Verified PID-1 wrapper binary: ${WRAP_INFO}"
echo "${WRAP_INFO}" | grep -qiE "ELF 64-bit.*x86-64"
test -x "${WORK_DIR}/mnt/sbin/droidport_init_wrapper"
cp -f "${WORK_DIR}/mnt/sbin/droidport_init_wrapper" "/tmp/droidport_init_wrapper_bin"
ls -lh "${WORK_DIR}/mnt/sbin/droidport_init_wrapper"

# Ensure clean boot in both SELinux Enforcing and Permissive modes + run ksud post-fs-data Magic Mount hook
INIT_DIR=""
for CANDIDATE_INIT in "${WORK_DIR}/mnt/system/etc/init" "${WORK_DIR}/mnt/etc/init"; do
  if [ -d "${CANDIDATE_INIT}" ]; then
    INIT_DIR="${CANDIDATE_INIT}"
    break
  fi
done

if [ -n "${INIT_DIR}" ]; then
  echo "Injecting ${INIT_DIR}/init.portable_selinux.rc for Enforcing/Permissive & KernelSU Next Magic Mount..."
  cat <<'EOF' > "${INIT_DIR}/init.portable_selinux.rc"
on post-fs-data
    restorecon_recursive /data/adb
    restorecon_recursive /data/local/tmp
    exec - root root -- /system/bin/sh -c "if [ -x /data/adb/ksud ] && [ -e /sys/module/kernelsu -o -d /data/adb/ksu ]; then /data/adb/ksud post-fs-data 2>/dev/null || true; /data/adb/ksud sepolicy patch 'allow hal_graphics_composer_default * * *' 'allow surfaceflinger * * *' 'allow su * * *' 2>/dev/null || true; fi"

on boot
    setprop ro.hardware.egl mesa
    setprop debug.hwui.renderer opengl
    setprop ro.hwui.use_vulkan false

on property:sys.boot_completed=1
    exec - root root -- /system/bin/sh -c "if [ -x /data/adb/ksud ] && [ -e /sys/module/kernelsu -o -d /data/adb/ksu ]; then /data/adb/ksud boot-completed 2>/dev/null || true; fi"
EOF
  chmod 0644 "${INIT_DIR}/init.portable_selinux.rc"
fi

# Unmount & re-compress vendor.img if modified
if [ "${HAS_VENDOR_RW}" -eq 1 ]; then
  sync
  umount "${WORK_DIR}/vendor_mnt"
  e2fsck -f -y "${VENDOR_RAW}" || true
  resize2fs -M "${VENDOR_RAW}" || true
  e2fsck -f -y "${VENDOR_RAW}" || true
  qemu-img convert -c -O qcow2 "${VENDOR_RAW}" "${IMG_DIR}/vendor.img"
  ls -lh "${IMG_DIR}/vendor.img"
fi

if mountpoint -q "${WORK_DIR}/bliss_mnt"; then
  umount "${WORK_DIR}/bliss_mnt"
fi
rm -f "/tmp/bliss_system_fallback.img"

# Ensure /vendor and /data mountpoint directories exist inside system.img
[ -e "${WORK_DIR}/mnt/vendor" ] || mkdir -p "${WORK_DIR}/mnt/vendor"
[ -e "${WORK_DIR}/mnt/data" ] || mkdir -p "${WORK_DIR}/mnt/data"

sync
umount "${WORK_DIR}/mnt"

echo "=== [4/5] Minimizing Empty Slack (resize2fs -M) & Compressing system.img to qcow2 ==="
e2fsck -f -y "${RAW_SYS}"
resize2fs -M "${RAW_SYS}"
e2fsck -f -y "${RAW_SYS}"
qemu-img convert -c -O qcow2 "${RAW_SYS}" "${IMG_DIR}/system.img"
rm -rf "${WORK_DIR}"
ls -lh "${IMG_DIR}/system.img"

BASE_INITRD="/tmp/base_initrd.img"
[ -s "${BASE_INITRD}" ] || BASE_INITRD="${IMG_DIR}/initrd.img"

if [ -s "${BASE_INITRD}" ]; then
  echo "=== [4.5/5] Building Dual Initrd Pair (initrd_stock.img & initrd_ksunext.img + x86_64 ksud) ==="
  INITRD_WORK="/tmp/initrd_patch_work"
  rm -rf "${INITRD_WORK}"
  mkdir -p "${INITRD_WORK}/root"
  INITRD_MAGIC=$(file -b "${BASE_INITRD}" || echo "unknown")
  echo "Detected base initrd format: ${INITRD_MAGIC}"

  COMP_KIND="gzip"
  if echo "${INITRD_MAGIC}" | grep -qi "XZ"; then
    COMP_KIND="xz"
    xz -dc "${BASE_INITRD}" | (cd "${INITRD_WORK}/root" && cpio -idm --no-absolute-filenames >/dev/null 2>&1 || cpio -idm --no-absolute-filenames)
  elif echo "${INITRD_MAGIC}" | grep -qi "LZ4"; then
    COMP_KIND="lz4"
    lz4 -dc "${BASE_INITRD}" | (cd "${INITRD_WORK}/root" && cpio -idm --no-absolute-filenames >/dev/null 2>&1 || cpio -idm --no-absolute-filenames)
  elif echo "${INITRD_MAGIC}" | grep -qi "Zstandard"; then
    COMP_KIND="zstd"
    zstd -dc "${BASE_INITRD}" | (cd "${INITRD_WORK}/root" && cpio -idm --no-absolute-filenames >/dev/null 2>&1 || cpio -idm --no-absolute-filenames)
  elif echo "${INITRD_MAGIC}" | grep -qi "gzip"; then
    COMP_KIND="gzip"
    gzip -dc "${BASE_INITRD}" | (cd "${INITRD_WORK}/root" && cpio -idm --no-absolute-filenames >/dev/null 2>&1 || cpio -idm --no-absolute-filenames)
  else
    COMP_KIND="gzip"
    (cd "${INITRD_WORK}/root" && cpio -idm --no-absolute-filenames < "${BASE_INITRD}") || true
  fi

  mkdir -p "${INITRD_WORK}/root/sbin"
  cat <<'EOF' > "${INITRD_WORK}/root/sbin/droidport_mount_hook.sh"
#!/bin/sh
_dp_log() {
  if [ -c /dev/ttyS0 ]; then
    echo "[INITRD] $*" >/dev/ttyS0 2>/dev/null || echo "[INITRD] $*"
  else
    echo "[INITRD] $*"
  fi
}

echo "7 7 1 7" > /proc/sys/kernel/printk 2>/dev/null || true
_dp_log "Kernel release: $(uname -r 2>/dev/null || echo unknown) | initrd flavor: $([ -x /sbin/ksud ] && echo ksunext || echo stock)"
_dp_log "VirtIO block devices: $(ls -1 /dev/vd* 2>/dev/null | tr '\n' ' ' || echo none)"

TARGET_ROOT="/android"
[ -d /android ] || [ ! -d /mnt ] || TARGET_ROOT="/mnt"
_dp_log "Preparing root target=${TARGET_ROOT} before switch_root"

for SUB in dev proc sys mnt metadata apex linkerconfig tmp; do
  if [ -L "${TARGET_ROOT}/${SUB}" ] || { [ -e "${TARGET_ROOT}/${SUB}" ] && [ ! -d "${TARGET_ROOT}/${SUB}" ]; }; then
    rm -f "${TARGET_ROOT}/${SUB}" 2>/dev/null || true
  fi
  [ -d "${TARGET_ROOT}/${SUB}" ] || mkdir -p "${TARGET_ROOT}/${SUB}" 2>/dev/null || true
done

if [ -d "${TARGET_ROOT}/dev" ] && ! grep -q " ${TARGET_ROOT}/dev " /proc/mounts 2>/dev/null; then
  mount -t devtmpfs devtmpfs "${TARGET_ROOT}/dev" 2>/dev/null || true
fi
_dp_log "Pre-switch dev nodes: ttyS0=$([ -c "${TARGET_ROOT}/dev/ttyS0" ] && echo ok || echo miss), kmsg=$([ -c "${TARGET_ROOT}/dev/kmsg" ] && echo ok || echo miss)"

if [ -d "${TARGET_ROOT}/metadata" ] && ! grep -q " ${TARGET_ROOT}/metadata " /proc/mounts 2>/dev/null; then
  mount -t tmpfs -o mode=0755,nosuid,nodev,noexec tmpfs "${TARGET_ROOT}/metadata" 2>/dev/null || true
fi

if [ -b /dev/vdb ] && [ -d "${TARGET_ROOT}" ]; then
  [ -e "${TARGET_ROOT}/vendor" ] || mkdir -p "${TARGET_ROOT}/vendor" 2>/dev/null || true
  if ! grep -q " ${TARGET_ROOT}/vendor " /proc/mounts 2>/dev/null; then
    if mount -t ext4 -o ro /dev/vdb "${TARGET_ROOT}/vendor" 2>/dev/null || mount -o ro /dev/vdb "${TARGET_ROOT}/vendor" 2>/dev/null; then
      _dp_log "Mounted /dev/vdb -> ${TARGET_ROOT}/vendor (ro ext4)"
    else
      _dp_log "WARN: Failed to mount /dev/vdb -> ${TARGET_ROOT}/vendor"
    fi
  else
    _dp_log "${TARGET_ROOT}/vendor already mounted"
  fi
fi

if [ -b /dev/vdc ] && [ -d "${TARGET_ROOT}" ]; then
  [ -e "${TARGET_ROOT}/data" ] || mkdir -p "${TARGET_ROOT}/data" 2>/dev/null || true
  if ! grep -q " ${TARGET_ROOT}/data " /proc/mounts 2>/dev/null; then
    if ! mount -t ext4 -o rw,noatime /dev/vdc "${TARGET_ROOT}/data" 2>/dev/null; then
      _dp_log "Initial mount of /dev/vdc failed; running e2fsck/recovery..."
      command -v e2fsck >/dev/null 2>&1 && e2fsck -p /dev/vdc >/dev/null 2>&1 || true
      if ! mount -t ext4 -o rw,noatime /dev/vdc "${TARGET_ROOT}/data" 2>/dev/null; then
        if command -v mkfs.ext4 >/dev/null 2>&1; then
          _dp_log "Formatting uninitialized /dev/vdc as ext4..."
          mkfs.ext4 -F -L data /dev/vdc >/dev/null 2>&1 || true
        elif command -v mke2fs >/dev/null 2>&1; then
          _dp_log "Formatting uninitialized /dev/vdc with mke2fs..."
          mke2fs -t ext4 -F -L data /dev/vdc >/dev/null 2>&1 || true
        fi
        mount -t ext4 -o rw,noatime /dev/vdc "${TARGET_ROOT}/data" 2>/dev/null || _dp_log "ERROR: Unable to mount /dev/vdc on ${TARGET_ROOT}/data"
      fi
    fi
    if grep -q " ${TARGET_ROOT}/data " /proc/mounts 2>/dev/null; then
      _dp_log "Mounted /dev/vdc -> ${TARGET_ROOT}/data (rw ext4)"
    fi
  else
    _dp_log "${TARGET_ROOT}/data already mounted"
  fi
fi

# KernelSU Next Initrd Staging (only runs in initrd_ksunext.img where /sbin/ksud exists)
if [ -x /sbin/ksud ] && [ -d "${TARGET_ROOT}/data" ] && grep -q " ${TARGET_ROOT}/data " /proc/mounts 2>/dev/null; then
  mkdir -p "${TARGET_ROOT}/data/adb/modules" "${TARGET_ROOT}/data/adb/ksu/bin" 2>/dev/null || true
  cp -f /sbin/ksud "${TARGET_ROOT}/data/adb/ksud" 2>/dev/null || true
  chmod 0755 "${TARGET_ROOT}/data/adb/ksud" 2>/dev/null || true
  _dp_log "KernelSU Next staged /sbin/ksud -> ${TARGET_ROOT}/data/adb/ksud (OverlayFS Magic Mount ready)"
fi

_dp_log "Target binary check: $(ls -l ${TARGET_ROOT}/sbin/droidport_init_wrapper ${TARGET_ROOT}/init ${TARGET_ROOT}/system/bin/init 2>&1 | tr '\n' ' ')"
_dp_log "Active target mounts: $(grep " ${TARGET_ROOT}" /proc/mounts 2>/dev/null | tr '\n' ';' || echo none)"
EOF
  chmod 0755 "${INITRD_WORK}/root/sbin/droidport_mount_hook.sh"

  if [ -x "/tmp/droidport_init_wrapper_bin" ]; then
    cp -f "/tmp/droidport_init_wrapper_bin" "${INITRD_WORK}/root/sbin/droidport_init_wrapper"
    chmod 0755 "${INITRD_WORK}/root/sbin/droidport_init_wrapper"
    rm -f "/tmp/droidport_init_wrapper_bin"
  fi
  rm -rf "/tmp/bliss_donor_meta"

  python3 - "${INITRD_WORK}/root/init" <<'PYEOF'
import pathlib, re, sys

init_path = pathlib.Path(sys.argv[1])
if not init_path.exists():
    print("WARNING: initrd /init not found; skipping /init hook injection")
    sys.exit(0)

text = init_path.read_text(encoding="utf-8", errors="replace")
if "droidport_mount_hook.sh" in text and "droidport_init_wrapper" in text:
    print("initrd /init already patched with wrapper")
    sys.exit(0)

lines = text.splitlines(keepends=True)
out = []
hook_inserted = False
header_logged = False

# Matches optional leading keywords, ${SWITCH:-switch_root}, optional busybox, and switch_root syntax
sr_re = re.compile(
    r'^(\s*)(.*?)(?:(\$\{[^}]*switch_root[^}]*\}|(?:busybox\s+)?switch_root))\s+(\S+)\s+(\S+)(.*)$'
)

for i, line in enumerate(lines):
    if not header_logged and i == 0 and line.startswith("#!"):
        out.append(line)
        out.append('echo 7 7 1 7 > /proc/sys/kernel/printk 2>/dev/null || true\n')
        out.append('echo "[INITRD] Bliss/Android-x86 /init started (cmd=$(cat /proc/cmdline 2>/dev/null))" >/dev/ttyS0 2>/dev/null || true\n')
        header_logged = True
        continue

    if "0 0 0 0" in line and "/proc/sys/kernel/printk" in line and not line.lstrip().startswith("#"):
        indent = re.match(r'^(\s*)', line).group(1)
        out.append(f'{indent}echo 7 7 1 7 > /proc/sys/kernel/printk 2>/dev/null || true\n')
        continue

    if re.search(r'^\s*LOG=/dev/null\s*$', line):
        indent = re.match(r'^(\s*)', line).group(1)
        out.append(f'{indent}if [ -c /dev/ttyS0 ]; then LOG=/dev/ttyS0; else LOG=/dev/null; fi\n')
        continue

    if re.search(r'\bswitch_root\b', line) and not line.lstrip().startswith("#"):
        indent = re.match(r'^(\s*)', line).group(1)
        out.append(f'{indent}[ -x /sbin/droidport_mount_hook.sh ] && /sbin/droidport_mount_hook.sh\n')
        out.append(f'{indent}echo 7 7 1 7 > /proc/sys/kernel/printk 2>/dev/null || true\n')
        out.append(f'{indent}[ -c /dev/ttyS0 ] && exec >/dev/ttyS0 2>&1\n')
        m = sr_re.match(line.rstrip("\r\n"))
        if m:
            lead, prefix, sr_cmd, tgt, init_arg, rest = m.groups()
            out.append(f'{lead}if [ -x "{tgt}/sbin/droidport_init_wrapper" ]; then\n')
            out.append(f'{lead}  echo "[INITRD] Executing: {prefix}{sr_cmd} {tgt} /sbin/droidport_init_wrapper" >/dev/ttyS0 2>/dev/null || true\n')
            out.append(f'{lead}  {prefix}{sr_cmd} {tgt} /sbin/droidport_init_wrapper{rest}\n')
            out.append(f'{lead}else\n')
            out.append(f'{lead}  echo "[INITRD] WARN: wrapper missing at {tgt}/sbin/droidport_init_wrapper; running fallback" >/dev/ttyS0 2>/dev/null || true\n')
            out.append(f'{lead}  {line.strip()}\n')
            out.append(f'{lead}fi\n')
            print(f"Routed switch_root line #{i+1}: {line.strip()!r} -> target={tgt} wrapper=/sbin/droidport_init_wrapper")
        else:
            out.append(f'{indent}echo "[INITRD] Executing raw switch_root: {line.strip()}" >/dev/ttyS0 2>/dev/null || true\n')
            out.append(line)
            print(f"WARNING: switch_root regex fell back on line #{i+1}: {line.strip()!r}")
        hook_inserted = True
        continue

    if re.search(r'\breboot\b', line) and not line.lstrip().startswith("#") and "reboot and check" not in line.lower():
        indent = re.match(r'^(\s*)', line).group(1)
        out.append(f'{indent}echo "[INITRD] WARN: initrd triggered reboot: {line.strip()}" >/dev/ttyS0 2>/dev/null || true\n')

    out.append(line)

if not hook_inserted:
    out.insert(max(len(out) - 1, 0), '[ -x /sbin/droidport_mount_hook.sh ] && /sbin/droidport_mount_hook.sh\n')

init_path.write_text("".join(out), encoding="utf-8")
print(f"Patched {init_path} (switch_root_hook={hook_inserted})")
PYEOF

  chmod 0755 "${INITRD_WORK}/root/init" 2>/dev/null || true
  echo "--- Patched initrd /init switch_root block ---"
  grep -n -C 4 "switch_root" "${INITRD_WORK}/root/init" || true

  pack_initrd() {
    local SRC_ROOT="$1"
    local OUT_IMG
    OUT_IMG="$(realpath -m "$2")"
    mkdir -p "$(dirname "${OUT_IMG}")"
    case "${COMP_KIND}" in
      xz)
        (cd "${SRC_ROOT}" && find . | cpio -o -H newc --quiet | xz --check=crc32 -9 > "${OUT_IMG}")
        ;;
      lz4)
        (cd "${SRC_ROOT}" && find . | cpio -o -H newc --quiet | lz4 -l -9 > "${OUT_IMG}")
        ;;
      zstd)
        (cd "${SRC_ROOT}" && find . | cpio -o -H newc --quiet | zstd -q -19 > "${OUT_IMG}")
        ;;
      *)
        (cd "${SRC_ROOT}" && find . | cpio -o -H newc --quiet | gzip -9 > "${OUT_IMG}")
        ;;
    esac
  }

  # 1) Stock clean initrd_stock.img (NO ksud inside)
  rm -f "${INITRD_WORK}/root/sbin/ksud"
  pack_initrd "${INITRD_WORK}/root" "${IMG_DIR}/initrd_stock.img"
  if [ ! -s "${IMG_DIR}/initrd_stock.img" ]; then
    echo "ERROR: Repacked initrd_stock.img is empty!" >&2
    exit 1
  fi
  cp -f "${IMG_DIR}/initrd_stock.img" "${IMG_DIR}/initrd.img"
  ls -lh "${IMG_DIR}/initrd_stock.img" "${IMG_DIR}/initrd.img"

  # 2) KernelSU Next initrd_ksunext.img (with verified x86_64 /sbin/ksud)
  if [ ! -s "/tmp/ksud_x86_64" ]; then
    echo "ERROR: /tmp/ksud_x86_64 missing when building initrd_ksunext.img!" >&2
    exit 1
  fi
  rm -rf "${INITRD_WORK}/root_ksu"
  cp -a "${INITRD_WORK}/root" "${INITRD_WORK}/root_ksu"
  cp -f "/tmp/ksud_x86_64" "${INITRD_WORK}/root_ksu/sbin/ksud"
  chmod 0755 "${INITRD_WORK}/root_ksu/sbin/ksud"
  KSUD_IN_INITRD=$(file -b "${INITRD_WORK}/root_ksu/sbin/ksud" || echo "unknown")
  echo "Verified ksud in initrd_ksunext.img: ${KSUD_IN_INITRD}"
  echo "${KSUD_IN_INITRD}" | grep -qiE 'ELF 64-bit.*x86-64'
  pack_initrd "${INITRD_WORK}/root_ksu" "${IMG_DIR}/initrd_ksunext.img"
  if [ ! -s "${IMG_DIR}/initrd_ksunext.img" ]; then
    echo "ERROR: Repacked initrd_ksunext.img is empty!" >&2
    exit 1
  fi
  ls -lh "${IMG_DIR}/initrd_ksunext.img"
  rm -rf "${INITRD_WORK}" "/tmp/ksud_x86_64" "/tmp/base_initrd.img"
else
  echo "ERROR: No initrd.img available to patch!" >&2
  exit 1
fi

echo "=== [5/5] Packaging All-in-One Module: modules/Portable_Stealth_KSU.zip ==="
mkdir -p "${BUNDLE_DIR}/modules"
MOD_OUT_DIR="$(cd "${BUNDLE_DIR}/modules" && pwd)"
MOD_STAGE="/tmp/portable_stealth_ksu_stage"
rm -rf "${MOD_STAGE}"
mkdir -p "${MOD_STAGE}"

if [ -d "modules/Portable_Stealth_KSU" ]; then
  cp -a "modules/Portable_Stealth_KSU/." "${MOD_STAGE}/"
else
  cat <<'EOF' > "${MOD_STAGE}/module.prop"
id=portable_stealth_ksu
name=Portable Stealth KSU All-in-One
version=v1.0.0
versionCode=100
author=DroidPort
description=Scrubs QEMU/VirtIO/x86/Bliss/Lineage traces, wraps eth0 as Home_WiFi_5G wlan0, and simulates natural discharging battery (75%-88%).
EOF
  cat <<'EOF' > "${MOD_STAGE}/post-fs-data.sh"
#!/system/bin/sh
MODDIR=${0%/*}
RESETPROP=""
for BIN in /data/adb/ksu/bin/resetprop /data/adb/ksud /system/bin/resetprop resetprop; do
  if command -v "$BIN" >/dev/null 2>&1 || [ -x "$BIN" ]; then
    RESETPROP=$([ "$BIN" = "/data/adb/ksud" ] && echo "/data/adb/ksu/bin/resetprop" || echo "$BIN")
    break
  fi
done
[ -n "$RESETPROP" ] || exit 0
for PROP in ro.kernel.qemu ro.kernel.qemu.gles ro.kernel.android.qemud ro.boot.qemu qemu.hw.mainkeys qemu.sf.fake_camera qemu.sf.lcd_density init.svc.qemu-props ro.hardware.virtual_device ro.lineage.version ro.lineage.display.version ro.lineage.build.version ro.lineage.device ro.modversion ro.bliss.version ro.bliss.display.version ro.bliss.device; do
  "$RESETPROP" --delete "$PROP" 2>/dev/null || true
done
getprop | while IFS= read -r LINE; do
  NAME=$(echo "$LINE" | sed -n 's/^\[\([^]]*\)\]:.*$/\1/p')
  VAL=$(echo "$LINE" | sed -n 's/^\[[^]]*\]: \[\(.*\)\]$/\1/p')
  case "$NAME" in ro.product.cpu.abi*|ro.dalvik.vm.native.bridge|dalvik.vm.*|ro.boot.selinux) continue ;; esac
  echo "$NAME $VAL" | grep -qiE 'qemu|virtio|bliss|lineage' && "$RESETPROP" --delete "$NAME" 2>/dev/null || true
done
"$RESETPROP" -n "ro.boot.verifiedbootstate" "green"
"$RESETPROP" -n "ro.boot.flash.locked" "1"
"$RESETPROP" -n "ro.boot.vbmeta.device_state" "locked"
"$RESETPROP" -n "ro.debuggable" "0"
"$RESETPROP" -n "ro.secure" "1"
EOF
  cat <<'EOF' > "${MOD_STAGE}/service.sh"
#!/system/bin/sh
MODDIR=${0%/*}
WIFI_FLAG="/data/adb/portable_stealth_wifi_disabled"
while [ "$(getprop sys.boot_completed)" != "1" ]; do sleep 2; done
sleep 3
if [ ! -f "$WIFI_FLAG" ]; then
  [ -d /sys/class/net/eth0 ] && [ ! -d /sys/class/net/wlan0 ] && { ip link add link eth0 name wlan0 type virt_wifi 2>/dev/null || modprobe virt_wifi 2>/dev/null || modprobe mac80211_hwsim radios=2 2>/dev/null || true; }
  [ -d /sys/class/net/wlan0 ] && ip link set wlan0 up 2>/dev/null || true
  svc wifi enable 2>/dev/null || true
  cmd wifi connect-network "Home_WiFi_5G" open 2>/dev/null || true
fi
LEVEL=84
DIR=-1
while true; do
  dumpsys battery unplug 2>/dev/null || true
  dumpsys battery set ac 0 2>/dev/null || true
  dumpsys battery set usb 0 2>/dev/null || true
  dumpsys battery set status 3 2>/dev/null || true
  dumpsys battery set level "$LEVEL" 2>/dev/null || true
  RND=$(( $(od -An -N1 -tu1 /dev/urandom 2>/dev/null | tr -d ' ') % 3 ))
  [ "$RND" -eq 0 ] && LEVEL=$((LEVEL + DIR))
  if [ "$LEVEL" -le 75 ]; then LEVEL=76; DIR=1; elif [ "$LEVEL" -ge 88 ]; then LEVEL=87; DIR=-1; fi
  sleep 45
done
EOF
fi

chmod 0755 "${MOD_STAGE}/post-fs-data.sh" "${MOD_STAGE}/service.sh"
chmod 0644 "${MOD_STAGE}/module.prop"
rm -f "${MOD_OUT_DIR}/Portable_Stealth_KSU.zip"
(cd "${MOD_STAGE}" && 7z a -tzip -mx=9 "${MOD_OUT_DIR}/Portable_Stealth_KSU.zip" ./* >/dev/null)
rm -rf "${MOD_STAGE}"
ls -lh "${MOD_OUT_DIR}/Portable_Stealth_KSU.zip"
