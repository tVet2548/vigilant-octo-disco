# QEMU / Android 13 boot diagnostics

## Supported baseline

The conservative profile for Intel Ivy Bridge / HD Graphics 4000 is QEMU TCG or WHPX,
VirtIO VGA in software mode, and an E1000 network adapter. VirGL remains an opt-in
experiment: failure to create a host OpenGL 3.0 context must not prevent Android from
starting through the software graphics path.

The launcher no longer forces a 1280x720 custom mode on VirtIO VGA. A captured guest
log rejected that user-defined DRM mode as unsupported. QEMU's advertised display mode
should be negotiated instead of forcing a modeline the guest rejected.

The TCG IvyBridge model masks `ht` and `tsc-deadline`, which TCG warned it could not
provide in the supplied QEMU stderr. Those CPUID warnings were not the cause of Android's
framework restart, but leaving unsupported features enabled made diagnostics noisy.

## Confirmed failure signatures

* **Host VirGL initialization:** QEMU reports that it cannot create an OpenGL 3.0 context
  and that vrend cannot initialize. Guest VirtIO GPU capset negotiation may then time out.
  This is a host renderer failure, not evidence of a kernel panic. Use the software VirtIO
  VGA mode as the baseline.
* **Unsupported DRM mode:** the guest rejected a forced `1280x720` user-defined mode.
  The launcher and CI smoke test no longer inject the `xres/yres` device properties.
* **Android networking/framework:** the supplied serial log shows `netd` exiting with
  status 1 more than once. Android init's `netd` `onrestart` actions then kill/restart
  zygote. The same run detected the E1000 driver, and the BPF loader reported successful
  object loads. These details do not establish why `netd` exits. Do not claim that changing
  the NIC model or disabling BPF fixes the service without the actual process error/crash
  context.

## What changed

* The launcher and Linux QEMU smoke test use E1000. The kernel build explicitly enables
  `NETDEVICES`, `ETHERNET`, `NET_VENDOR_INTEL` and `E1000` so the selected NIC is part
  of the generated kernel configuration, rather than relying on a defconfig default.
* The host ADB forward binds to `127.0.0.1` only.
* The launcher records all Android logcat buffers with thread time and rotates the current
  capture at 32 MiB:
  * `logs/android-logcat.log`
  * `logs/android-logcat.previous.log`
* The serial parser calls out a non-zero `netd` exit and the init ramdisk emits an explicit
  `[PORTABLE-BOOT] BOOT_COMPLETED=1` marker when Android sets `sys.boot_completed=1`.
* CI now waits up to 15 minutes for that Android boot-complete marker, fails on a non-zero
  `netd`, HWC or SurfaceFlinger exit, and then requires a 90-second stability soak.
* The ZIP ingestion workflow accepts both historical archive names, validates paths and
  symlink entries, caps the expanded size, and uses a normal fast-forward push instead of
  force-pushing or amending branch history.

## Capture the actual netd failure

The launcher writes a full logcat capture once ADB is reachable. Preserve the `logs`
directory when reporting a failure.

Manual capture from a second Windows terminal:

```bat
bin\adb.exe connect 127.0.0.1:5555
bin\adb.exe -s 127.0.0.1:5555 logcat -b all -v threadtime > android-logcat-manual.txt
```

Useful checks after ADB is online:

```bat
bin\adb.exe -s 127.0.0.1:5555 shell getprop sys.boot_completed
bin\adb.exe -s 127.0.0.1:5555 shell getprop init.svc.netd
bin\adb.exe -s 127.0.0.1:5555 shell ip addr
bin\adb.exe -s 127.0.0.1:5555 shell ip route
```

## CI coverage and limits

The QEMU TCG smoke test boots the KernelSU and stock kernel/initrd pairs with SELinux
Enforcing, software VirtIO VGA and E1000 user networking. It verifies the init-emitted
Android boot-complete marker, and that `netd`, HWC and SurfaceFlinger do not exit during
the post-boot window.

This smoke test is not a full internet-connectivity test: it does not independently prove
DHCP lease acquisition, DNS resolution or traffic to an external host. Those require an
ADB-driven guest network test or a Windows-host runtime test. It also does not prove
Google Play certification, game compatibility, or physical Intel GPU acceleration.

The root cause of the previously observed `netd` exit remains unconfirmed until its
captured logcat/crash context is inspected. A correct diagnostic workflow must preserve
that uncertainty instead of papering over it with a speculative property, SELinux allow
rule, or BPF disable.
