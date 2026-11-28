# QEMU / Android 13 boot diagnostics

## Supported baseline

The CI baseline for Intel Ivy Bridge is QEMU TCG, software VirtIO VGA with an SDL
display backed by Xvfb, and an E1000 NIC. The runner must install the separate
`qemu-system-gui` package; `qemu-system-x86` alone may lack the SDL display backend. VirGL remains optional; host OpenGL is
not required for the software path.

The guest uses QEMU's negotiated VirtIO display mode; no custom 1280x720 DRM
modeline is forced. Xvfb supplies a real display backend instead of using
`-display none`, so the guest's display/HWC path is exercised in CI.

The kernel command line retains `console=ttyS0`, `earlycon` and `earlyprintk`
for kernel and init-wrapper diagnostics, but omits `androidboot.console=ttyS0`
and `SERIAL=ttyS0`. Android framework services should not inherit the diagnostic
UART as their Android console. The init wrapper separately mirrors kernel messages
to the serial log.

## Previous failure evidence

The failed run `46115043624` at commit `0748312` established:

* KernelSU reached Android userspace; `netd` exited with status 1 at about 64 seconds.
  Android init then restarted zygote.
* SELinux logged denials for `netd`, zygote and other domains accessing
  `/dev/ttyS0`, whose runtime target label was `u:object_r:device:s0`.
  This is a console/label mismatch signal, but the log did not include the netd
  exception or tombstone, so it was not enough to prove the cause.
* Stock kernel did not emit `BOOT_COMPLETED` within 900 seconds.
* The previous CI regex missed init's `received signal 6` form. The signals in
  the final tail occurred at the end of the timed-out run; without a crash backtrace
  they must not be treated as the proven original cause of the stock boot failure.

The earlier run also showed successful BPF object loading and E1000 driver
registration. Neither proves complete networking, and neither proves BPF or the
NIC caused the netd exit.

## Runtime and CI changes

* Portable init enables ADB TCP on guest port 5555. QEMU forwards it only to host
  loopback; CI uses host port 5556.
* CI runs QEMU's SDL software display under Xvfb, keeping the VirtIO VGA display
  path active without host GPU acceleration.
* The Android framework console override is removed while kernel UART diagnostics
  remain enabled.
* The smoke test captures serial, QEMU stderr, QEMU guest debug, full Android logcat,
  guest properties, interface addresses, routes, SurfaceFlinger state and tombstone
  directory visibility.
* It detects non-zero exits and SIGABRT/SIGSEGV (signals 6/11) for netd, HWC,
  SurfaceFlinger and zygote. It does not misclassify an init-issued SIGKILL as an
  independent crash.
* It requires the boot-complete marker, ADB reachability, E1000 DHCP IPv4 address,
  QEMU user-network default route and a 90-second stability soak.
* Diagnostics upload as a GitHub Actions artifact with `if: always()`, including
  when the smoke test fails.

## Local diagnostics

```bat
bin\adb.exe connect 127.0.0.1:5555
bin\adb.exe -s 127.0.0.1:5555 logcat -b all -v threadtime > android-logcat-manual.txt
bin\adb.exe -s 127.0.0.1:5555 shell getprop sys.boot_completed
bin\adb.exe -s 127.0.0.1:5555 shell ip addr
bin\adb.exe -s 127.0.0.1:5555 shell ip route
```

## Validation limits

Static validation proves source/shell contracts only. Both KernelSU and stock QEMU
boot tests must pass before this runtime change is considered verified. The QEMU
user-network checks DHCP and the default gateway; it does not by itself prove
public Internet access, DNS reliability, Play Integrity, game compatibility or
physical Intel HD 4000 acceleration.

Do not add broad SELinux allow rules, disable BPF, or switch SELinux to permissive
without a crash trace tying one of those components to the failure.
