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

    def test_android_boot_does_not_assign_framework_console_to_uart(self):
        smoke = self.read("scripts/qemu_boot_smoke.sh")
        self.assertIn("console=ttyS0,115200", smoke)
        self.assertNotIn("androidboot.console=ttyS0", smoke)
        self.assertNotIn("SERIAL=ttyS0", smoke)

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

    def test_ci_drmfb_hwc_requires_a_real_framebuffer(self):
        patch = self.read("scripts/patch_system_img.sh")
        self.assertIn('HAS_FB=0', patch)
        self.assertIn('[ -e /dev/fb0 ] || [ -e /sys/class/graphics/fb0 ]', patch)
        self.assertIn('if [ "${HAS_FB}" -eq 1 ] && { [ -x /vendor/bin/hw/android.hardware.graphics.composer@2.1-drmfb-service ]', patch)
        self.assertIn('setprop portable.hwc.svc v21', patch)

    def test_ci_logcat_mirror_captures_native_crash_backtraces(self):
        mirror = self.read("scripts/portable_ci_logcat_mirror.sh")
        self.assertIn("*debuggerd*", mirror)
        self.assertIn("*DEBUG*", mirror)
        self.assertIn("*Abort message*", mirror)
        self.assertIn('printf \'<6>PORTABLE-LOGCAT %.900s\\n\' "$line"', mirror)
        self.assertNotIn('\\${line:0:900}', mirror)

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
