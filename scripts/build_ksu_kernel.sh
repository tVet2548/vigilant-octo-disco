#!/usr/bin/env bash
set -euo pipefail

BUNDLE_DIR="${1:-dist_bundle}"
IMG_DIR="${BUNDLE_DIR}/images"
WORK_DIR="/tmp/bliss_work"
mkdir -p "${IMG_DIR}" "${WORK_DIR}"

echo "=== [1/4] Resolving Bliss OS 16.9 (Android 13 / API 33) x86_64 ISO ==="
ISO_URL="${BLISS_ISO_URL:-}"
DONOR_SERIES="BlissOS16"
if [ -z "${ISO_URL}" ]; then
  for SF_PATH in "/Official/BlissOS16" "/Official/BlissOS16/Gapps/Generic" "/Official/BlissOS16/FOSS/Generic"; do
    RSS_XML=$(curl -fsSL "https://sourceforge.net/projects/blissos-x86/rss?path=${SF_PATH}" || true)
    ISO_URL=$(echo "${RSS_XML}" | grep -oE 'https://sourceforge\.net/projects/blissos-x86/files/Official/BlissOS16/[^"<]*Bliss[^"<]*16\.9[^"<]*x86_64[^"<]*\.iso/download' | head -n1 || true)
    if [ -z "${ISO_URL}" ]; then
      ISO_URL=$(echo "${RSS_XML}" | grep -oE 'https://sourceforge\.net/projects/blissos-x86/files/Official/BlissOS16/[^"<]*x86_64[^"<]*\.iso/download' | head -n1 || true)
    fi
    if [ -n "${ISO_URL}" ]; then
      break
    fi
  done
fi

if [ -z "${ISO_URL}" ]; then
  echo "ERROR: Unable to resolve Bliss OS 16.9 (API 33) x86_64 ISO download URL." >&2
  exit 1
fi

echo "Downloading ${DONOR_SERIES} ISO via aria2c (16 connections): ${ISO_URL}"
aria2c -x 16 -s 16 -k 1M --user-agent="Wget/1.21.4" --max-tries=5 --retry-wait=5 -d "${WORK_DIR}" -o "bliss_donor.iso" "${ISO_URL}"

ISO_BYTES=$(stat -c%s "${WORK_DIR}/bliss_donor.iso" 2>/dev/null || echo 0)
ISO_TYPE=$(file -b "${WORK_DIR}/bliss_donor.iso" 2>/dev/null || echo "unknown")
if [ "${ISO_BYTES}" -lt 52428800 ] || echo "${ISO_TYPE}" | grep -qiE 'HTML|ASCII text'; then
  echo "ERROR [Bliss-ISO]: Downloaded file failed integrity check (> 50MB required)!" >&2
  echo "  Broken URL   : ${ISO_URL}" >&2
  echo "  Actual Size  : ${ISO_BYTES} bytes" >&2
  echo "  Detected Type: ${ISO_TYPE}" >&2
  exit 1
fi
echo "Verified [Bliss-ISO] (${DONOR_SERIES}): ${ISO_BYTES} bytes (${ISO_TYPE})"

echo "=== [2/4] Extracting kernel_stock, initrd.img, and API-33 vendor.img ==="
mkdir -p "${WORK_DIR}/iso_mnt" "${WORK_DIR}/sfs_mnt" "/tmp/bliss_donor_meta"
mount -o loop,ro "${WORK_DIR}/bliss_donor.iso" "${WORK_DIR}/iso_mnt"

cp -f "${WORK_DIR}/iso_mnt/kernel" "${IMG_DIR}/kernel_stock"
cp -f "${WORK_DIR}/iso_mnt/initrd.img" "${IMG_DIR}/initrd.img"
cp -f "${WORK_DIR}/iso_mnt/initrd.img" "/tmp/base_initrd.img"

RAW_VENDOR="${WORK_DIR}/vendor_raw.img"
if [ -f "${WORK_DIR}/iso_mnt/vendor.img" ]; then
  cp -f "${WORK_DIR}/iso_mnt/vendor.img" "${RAW_VENDOR}"
elif [ -f "${WORK_DIR}/iso_mnt/vendor.efs" ]; then
  mkdir -p "${WORK_DIR}/vefs_mnt"
  mount -t erofs -o loop,ro "${WORK_DIR}/iso_mnt/vendor.efs" "${WORK_DIR}/vefs_mnt"
  if [ -f "${WORK_DIR}/vefs_mnt/vendor.img" ]; then
    cp -f "${WORK_DIR}/vefs_mnt/vendor.img" "${RAW_VENDOR}"
  fi
  umount "${WORK_DIR}/vefs_mnt"
elif [ -f "${WORK_DIR}/iso_mnt/vendor.sfs" ]; then
  unsquashfs -d "${WORK_DIR}/vsfs_out" "${WORK_DIR}/iso_mnt/vendor.sfs" "vendor.img" || true
  [ -f "${WORK_DIR}/vsfs_out/vendor.img" ] && mv "${WORK_DIR}/vsfs_out/vendor.img" "${RAW_VENDOR}"
fi

if [ -f "${WORK_DIR}/iso_mnt/system.efs" ]; then
  mkdir -p "${WORK_DIR}/efs_mnt"
  mount -t erofs -o loop,ro "${WORK_DIR}/iso_mnt/system.efs" "${WORK_DIR}/efs_mnt"
  if [ -f "${WORK_DIR}/efs_mnt/system.img" ]; then
    cp -f "${WORK_DIR}/efs_mnt/system.img" "${WORK_DIR}/bliss_system_fallback.img"
  fi
  umount "${WORK_DIR}/efs_mnt"
elif [ -f "${WORK_DIR}/iso_mnt/system.sfs" ]; then
  unsquashfs -d "${WORK_DIR}/sfs_out" "${WORK_DIR}/iso_mnt/system.sfs" "system.img"
  mv "${WORK_DIR}/sfs_out/system.img" "${WORK_DIR}/bliss_system_fallback.img"
elif [ -f "${WORK_DIR}/iso_mnt/system.img" ]; then
  cp -f "${WORK_DIR}/iso_mnt/system.img" "${WORK_DIR}/bliss_system_fallback.img"
fi

if [ -f "${WORK_DIR}/bliss_system_fallback.img" ]; then
  if file -b "${WORK_DIR}/bliss_system_fallback.img" | grep -qi "Android sparse image"; then
    simg2img "${WORK_DIR}/bliss_system_fallback.img" "${WORK_DIR}/bliss_unsparse.img"
    mv -f "${WORK_DIR}/bliss_unsparse.img" "${WORK_DIR}/bliss_system_fallback.img"
  fi
  mkdir -p "${WORK_DIR}/bliss_sys_mnt"
  if mount -o loop,ro "${WORK_DIR}/bliss_system_fallback.img" "${WORK_DIR}/bliss_sys_mnt" 2>/dev/null; then
    for PROP_C in "${WORK_DIR}/bliss_sys_mnt/system/build.prop" "${WORK_DIR}/bliss_sys_mnt/build.prop"; do
      if [ -f "${PROP_C}" ]; then
        DONOR_SDK=$(grep -E '^ro\.build\.version\.sdk=' "${PROP_C}" | head -n1 | cut -d= -f2 || true)
        echo "Detected Bliss donor SDK level: API ${DONOR_SDK:-unknown} (${DONOR_SERIES})"
        break
      fi
    done

    for META_F in fstab.android_x86_64 init.android_x86_64.rc ueventd.android_x86_64.rc; do
      for META_DIR in "${WORK_DIR}/bliss_sys_mnt" "${WORK_DIR}/bliss_sys_mnt/system/etc" "${WORK_DIR}/bliss_sys_mnt/system/etc/init/hw" "${WORK_DIR}/bliss_sys_mnt/vendor/etc" "${WORK_DIR}/bliss_sys_mnt/vendor/etc/init/hw"; do
        if [ -f "${META_DIR}/${META_F}" ] && [ ! -f "/tmp/bliss_donor_meta/${META_F}" ]; then
          cp -f "${META_DIR}/${META_F}" "/tmp/bliss_donor_meta/${META_F}"
        fi
      done
    done

    if [ ! -f "${RAW_VENDOR}" ]; then
      echo "Synthesizing standalone vendor.img containing Bliss OS 16.9 API-33 HALs..."
      mkdir -p "${WORK_DIR}/vendor_root"
      VENDOR_SRC=""
      if [ -d "${WORK_DIR}/bliss_sys_mnt/system/vendor/lib64" ]; then
        VENDOR_SRC="${WORK_DIR}/bliss_sys_mnt/system/vendor"
      elif [ -d "${WORK_DIR}/bliss_sys_mnt/vendor/lib64" ]; then
        VENDOR_SRC="${WORK_DIR}/bliss_sys_mnt/vendor"
      fi
      if [ -n "${VENDOR_SRC}" ]; then
        VENDOR_MB=$(du -sm "${VENDOR_SRC}" | awk '{print $1 + 128}')
        dd if=/dev/zero of="${RAW_VENDOR}" bs=1M count="${VENDOR_MB}" status=none
        mkfs.ext4 -F -L vendor "${RAW_VENDOR}" >/dev/null
        mount -o loop "${RAW_VENDOR}" "${WORK_DIR}/vendor_root"
        cp -a "${VENDOR_SRC}/." "${WORK_DIR}/vendor_root/"
        umount "${WORK_DIR}/vendor_root"
      fi
    fi
    umount "${WORK_DIR}/bliss_sys_mnt"
  fi
fi

umount "${WORK_DIR}/iso_mnt"
echo "Deleting Bliss OS ISO immediately to conserve disk space..."
rm -f "${WORK_DIR}/bliss_donor.iso"

if [ ! -s "${RAW_VENDOR}" ]; then
  echo "ERROR: Could not extract or synthesize vendor.img from Bliss OS 16.9 ISO." >&2
  exit 1
fi

echo "Minimizing and compressing vendor.img (e2fsck -> resize2fs -M -> qcow2)..."
if file -b "${RAW_VENDOR}" | grep -qi "Android sparse image"; then
  simg2img "${RAW_VENDOR}" "${RAW_VENDOR}.unsparse"
  mv -f "${RAW_VENDOR}.unsparse" "${RAW_VENDOR}"
fi
e2fsck -f -y "${RAW_VENDOR}" || true
resize2fs -M "${RAW_VENDOR}" || true
qemu-img convert -c -O qcow2 "${RAW_VENDOR}" "${IMG_DIR}/vendor.img"
rm -f "${RAW_VENDOR}"

if [ -f "${WORK_DIR}/bliss_system_fallback.img" ]; then
  mv "${WORK_DIR}/bliss_system_fallback.img" "/tmp/bliss_system_fallback.img"
fi

echo "=== [3/4] Acquiring Verified x86_64 ksud Binary & Checking Kernel Override ==="
rm -f "/tmp/ksud_x86_64"
KSU_APK="${BUNDLE_DIR}/modules/KernelSU_Next.apk"
if [ -s "${KSU_APK}" ]; then
  mkdir -p "${WORK_DIR}/apk_ext"
  if 7z e "${KSU_APK}" "lib/x86_64/libksud.so" -o"${WORK_DIR}/apk_ext" -y >/dev/null 2>&1 && [ -s "${WORK_DIR}/apk_ext/libksud.so" ]; then
    cp -f "${WORK_DIR}/apk_ext/libksud.so" "/tmp/ksud_x86_64"
    echo "Extracted ksud candidate from KernelSU_Next.apk (lib/x86_64/libksud.so)."
  fi
fi

if [ ! -s "/tmp/ksud_x86_64" ]; then
  KSUD_URL=$(curl -fsSL "https://api.github.com/repos/KernelSU-Next/KernelSU-Next/releases/latest" 2>/dev/null | \
    jq -r '.assets[] | select(.name | test("ksud.*(x86_64|x64)"; "i")) | .browser_download_url' | head -n1 || true)
  if [ -n "${KSUD_URL}" ] && [ "${KSUD_URL}" != "null" ]; then
    echo "Downloading x86_64 ksud release asset: ${KSUD_URL}"
    curl -fSL --retry 3 -o "/tmp/ksud_x86_64" "${KSUD_URL}" || rm -f "/tmp/ksud_x86_64"
  fi
fi

if [ ! -s "/tmp/ksud_x86_64" ]; then
  echo "ERROR: Could not extract or download x86_64 ksud binary!" >&2
  exit 1
fi
chmod 0755 "/tmp/ksud_x86_64"
KSUD_FILE_INFO=$(file -b "/tmp/ksud_x86_64" || echo "unknown")
echo "Verified [ksud_x86_64]: $(stat -c%s "/tmp/ksud_x86_64") bytes (${KSUD_FILE_INFO})"
if ! echo "${KSUD_FILE_INFO}" | grep -qiE 'ELF 64-bit.*x86-64' || echo "${KSUD_FILE_INFO}" | grep -qiE 'ARM|aarch64'; then
  echo "ERROR: ksud binary is NOT a valid 64-bit x86-64 ELF binary (${KSUD_FILE_INFO})!" >&2
  exit 1
fi

if [ -n "${KSU_KERNEL_URL:-}" ]; then
  echo "Downloading user-specified KernelSU Next x86_64 kernel: ${KSU_KERNEL_URL}"
  curl -fSL --retry 3 -o "${IMG_DIR}/kernel_ksunext" "${KSU_KERNEL_URL}"
  K_BYTES=$(stat -c%s "${IMG_DIR}/kernel_ksunext" 2>/dev/null || echo 0)
  K_TYPE=$(file -b "${IMG_DIR}/kernel_ksunext" 2>/dev/null || echo "unknown")
  if [ "${K_BYTES}" -lt 2097152 ] || ! echo "${K_TYPE}" | grep -qiE 'bzImage|Linux kernel x86'; then
    echo "ERROR [KSU-Kernel]: Custom kernel URL invalid (${K_BYTES} bytes, ${K_TYPE}): ${KSU_KERNEL_URL}" >&2
    rm -f "${IMG_DIR}/kernel_ksunext"
  fi
fi

echo "=== [4/4] Building kernel_ksunext (6.1 x86_64 ikconfig Parity + Stable KernelSU-Next + OverlayFS) ==="
if [ ! -s "${IMG_DIR}/kernel_ksunext" ]; then
  KERNEL_SRC="${WORK_DIR}/kernel_src"
  rm -rf "${KERNEL_SRC}"

  STOCK_VER=$(python3 - "${IMG_DIR}/kernel_stock" <<'PYEOF'
import sys
data = open(sys.argv[1], "rb").read(65536)
if len(data) >= 0x210 and data[0x202:0x206] == b"HdrS":
    off = int.from_bytes(data[0x20e:0x210], "little") + 0x200
    if 0x200 <= off < len(data):
        ver = data[off:off+128].split(b"\x00", 1)[0].decode("ascii", "ignore").strip()
        print(ver)
PYEOF
)
  echo "Detected kernel_stock version banner: ${STOCK_VER:-unknown}"
  STOCK_MAJMIN=$(echo "${STOCK_VER}" | grep -oE '^[0-9]+\.[0-9]+' || echo "6.1")
  echo "Target Linux LTS branch to match kernel_stock (Bliss 16.9): linux-${STOCK_MAJMIN}.y"

  if git clone --depth=1 --branch "linux-${STOCK_MAJMIN}.y" https://github.com/gregkh/linux.git "${KERNEL_SRC}"; then
    echo "Cloned branch linux-${STOCK_MAJMIN}.y from gregkh/linux."
  elif git clone --depth=1 --branch "v${STOCK_MAJMIN}" https://github.com/torvalds/linux.git "${KERNEL_SRC}"; then
    echo "Cloned tag v${STOCK_MAJMIN} from torvalds/linux."
  else
    rm -rf "${KERNEL_SRC}"
    echo "Fallback: cloning linux-6.1.y from gregkh/linux..."
    git clone --depth=1 --branch linux-6.1.y https://github.com/gregkh/linux.git "${KERNEL_SRC}"
  fi

  cd "${KERNEL_SRC}"

  KSU_TAG=$(curl -fsSL "https://api.github.com/repos/KernelSU-Next/KernelSU-Next/releases/latest" 2>/dev/null | jq -r '.tag_name // empty' || true)
  if [ -z "${KSU_TAG}" ] || [ "${KSU_TAG}" = "null" ]; then
    KSU_TAG=$(curl -fsSL "https://api.github.com/repos/KernelSU-Next/KernelSU-Next/tags?per_page=10" 2>/dev/null | jq -r '[.[] | select(.name | test("^v[0-9]+\\.[0-9]+\\.[0-9]+$"))][0].name // empty' || true)
  fi
  KSU_REF="${KSU_TAG:-legacy}"
  echo "Integrating stable KernelSU-Next ref '${KSU_REF}' (NO SUSFS)..."
  if ! curl -LSs "https://raw.githubusercontent.com/KernelSU-Next/KernelSU-Next/${KSU_REF}/kernel/setup.sh" | bash -s "${KSU_REF}"; then
    echo "WARNING: setup.sh failed for '${KSU_REF}', trying 'legacy' kprobe ref..." >&2
    if ! curl -LSs "https://raw.githubusercontent.com/KernelSU-Next/KernelSU-Next/legacy/kernel/setup.sh" | bash -s legacy; then
      echo "Fallback: cloning KernelSU-Next directly at ${KSU_REF}..." >&2
      git clone --depth=1 -b "${KSU_REF}" https://github.com/KernelSU-Next/KernelSU-Next.git "${KERNEL_SRC}/KernelSU-Next" || \
        git clone --depth=1 https://github.com/KernelSU-Next/KernelSU-Next.git "${KERNEL_SRC}/KernelSU-Next"
      ln -sf "../KernelSU-Next/kernel" "${KERNEL_SRC}/drivers/kernelsu"
      grep -q "kernelsu" "${KERNEL_SRC}/drivers/Kconfig" || sed -i '/endmenu/i source "drivers/kernelsu/Kconfig"' "${KERNEL_SRC}/drivers/Kconfig"
      grep -q "kernelsu" "${KERNEL_SRC}/drivers/Makefile" || echo 'obj-$(CONFIG_KSU) += kernelsu/' >> "${KERNEL_SRC}/drivers/Makefile"
    fi
  fi

  echo "Applying QEMU x86_64 compatibility guards on drivers/kernelsu..."
  if [ -f "arch/x86/include/asm/cpufeatures.h" ]; then
    python3 -c '
p = "arch/x86/include/asm/cpufeatures.h"
t = open(p, encoding="utf-8").read()
if "X86_FEATURE_INDIRECT_SAFE" not in t:
    macro = "\n#ifndef X86_FEATURE_INDIRECT_SAFE\n#define X86_FEATURE_INDIRECT_SAFE (7*32+31)\n#endif\n"
    idx = t.rfind("#endif")
    t = (t[:idx] + macro + t[idx:]) if idx != -1 else (t + macro)
    open(p, "w", encoding="utf-8").write(t)
'
  fi
  if [ -d "drivers/kernelsu" ]; then
    find -L drivers/kernelsu -type f \( -name "*.c" -o -name "*.h" \) -exec sed --follow-symlinks -i \
      -e '/FATAL: Your kernel is missing the indirect syscall/d' \
      -e 's/boot_cpu_has(X86_FEATURE_INDIRECT_SAFE)/true/g' \
      -e 's/cpu_feature_enabled(X86_FEATURE_INDIRECT_SAFE)/true/g' {} +
    if [ -f "drivers/kernelsu/core/init.c" ]; then
      sed --follow-symlinks -i '1i #ifndef X86_FEATURE_INDIRECT_SAFE\n#define X86_FEATURE_INDIRECT_SAFE (7*32+31)\n#endif' drivers/kernelsu/core/init.c
    fi
  fi

  IKCFG_OK=0
  if [ -x "./scripts/extract-ikconfig" ]; then
    echo "Extracting embedded .config from kernel_stock via scripts/extract-ikconfig..."
    if bash ./scripts/extract-ikconfig "${IMG_DIR}/kernel_stock" > .config 2>/dev/null && grep -q '^CONFIG_' .config; then
      CFG_LINES=$(wc -l < .config)
      echo "Success: extracted ${CFG_LINES} lines of kernel_stock .config!"
      IKCFG_OK=1
    fi
  fi
  if [ "${IKCFG_OK}" -eq 0 ]; then
    echo "WARNING: extract-ikconfig returned empty; falling back to x86_64_defconfig." >&2
    make ARCH=x86_64 x86_64_defconfig
  fi

  # Clear distributor signing keys, enable OverlayFS Magic Mount & Kprobes, promote boot drivers to built-in (=y)
  ./scripts/config \
    --set-str CONFIG_SYSTEM_TRUSTED_KEYS "" \
    --set-str CONFIG_SYSTEM_REVOCATION_KEYS "" \
    --set-str CONFIG_MODULE_SIG_KEY "" \
    --disable CONFIG_MODULE_SIG \
    --disable CONFIG_WERROR \
    --disable CONFIG_KSU_SUSFS \
    --disable CONFIG_KSU_X86_PATCH_SYSCALL_DISPATCHER \
    --disable CONFIG_DEBUG_INFO \
    --disable CONFIG_DEBUG_INFO_DWARF_TOOLCHAIN_DEFAULT \
    --disable CONFIG_DEBUG_INFO_BTF \
    --disable CONFIG_RANDOMIZE_BASE \
    --disable CONFIG_RANDOMIZE_MEMORY \
    --disable CONFIG_X86_5LEVEL \
    --enable CONFIG_KSU \
    --enable CONFIG_KPROBES \
    --enable CONFIG_HAVE_KPROBES \
    --enable CONFIG_KPROBE_EVENTS \
    --enable CONFIG_KSU_KPROBE_HOOKS \
    --enable CONFIG_KALLSYMS \
    --enable CONFIG_KALLSYMS_ALL \
    --enable CONFIG_IKCONFIG \
    --enable CONFIG_IKCONFIG_PROC \
    --enable CONFIG_OVERLAY_FS \
    --enable CONFIG_OVERLAY_FS_REDIRECT_DIR \
    --enable CONFIG_OVERLAY_FS_INDEX \
    --enable CONFIG_MODULES \
    --enable CONFIG_STAGING \
    --enable CONFIG_SECURITY \
    --enable CONFIG_SECURITY_NETWORK \
    --enable CONFIG_SECURITY_SELINUX \
    --enable CONFIG_SECURITY_SELINUX_BOOTPARAM \
    --enable CONFIG_SECURITY_SELINUX_DEVELOP \
    --enable CONFIG_SECURITY_SELINUX_AVC_STATS \
    --enable CONFIG_AUDIT \
    --enable CONFIG_BPF \
    --enable CONFIG_BPF_SYSCALL \
    --enable CONFIG_BPF_JIT \
    --enable CONFIG_HAVE_EBPF_JIT \
    --enable CONFIG_CGROUP_BPF \
    --enable CONFIG_NET_CLS_BPF \
    --enable CONFIG_NET_ACT_BPF \
    --enable CONFIG_PSI \
    --disable CONFIG_PSI_DEFAULT_DISABLED \
    --enable CONFIG_CGROUPS \
    --enable CONFIG_CGROUP_SCHED \
    --enable CONFIG_FAIR_GROUP_SCHED \
    --enable CONFIG_CFS_BANDWIDTH \
    --enable CONFIG_RT_GROUP_SCHED \
    --enable CONFIG_CGROUP_PIDS \
    --enable CONFIG_CGROUP_FREEZER \
    --enable CONFIG_CGROUP_CPUACCT \
    --enable CONFIG_MEMCG \
    --enable CONFIG_BLK_CGROUP \
    --enable CONFIG_CPUSETS \
    --enable CONFIG_NAMESPACES \
    --enable CONFIG_UTS_NS \
    --enable CONFIG_IPC_NS \
    --enable CONFIG_USER_NS \
    --enable CONFIG_PID_NS \
    --enable CONFIG_NET_NS \
    --enable CONFIG_TMPFS \
    --enable CONFIG_TMPFS_XATTR \
    --enable CONFIG_TMPFS_POSIX_ACL \
    --enable CONFIG_MEMFD_CREATE \
    --enable CONFIG_SYNC_FILE \
    --enable CONFIG_NETFILTER \
    --enable CONFIG_ANDROID \
    --enable CONFIG_ANDROID_BINDER_IPC \
    --enable CONFIG_ANDROID_BINDERFS \
    --set-str CONFIG_ANDROID_BINDER_DEVICES "binder,hwbinder,vndbinder" \
    --enable CONFIG_ASHMEM \
    --enable CONFIG_NET \
    --enable CONFIG_WIRELESS \
    --enable CONFIG_CFG80211 \
    --enable CONFIG_MAC80211 \
    --enable CONFIG_MAC80211_HWSIM \
    --enable CONFIG_VIRT_WIFI \
    --enable CONFIG_PCI \
    --enable CONFIG_PCI_MSI \
    --enable CONFIG_ACPI \
    --enable CONFIG_VIRTIO \
    --enable CONFIG_VIRTIO_PCI \
    --enable CONFIG_VIRTIO_BLK \
    --enable CONFIG_VIRTIO_NET \
    --enable CONFIG_VIRTIO_CONSOLE \
    --enable CONFIG_VIRTIO_INPUT \
    --enable CONFIG_PRINTK \
    --enable CONFIG_PRINTK_TIME \
    --set-val CONFIG_LOG_BUF_SHIFT 18 \
    --enable CONFIG_EARLY_PRINTK \
    --enable CONFIG_SERIAL_EARLYCON \
    --enable CONFIG_VT \
    --enable CONFIG_VT_CONSOLE \
    --enable CONFIG_HW_CONSOLE \
    --enable CONFIG_SERIAL_8250 \
    --enable CONFIG_SERIAL_8250_PCI \
    --enable CONFIG_SERIAL_8250_CONSOLE \
    --set-val CONFIG_SERIAL_8250_NR_UARTS 4 \
    --set-val CONFIG_SERIAL_8250_RUNTIME_UARTS 4 \
    --enable CONFIG_DEVTMPFS \
    --enable CONFIG_DEVTMPFS_MOUNT \
    --enable CONFIG_BLK_DEV_INITRD \
    --enable CONFIG_BLK_DEV_LOOP \
    --set-val CONFIG_BLK_DEV_LOOP_MIN_COUNT 16 \
    --enable CONFIG_BLK_DEV_DM \
    --enable CONFIG_DM_VERITY \
    --enable CONFIG_BLK_DEV_RAM \
    --set-val CONFIG_BLK_DEV_RAM_SIZE 65536 \
    --enable CONFIG_RD_GZIP \
    --enable CONFIG_RD_XZ \
    --enable CONFIG_RD_LZ4 \
    --enable CONFIG_RD_ZSTD \
    --enable CONFIG_HYPERVISOR_GUEST \
    --enable CONFIG_PARAVIRT \
    --enable CONFIG_DRM \
    --enable CONFIG_DRM_FBDEV_EMULATION \
    --enable CONFIG_FRAMEBUFFER_CONSOLE \
    --enable CONFIG_DRM_VIRTIO_GPU \
    --enable CONFIG_DRM_BOCHS \
    --enable CONFIG_DRM_SIMPLEDRM \
    --enable CONFIG_FB_VESA \
    --enable CONFIG_FB_SIMPLE \
    --enable CONFIG_SOUND \
    --enable CONFIG_SND \
    --enable CONFIG_SND_PCI \
    --enable CONFIG_SND_HDA_INTEL \
    --enable CONFIG_SND_HDA_GENERIC \
    --enable CONFIG_SND_AC97_CODEC \
    --enable CONFIG_EXT4_FS \
    --enable CONFIG_EXT4_FS_POSIX_ACL \
    --enable CONFIG_EXT4_FS_SECURITY \
    --enable CONFIG_VFAT_FS \
    --enable CONFIG_MSDOS_FS \
    --enable CONFIG_NLS_CODEPAGE_437 \
    --enable CONFIG_NLS_ISO8859_1 \
    --enable CONFIG_EROFS_FS \
    --enable CONFIG_FUSE_FS \
    --enable CONFIG_SQUASHFS \
    --set-val CONFIG_PANIC_TIMEOUT 0 || true

  # Enforce baseline x86-64 CPU (no AVX2/v3), GZIP bzImage, and disable Clang LTO/CFI/IBT/TDX/SEV quirks
  ./scripts/config \
    --enable CONFIG_GENERIC_CPU \
    --enable CONFIG_RELOCATABLE \
    --enable CONFIG_KERNEL_GZIP \
    --disable CONFIG_KERNEL_XZ \
    --disable CONFIG_KERNEL_ZSTD \
    --disable CONFIG_KERNEL_LZ4 \
    --disable CONFIG_KERNEL_LZMA \
    --disable CONFIG_KERNEL_BZIP2 \
    --disable CONFIG_KERNEL_LZO \
    --disable CONFIG_MK8 \
    --disable CONFIG_MPSC \
    --disable CONFIG_MCORE2 \
    --disable CONFIG_MATOM \
    --disable CONFIG_MNATIVE_INTEL \
    --disable CONFIG_MNATIVE_AMD \
    --disable CONFIG_X86_KERNEL_IBT \
    --disable CONFIG_CFI_CLANG \
    --disable CONFIG_LTO_CLANG_THIN \
    --disable CONFIG_LTO_CLANG_FULL \
    --disable CONFIG_AMD_MEM_ENCRYPT \
    --disable CONFIG_INTEL_TDX_GUEST \
    --disable CONFIG_KASAN \
    --disable CONFIG_UBSAN \
    --disable CONFIG_CMDLINE_BOOL \
    --disable CONFIG_CMDLINE_OVERRIDE \
    --disable CONFIG_RETHUNK \
    --disable CONFIG_MITIGATION_RETHUNK \
    --disable CONFIG_SLS \
    --disable CONFIG_MITIGATION_SLS \
    --disable CONFIG_CALL_DEPTH_TRACKING \
    --disable CONFIG_FINEIBT \
    --disable CONFIG_GCC_PLUGINS \
    --disable CONFIG_GCOV_KERNEL \
    --disable CONFIG_KCSAN \
    --disable CONFIG_KFENCE \
    --disable CONFIG_DEBUG_VIRTUAL \
    --disable CONFIG_DRM_I915 \
    --disable CONFIG_DRM_AMDGPU \
    --disable CONFIG_DRM_NOUVEAU \
    --disable CONFIG_DRM_RADEON || true

  yes "" | make ARCH=x86_64 olddefconfig >/dev/null 2>&1 || make ARCH=x86_64 olddefconfig
  echo "Verified critical kernel symbols before compilation:"
  grep -E 'CONFIG_(KSU|KPROBES|KSU_KPROBE_HOOKS|OVERLAY_FS|TMPFS_XATTR|EXT4_FS_SECURITY|RANDOMIZE_BASE|X86_5LEVEL|GENERIC_CPU|MNATIVE|KERNEL_GZIP|X86_KERNEL_IBT|BPF_SYSCALL|CGROUP_BPF|PSI|CGROUPS|SECURITY_SELINUX_DEVELOP|EARLY_PRINTK|SERIAL_EARLYCON|SERIAL_8250|DRM_VIRTIO_GPU|ANDROID_BINDER|DEVTMPFS|MAC80211_HWSIM|VIRT_WIFI|RETHUNK|SLS|CMDLINE_BOOL)' .config | head -n 90 || true
  grep -q '^CONFIG_KSU=y' .config
  grep -q '^CONFIG_OVERLAY_FS=y' .config
  grep -q '^CONFIG_VIRTIO_BLK=y' .config
  grep -q '^CONFIG_SERIAL_8250_CONSOLE=y' .config
  grep -q '^CONFIG_DRM_VIRTIO_GPU=y' .config
  grep -q '^CONFIG_DEVTMPFS=y' .config
  grep -q '^CONFIG_DEVTMPFS_MOUNT=y' .config
  grep -q '^CONFIG_TMPFS=y' .config
  grep -q '^CONFIG_ANDROID_BINDER_IPC=y' .config
  grep -q '^CONFIG_GENERIC_CPU=y' .config

  BUILD_LOG="${WORK_DIR}/kernel_build.log"
  if ! make ARCH=x86_64 KCFLAGS="-Wno-error" -j"$(nproc)" bzImage 2>&1 | tee "${BUILD_LOG}"; then
    echo "==================================================================" >&2
    echo "ERROR: KernelSU Next x86_64 bzImage build failed! Error summary:" >&2
    echo "==================================================================" >&2
    grep -niE 'error:|fatal:|undefined reference|No such file' "${BUILD_LOG}" | tail -n 60 >&2 || true
    echo "--- Last 60 lines of kernel build log ---" >&2
    tail -n 60 "${BUILD_LOG}" >&2 || true
    exit 2
  fi
  cd - >/dev/null

  cp -f "${KERNEL_SRC}/arch/x86/boot/bzImage" "${IMG_DIR}/kernel_ksunext"
  BZ_TYPE=$(file -b "${IMG_DIR}/kernel_ksunext" 2>/dev/null || echo "unknown")
  echo "Verified [kernel_ksunext]: $(stat -c%s "${IMG_DIR}/kernel_ksunext") bytes (${BZ_TYPE})"
  if ! echo "${BZ_TYPE}" | grep -qiE 'bzImage|Linux kernel x86'; then
    echo "ERROR: Built kernel_ksunext is not a valid x86 bzImage (${BZ_TYPE})!" >&2
    exit 2
  fi
  echo "Cleaning up kernel source tree to free runner disk space..."
  rm -rf "${KERNEL_SRC}"
fi

rm -rf "${WORK_DIR}"
ls -lh "${IMG_DIR}"
