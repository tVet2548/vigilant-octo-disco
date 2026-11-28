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

    def test_software_virtio_mode_does_not_force_custom_modeline(self):
        source = self.read("src/launcher.py")
        workflow = self.read(".github/workflows/build.yml")
        self.assertIn('"-device", "virtio-vga", "-display", "sdl,gl=off"', source)
        self.assertNotIn("xres=1280,yres=720", source)
        self.assertNotIn("xres=1280,yres=720", workflow)

    def test_tcg_cpu_does_not_request_unavailable_features(self):
        source = self.read("src/launcher.py")
        workflow = self.read(".github/workflows/build.yml")
        expected = "IvyBridge,-ht,-tsc-deadline,+ssse3,+sse4.1,+sse4.2,+popcnt"
        self.assertIn(expected, source)
        self.assertIn(expected, workflow)

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

    def test_ci_waits_for_android_boot_and_checks_post_boot_stability(self):
        workflow = self.read(".github/workflows/build.yml")
        self.assertIn("BOOT_TIMEOUT_SECONDS=900", workflow)
        self.assertIn("SOAK_SECONDS=90", workflow)
        self.assertIn("[PORTABLE-BOOT] BOOT_COMPLETED=1", workflow)
        self.assertIn("Service 'netd'.*exited with status [1-9]", workflow)
        self.assertIn("-device e1000,netdev=net0", workflow)
        self.assertNotIn("seq 1 135", workflow)
        self.assertIn("sys.boot_completed", self.read("docs/boot-diagnostics.md"))

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
