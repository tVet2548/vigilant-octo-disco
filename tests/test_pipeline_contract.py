from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class QemuAndroidPipelineContractTests(unittest.TestCase):
    def read(self, relative_path: str) -> str:
        return (ROOT / relative_path).read_text(encoding="utf-8")

    def test_launcher_uses_loopback_adb_forward_and_e1000(self):
        source = self.read("src/launcher.py")
        self.assertIn("hostfwd=tcp:127.0.0.1:5555-:5555", source)
        self.assertIn('"e1000,netdev=net0"', source)
        self.assertNotIn("hostfwd=tcp::5555-:5555", source)
        self.assertNotIn('"virtio-net-pci,netdev=net0"', source)

    def test_software_virtio_mode_uses_real_headless_display(self):
        source = self.read("src/launcher.py")
        smoke = self.read("scripts/qemu_boot_smoke.sh")
        self.assertIn('"-device", "virtio-vga", "-display", "sdl,gl=off"', source)
        self.assertIn("-display sdl,gl=off", smoke)
        self.assertIn("xvfb-run -a", smoke)
        workflow = self.read(".github/workflows/build.yml")
        self.assertIn("qemu-system-gui", workflow)
        self.assertIn("setsid xvfb-run -a", smoke)
        self.assertIn('kill -TERM -- "-$qpid"', smoke)
        self.assertNotIn("-display none", smoke)
        self.assertNotIn("xres=1280,yres=720", source)
        self.assertNotIn("xres=1280,yres=720", smoke)

    def test_tcg_cpu_does_not_request_unavailable_features(self):
        source = self.read("src/launcher.py")
        workflow = self.read(".github/workflows/build.yml")
        expected = "IvyBridge,-ht,-tsc-deadline,+ssse3,+sse4.1,+sse4.2,+popcnt"
        self.assertIn(expected, source)
        self.assertIn(expected, workflow + self.read("scripts/qemu_boot_smoke.sh"))

    def test_kernel_build_enables_e1000_driver_explicitly(self):
        source = self.read("scripts/build_ksu_kernel.sh")
        self.assertIn("--enable CONFIG_NETDEVICES", source)
        self.assertIn("--enable CONFIG_ETHERNET", source)
        self.assertIn("--enable CONFIG_NET_VENDOR_INTEL", source)
        self.assertIn("--enable CONFIG_E1000", source)

    def test_full_logcat_is_persisted_with_real_line_endings(self):
        source = self.read("src/launcher.py")
        self.assertIn('"logcat", "-b", "all", "-v", "threadtime"', source)
        self.assertIn("android-logcat.log", source)
        self.assertIn("android-logcat.previous.log", source)
        self.assertIn('line.rstrip("\\r\\n")', source)
        self.assertIn('log_file.write(clean + "\\n")', source)
        self.assertIn("log_bytes_written += len", source)

    def test_netd_exit_is_reported_and_boot_complete_is_marked(self):
        launcher = self.read("src/launcher.py")
        patch = self.read("scripts/patch_system_img.sh")
        self.assertIn("netd_fail_count", launcher)
        self.assertIn("[portable-boot] boot_completed=1", launcher.lower())
        self.assertIn('write /dev/kmsg "[PORTABLE-BOOT] BOOT_COMPLETED=1"', patch)

    def test_ci_boot_gate_checks_runtime_crashes_adb_and_dhcp(self):
        workflow = self.read(".github/workflows/build.yml")
        smoke = self.read("scripts/qemu_boot_smoke.sh")
        self.assertIn("BOOT_TIMEOUT_SECONDS", smoke)
        self.assertIn("SOAK_SECONDS", smoke)
        self.assertIn("[PORTABLE-BOOT] BOOT_COMPLETED=1", smoke)
        self.assertIn("received signal (6|11)", smoke)
        self.assertIn("Service 'netd'", smoke)
        self.assertIn("hostfwd=tcp:127.0.0.1:5556-:5555", smoke)
        self.assertIn("logcat -b all -v threadtime", smoke)
        self.assertIn("androidboot.portable_ci=1", smoke)
        self.assertIn("POST_FAILURE_ADB_GRACE_SECONDS", smoke)
        self.assertIn("tombstone", smoke)
        self.assertIn("ip route show default", smoke)
        self.assertIn("-device e1000,netdev=net0", smoke)
        self.assertIn("xvfb-run -a", smoke)
        self.assertIn("if: always()", workflow)
        self.assertIn("qemu-android-diagnostics", workflow)
        self.assertIn("sys.boot_completed", self.read("docs/boot-diagnostics.md"))

    def test_android_boot_keeps_early_uart_logging_without_framework_console(self):
        smoke = self.read("scripts/qemu_boot_smoke.sh")
        launcher = self.read("src/launcher.py")
        self.assertIn("earlycon=uart8250,io,0x3f8,115200", smoke)
        self.assertIn("earlyprintk=serial,ttyS0,115200,keep", smoke)
        self.assertIn("androidboot.console=null", smoke)
        self.assertIn("androidboot.console=null", launcher)
        self.assertNotIn("console=ttyS0", smoke)
        self.assertNotIn("console=tty0", launcher)
        self.assertNotIn("androidboot.console=ttyS0", smoke + launcher)
        self.assertNotIn("SERIAL=ttyS0", smoke + launcher)

    def test_surfaceflinger_ioctl_policy_matches_only_observed_drm_commands(self):
        patch = self.read("scripts/patch_system_img.sh")
        self.assertIn('plat_rules.append(f"(allowx {src} {tgt} (ioctl {cls} ({commands})))")', patch)
        self.assertIn('add_plat_allowx("surfaceflinger", "gpu_device", "chr_file", "0x6400 0x640c 0x6443")', patch)
        self.assertIn('add_plat_allowx("surfaceflinger", "dri_device", "chr_file", "0x6400 0x640c 0x6443")', patch)
        self.assertNotIn('plat_rules.append(f"(allowxperm ', patch)
        self.assertNotIn('add_plat_allowx("surfaceflinger", "device"', patch)

    def test_ci_logcat_service_has_valid_selinux_domain_and_socket_access(self):
        patch = self.read("scripts/patch_system_img.sh")
        self.assertIn('seclabel u:r:droidport_gfx:s0', patch)
        self.assertIn('add_plat_allow("droidport_gfx", "logcat_exec", "file"', patch)
        self.assertIn('add_plat_allow("droidport_gfx", "logdr_socket", "sock_file", "getattr write")', patch)
        self.assertIn('add_plat_allow("droidport_gfx", "logd", "unix_stream_socket"', patch)
        self.assertIn('add_plat_allow(_sf_domain, "gpu_device", "chr_file"', patch)
        self.assertIn('add_plat_allow("hal_graphics_allocator_default", "tty_device"', patch)
        self.assertIn('add_ven_allow(("surfaceflinger",', patch)
        self.assertIn('add_ven_allow(("hal_graphics_composer_default",), "self", "capability", "net_admin")', patch)
        self.assertIn('add_ven_allow(("hal_graphics_allocator_default",), (f"default_prop_{plat_ver.replace', patch)
        self.assertIn('ro.adb.secure=0', patch)
        self.assertIn('persist.adb.tcp.port=5555', patch)
        self.assertIn('"ctl_start_prop"', patch)
        self.assertIn('"exported_config_prop"', patch)
        mirror = self.read("scripts/portable_ci_logcat_mirror.sh")
        self.assertIn("exec /system/bin/logcat -b all -v threadtime", mirror)
        self.assertIn("stdio_to_kmsg", patch)


    def test_bliss_init_and_ksu_hooks_do_not_run_in_graphics_domain(self):
        patch = self.read("scripts/patch_system_img.sh")
        self.assertIn("SYS_BUILD_TYPE=", patch)
        self.assertIn('userdebug|eng) PORTABLE_PRIV_SECLABEL="u:r:su:s0"', patch)
        self.assertIn('f"exec {priv_domain} -- "', patch)
        self.assertIn("exec ${PORTABLE_PRIV_SECLABEL} -- /system/bin/sh /system/etc/init.sh", patch)
        self.assertNotIn('exec u:r:droidport_gfx:s0 -- /system/bin/sh -c "if [ -x /data/adb/ksud ]', patch)
        # KernelSU's own generated init.rc installs this native hook at runtime;
        # the portable patch must not add a second invocation in its graphics domain.
        self.assertIn("restorecon_recursive /data/adb", patch)

    def test_gralloc_allocator_receives_read_only_property_and_sysfs_access(self):
        patch = self.read("scripts/patch_system_img.sh")
        self.assertIn('add_plat_allow("hal_graphics_allocator_default", "default_prop", "file", "read open getattr map")', patch)
        self.assertIn('add_plat_allow("hal_graphics_allocator_default", "system_prop", "file", "read open getattr map")', patch)
        self.assertIn('add_plat_allow("hal_graphics_allocator_default", "sysfs", "file", "read open getattr")', patch)

    def test_portable_image_enables_adb_tcp(self):
        patch = self.read("scripts/patch_system_img.sh")
        self.assertIn("setprop persist.sys.usb.config adb", patch)
        self.assertIn("setprop service.adb.tcp.port 5555", patch)

    def test_qemu_smoke_has_executable_regex_self_test(self):
        smoke = self.read("scripts/qemu_boot_smoke.sh")
        validate = self.read(".github/workflows/validate.yml")
        self.assertIn('--self-test', smoke)
        self.assertIn('bash scripts/qemu_boot_smoke.sh --self-test', validate)

    def test_qemu_smoke_persists_serial_qemu_logcat_and_guest_state(self):
        smoke = self.read("scripts/qemu_boot_smoke.sh")
        for name in ("serial.log", "qemu.stderr.log", "qemu.debug.log", "guest.logcat.log", "guest-state.log"):
            self.assertIn(name, smoke)
        self.assertIn('"$ADB_BIN" -s "$ADB_SERIAL" shell getprop', smoke)

    def test_disk_cleanup_skips_when_runner_already_has_required_free_space(self):
        cleanup = self.read("scripts/cleanup_disk.sh")
        self.assertIn('AVAIL_GB=$((AVAIL_KB / 1024 / 1024))', cleanup)
        self.assertIn('if [ "${AVAIL_GB}" -ge 45 ]; then', cleanup)
        self.assertIn('skipping destructive toolchain cleanup', cleanup)

    def test_qemu_stock_kernel_is_built_without_ksu_but_with_virtio_graphics_and_e1000(self):
        build = self.read("scripts/build_ksu_kernel.sh")
        self.assertIn("kernel_bliss_original", build)
        self.assertIn('configure_ksunext_config "stock-llvm" --stock LLVM=1 LLVM_IAS=1', build)
        self.assertIn("./scripts/config --disable CONFIG_KSU", build)
        self.assertIn("grep -q '^# CONFIG_KSU is not set' .config", build)
        self.assertIn("grep -q '^CONFIG_DRM_VIRTIO_GPU=y' .config", build)
        self.assertIn("grep -q '^CONFIG_E1000=y' .config", build)
        self.assertIn("build_stock_kernel", build)

        stock_start = build.index("  build_stock_kernel() {")
        stock_end = build.index("\n  build_stock_kernel\n", stock_start)
        stock_fn = build[stock_start:stock_end]
        self.assertNotIn(r"\${", stock_fn)

    def test_ci_drmfb_hwc_requires_a_real_framebuffer(self):
        patch = self.read("scripts/patch_system_img.sh")
        self.assertIn('HAS_FB=0', patch)
        self.assertIn("[ -c /dev/fb0 ] && HAS_FB=1", patch)
        self.assertIn("[ -c /dev/dri/card0 ] && HAS_DRI=1", patch)
        self.assertIn('if [ "${HAS_FB}" -eq 1 ] && { [ -x /vendor/bin/hw/android.hardware.graphics.composer@2.1-drmfb-service ]', patch)
        self.assertIn('elif [ "${HAS_DRI}" -eq 1 ] && {', patch)
        self.assertIn('setprop portable.hwc.svc v21', patch)

    def test_ci_logcat_mirror_captures_native_crash_backtraces(self):
        mirror = self.read("scripts/portable_ci_logcat_mirror.sh")
        patch = self.read("scripts/patch_system_img.sh")
        self.assertIn("exec /system/bin/logcat -b all -v threadtime", mirror)
        self.assertIn("stdio_to_kmsg", patch)
        self.assertNotIn("while IFS= read -r line", mirror)
        self.assertNotIn("/system/bin/seq", mirror)

    def test_zip_workflow_is_path_safe_and_never_rewrites_history(self):
        workflow = self.read(".github/workflows/main.yml")
        self.assertIn('"Chess4.zip"', workflow)
        self.assertIn('"imz.zip"', workflow)
        self.assertIn("users.noreply.github.com", workflow)
        self.assertIn("Path escapes repository root", workflow)
        self.assertIn("max_uncompressed = 2 * 1024 * 1024 * 1024", workflow)
        self.assertNotIn("git push --force", workflow)
        self.assertNotIn("git commit --amend", workflow)
        self.assertIn('git push origin "HEAD:${GITHUB_REF_NAME}"', workflow)


if __name__ == "__main__":
    unittest.main()
