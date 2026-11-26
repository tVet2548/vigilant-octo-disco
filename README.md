# Portable Android 13 (LineageOS 20.0 GApps x86_64) for Windows 11

Automated GitHub Actions CI/CD pipeline and Windows 11 portable launcher engineered for **Android 13 (API 33)** parity (**LineageOS 20.0 GApps + Bliss OS 16.9 vendor/initrd**) on **Intel Core i5-3475S (Ivy Bridge)** and **Intel HD Graphics 4000** (OpenGL 4.0 / DirectX 11 via Google ANGLE — Vulkan disabled).

## Key Highlights

- **100% API 33 Stack & Single-File Release (`< 1.95 GB`)**: Pairs **LineageOS 20.0 GApps `x86_64` (`bgN` / Waydroid GAPPS)** with **Bliss OS 16.9 (API 33)** `vendor.img`, `kernel_stock`, and dual `initrd` images; shrunk with `e2fsck -f -y` + `resize2fs -M`, compressed via `qemu-img convert -c -O qcow2`, and archived with `7z -mx=9 -m0=lzma2 -md=128m -ms=on`.
- **Dual Kernel + Dual Initrd Hot-Switch**:
  - `kernel_stock` + `initrd_stock.img`: Clean unrooted Android 13 + GApps boot.
  - `kernel_ksunext` + `initrd_ksunext.img`: Matched `extract-ikconfig` Linux `6.1` kernel with stable **KernelSU Next**, `CONFIG_OVERLAY_FS=y`, `CONFIG_KPROBES=y`, and verified `x86-64` `/sbin/ksud` pre-staged for Magic Mount.
- **Intel i5-3475S + HD 4000 Hardware Tuning**: Prioritizes WHPX (`-accel whpx,kernel-irqchip=off`) / AEHD / HAXM cascading through `-cpu host` -> `-cpu IvyBridge,+ssse3,+sse4.1,+sse4.2,+popcnt` -> `-cpu Nehalem` (and safe `-accel tcg,thread=multi -cpu IvyBridge,+ssse3,+sse4.1,+sse4.2,+popcnt`, strictly zero AVX2/AVX512/BMI2), with `virtio-vga-gl` (`ANGLE_DEFAULT_PLATFORM=d3d11`) and automatic `-vga std` software fallback.
- **Bilingual Common-Sense Launcher (`VI / EN`) & Stealth Suite**: Live CMD console (`dmesg` + `adb logcat`), **All-in-One `Portable_Stealth_KSU.zip`** (`Home_WiFi_5G` `wlan0`, 75%–88% battery simulation), **Waydroid Multi-Window (`scrcpy --new-display --start-app`)**, drag-and-drop `.apk`/`.zip`, 2-way clipboard, and 16 GB pre-formatted `ext4` `data.img`.

## Windows 11 Quick Start

1. Download `Portable_Android13_Win11.7z` from **GitHub Releases**.
2. Extract with 7-Zip to any drive/folder (e.g., `D:\PortableAndroid13`).
3. Double-click `AndroidLauncher.exe` (both the GUI and CMD log console will launch together).
4. Toggle **Root ON (KernelSU Next)** or **Clean Stock**, choose SELinux mode & Phone Disguise, and click **Start Android VM**.
