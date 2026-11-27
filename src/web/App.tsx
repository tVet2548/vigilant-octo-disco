import { useMemo, useState } from "react";
import {
  Activity,
  CheckCircle2,
  Copy,
  Cpu,
  Languages,
  ShieldCheck,
  Smartphone,
  Terminal,
  Wrench,
} from "lucide-react";

type Lang = "vi" | "en";
type TabKey = "diagnostics" | "qemu" | "spoof";

interface DeviceProfile {
  key: string;
  brand: string;
  manufacturer: string;
  model: string;
  device: string;
  product: string;
  board: string;
  platform: string;
  hardware: string;
  fingerprint: string;
  security_patch: string;
  build_id: string;
  incremental: string;
  first_api_level: string;
}

const DEVICE_PROFILES: Record<string, DeviceProfile> = {
  "Google Pixel 8 Pro": {
    key: "pixel8pro",
    brand: "google",
    manufacturer: "Google",
    model: "Pixel 8 Pro",
    device: "husky",
    product: "husky",
    board: "husky",
    platform: "zuma",
    hardware: "husky",
    fingerprint: "google/husky/husky:14/AP2A.240905.003/12231197:user/release-keys",
    security_patch: "2024-09-05",
    build_id: "AP2A.240905.003",
    incremental: "12231197",
    first_api_level: "34",
  },
  "Xiaomi 14": {
    key: "xiaomi14",
    brand: "Xiaomi",
    manufacturer: "Xiaomi",
    model: "23127PN0CG",
    device: "houji",
    product: "houji_global",
    board: "pineapple",
    platform: "pineapple",
    hardware: "qcom",
    fingerprint: "Xiaomi/houji_global/houji:14/UKQ1.231003.002/V816.0.14.0.UNCMIXM:user/release-keys",
    security_patch: "2024-08-01",
    build_id: "UKQ1.231003.002",
    incremental: "V816.0.14.0.UNCMIXM",
    first_api_level: "34",
  },
  "Samsung Galaxy S24 Ultra": {
    key: "s24ultra",
    brand: "samsung",
    manufacturer: "samsung",
    model: "SM-S928B",
    device: "e3q",
    product: "e3qxxx",
    board: "pineapple",
    platform: "pineapple",
    hardware: "qcom",
    fingerprint: "samsung/e3qxxx/e3q:14/UP1A.231005.007/S928BXXS3AXH7:user/release-keys",
    security_patch: "2024-08-01",
    build_id: "UP1A.231005.007",
    incremental: "S928BXXS3AXH7",
    first_api_level: "34",
  },
  "ROG Phone 8": {
    key: "rog8",
    brand: "asus",
    manufacturer: "ASUSTeK COMPUTER INC.",
    model: "ASUS_AI2401",
    device: "ASUS_AI2401",
    product: "WW_AI2401",
    board: "pineapple",
    platform: "pineapple",
    hardware: "qcom",
    fingerprint: "asus/WW_AI2401/ASUS_AI2401:14/UKQ1.230924.001/34.1420.1420.415:user/release-keys",
    security_patch: "2024-08-05",
    build_id: "UKQ1.230924.001",
    incremental: "34.1420.1420.415",
    first_api_level: "34",
  },
};

const COPY = {
  vi: {
    title: "Portable Android 13 · Diagnostics & Launcher Console",
    sub: "LineageOS 20.0 GApps x86_64 + Bliss OS 16.9 (API 33) · Intel i5-3475S / HD 4000",
    tabDiag: "Phân Tích & Đã Sửa Lỗi Boot",
    tabQemu: "Cấu Hình QEMU (Windows 11)",
    tabSpoof: "Hồ Sơ Spoof & PIF",
    fixesTitle: "Nguyên nhân & Bản vá đã áp dụng",
    captureTitle: "Ảnh lỗi gốc: Treo tại switch_root & CMD Select",
    qemuTitle: "Trình tạo lệnh QEMU (Intel i5-3475S + HD 4000)",
    copyCmd: "Copy lệnh QEMU",
    copied: "Đã copy!",
  },
  en: {
    title: "Portable Android 13 · Diagnostics & Launcher Console",
    sub: "LineageOS 20.0 GApps x86_64 + Bliss OS 16.9 (API 33) · Intel i5-3475S / HD 4000",
    tabDiag: "Boot-Hang Root Causes & Fixes",
    tabQemu: "QEMU Builder (Windows 11)",
    tabSpoof: "Device Spoof & PIF",
    fixesTitle: "Root Causes & Applied Fixes",
    captureTitle: "Reported Capture: Hung at switch_root & CMD Select",
    qemuTitle: "QEMU Command Builder (Intel i5-3475S + HD 4000)",
    copyCmd: "Copy QEMU Command",
    copied: "Copied!",
  },
} as const;

export default function App() {
  const [lang, setLang] = useState<Lang>("vi");
  const [tab, setTab] = useState<TabKey>("diagnostics");
  const [ksuEnabled, setKsuEnabled] = useState(true);
  const [accel, setAccel] = useState<"whpx_host" | "whpx_ivy" | "tcg_ivy">("whpx_host");
  const [gpu, setGpu] = useState<"angle" | "virtio_sw" | "software">("angle");
  const [cores, setCores] = useState(3);
  const [ramGb, setRamGb] = useState(4);
  const [selectedDevice, setSelectedDevice] = useState<string>("Google Pixel 8 Pro");
  const [copied, setCopied] = useState(false);

  const t = COPY[lang];

  const qemuCmd = useMemo(() => {
    const kernel = ksuEnabled ? "images/kernel_ksunext" : "images/kernel_stock";
    const initrd = ksuEnabled ? "images/initrd_ksunext.img" : "images/initrd_stock.img";
    const ramMb = ramGb * 1024;
    const machine = accel === "tcg_ivy" ? "pc,hpet=off" : "q35,hpet=off";
    const accelArgs =
      accel === "whpx_host"
        ? "-accel whpx,kernel-irqchip=off -cpu host"
        : accel === "whpx_ivy"
          ? "-accel whpx,kernel-irqchip=off -cpu IvyBridge,+ssse3,+sse4.1,+sse4.2,+popcnt"
          : "-accel tcg,thread=multi -cpu IvyBridge,+ssse3,+sse4.1,+sse4.2,+popcnt";
    const gpuArgs =
      gpu === "angle"
        ? "-device virtio-vga-gl,xres=1280,yres=720 -display sdl,gl=es"
        : gpu === "virtio_sw"
          ? "-device virtio-vga,xres=1280,yres=720 -display sdl,gl=off"
          : "-vga std -display sdl,gl=off";

    return [
      "bin/qemu-system-x86_64.exe",
      "-name Portable-Android13-Win11 -no-reboot",
      `-machine ${machine} -smp ${cores},cores=${cores},threads=1,sockets=1 -m ${ramMb}`,
      accelArgs,
      gpuArgs,
      "-device virtio-balloon-pci -usb -device usb-tablet -device usb-kbd",
      "-netdev user,id=net0,hostfwd=tcp::5555-:5555 -device virtio-net-pci,netdev=net0",
      "-drive file=images/system.img,if=virtio,format=qcow2,cache=writeback,readonly=on",
      "-drive file=images/vendor.img,if=virtio,format=qcow2,cache=writeback,readonly=on",
      "-drive file=images/data.img,if=virtio,format=qcow2,cache=writeback",
      `-kernel ${kernel} -initrd ${initrd}`,
      `-append "root=/dev/ram0 androidboot.hardware=android_x86_64 androidboot.selinux=permissive androidboot.init_fatal_panic=true DATA=/dev/vdc androidboot.console=ttyS0 printk.devkmsg=on printk.always_kmsg_dump=1 nokaslr panic=0 earlycon=uart8250,io,0x3f8,115200 console=tty0 console=ttyS0,115200 SERIAL=ttyS0 loglevel=7"`,
      "-serial stdio",
    ].join(" \\\n  ");
  }, [ksuEnabled, accel, gpu, cores, ramGb]);

  const activeProfile = DEVICE_PROFILES[selectedDevice];

  const pifJson = useMemo(() => {
    return JSON.stringify(
      {
        MANUFACTURER: activeProfile.manufacturer,
        MODEL: activeProfile.model,
        BRAND: activeProfile.brand,
        PRODUCT: activeProfile.product,
        DEVICE: activeProfile.device,
        FINGERPRINT: activeProfile.fingerprint,
        SECURITY_PATCH: activeProfile.security_patch,
        FIRST_API_LEVEL: activeProfile.first_api_level,
        ID: activeProfile.build_id,
        INCREMENTAL: activeProfile.incremental,
        TYPE: "user",
        TAGS: "release-keys",
      },
      null,
      2
    );
  }, [activeProfile]);

  const handleCopy = async (value: string) => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      // Clipboard unavailable in restricted context
    }
  };

  return (
    <div className="app-shell">
      <header className="header">
        <div>
          <h1>{t.title}</h1>
          <p>{t.sub}</p>
        </div>
        <button
          type="button"
          className="btn btn-accent"
          onClick={() => setLang((prev) => (prev === "vi" ? "en" : "vi"))}
        >
          <Languages size={16} />
          {lang === "vi" ? "Ngôn ngữ: VI / EN" : "Language: EN / VI"}
        </button>
      </header>

      <nav className="tabs">
        <button
          type="button"
          className={`tab-btn ${tab === "diagnostics" ? "active" : ""}`}
          onClick={() => setTab("diagnostics")}
        >
          <Wrench size={16} />
          {t.tabDiag}
        </button>
        <button
          type="button"
          className={`tab-btn ${tab === "qemu" ? "active" : ""}`}
          onClick={() => setTab("qemu")}
        >
          <Cpu size={16} />
          {t.tabQemu}
        </button>
        <button
          type="button"
          className={`tab-btn ${tab === "spoof" ? "active" : ""}`}
          onClick={() => setTab("spoof")}
        >
          <Smartphone size={16} />
          {t.tabSpoof}
        </button>
      </nav>

      {tab === "diagnostics" && (
        <div className="grid-2">
          <section className="card">
            <h2>
              <CheckCircle2 size={18} color="#16a34a" />
              {t.fixesTitle}
            </h2>

            <div className="fix-item">
              <div className="fix-title">
                1. Non-blocking UART &amp; /dev/kmsg Streamer (droidport_init_wrapper.c)
              </div>
              <p className="fix-desc">
                {lang === "vi"
                  ? "Bỏ O_SYNC và tcdrain() trên /dev/ttyS0 (nguyên nhân treo PID 1 dưới WHPX/QEMU 16550A), chuyển sang O_NONBLOCK + fallback STDERR_FILENO, seek /dev/kmsg trước khi fork và xử lý EPIPE."
                  : "Removed blocking O_SYNC and tcdrain() on /dev/ttyS0, switched to O_NONBLOCK with STDERR_FILENO fallback, fixed /dev/vd* by-name symlinks, and handled EPIPE in kmsg streaming."}
              </p>
              <div className="fix-file">scripts/patch_system_img.sh</div>
            </div>

            <div className="fix-item">
              <div className="fix-title">
                2. Linux 6.1 fstab &amp; SELinux CIL Conflict Healer
              </div>
              <p className="fix-desc">
                {lang === "vi"
                  ? "Xóa tùy chọn ext4 nomblk_io_submit (lỗi EINVAL trên Linux 6.1), đổi errors=panic sang errors=remount-ro, tự vá các dòng xung đột trùng lặp trong vendor CIL qua secilc thay vì xóa trắng vendor_sepolicy.cil, và bỏ mount /proc|/sys trùng trong C wrapper."
                  : "Removed deprecated nomblk_io_submit mount flag, switched errors=panic to errors=remount-ro, healed conflicting vendor CIL lines iteratively via secilc while keeping vendor types intact, and dropped redundant /proc|/sys pre-mounts."}
              </p>
              <div className="fix-file">scripts/patch_system_img.sh</div>
            </div>

            <div className="fix-item warn">
              <div className="fix-title">
                3. Windows CMD QuickEdit Freeze (&quot;Select ...&quot;) Fix
              </div>
              <p className="fix-desc">
                {lang === "vi"
                  ? "Tự động tắt ENABLE_QUICK_EDIT_MODE qua SetConsoleMode khi mở AndroidLauncher.exe để click vào CMD không làm đóng băng console_log, đồng thời lưu song song ra last_boot.log."
                  : "Disabled Windows Console QuickEdit Mode at startup via SetConsoleMode so clicking the CMD window never freezes stdout threads, and mirrored logs to last_boot.log."}
              </p>
              <div className="fix-file">src/launcher.py</div>
            </div>

            <div className="fix-item">
              <div className="fix-title">
                4. Post-switch_root Watchdog, VirtIO-SW Fallback &amp; Profile Sync
              </div>
              <p className="fix-desc">
                {lang === "vi"
                  ? "Theo dõi switch_root_seen → init_wrapper_seen (25s) và last_serial_ts trước khi có ADB, tự lùi GPU theo chuỗi virtio-vga-gl → virtio-gpu-gl-pci → virtio-vga (gl=off) → -vga std, sửa race condition _adb_logcat_worker và bảo vệ chuyển Profile khỏi ghi đè data.img."
                  : "Added post-switch_root watchdog stages, 4-tier GPU step-down (virtio-vga-gl → virtio-gpu-gl-pci → virtio-vga SW → -vga std), fixed _adb_logcat_worker race, and prevented cross-profile data.img overwrites."}
              </p>
              <div className="fix-file">src/launcher.py</div>
            </div>
          </section>

          <section className="card">
            <h2>
              <Activity size={18} color="#38bdf8" />
              {t.captureTitle}
            </h2>
            <img
              src="/assets/aistudio/image-10_fae92756.webp"
              alt="AndroidLauncher CMD output stuck at exec switch_root"
              className="screenshot-img"
            />
            <p className="fix-desc">
              {lang === "vi"
                ? "Cửa sổ gốc dừng ngay sau [INITRD] Executing: exec switch_root /android /sbin/droidport_init_wrapper với tiêu đề 'Select ...' và không có dòng [INIT-WRAPPER] nào."
                : "Original capture stopped immediately after switch_root with the console title in 'Select ...' QuickEdit state and zero [INIT-WRAPPER] serial output."}
            </p>
          </section>
        </div>
      )}

      {tab === "qemu" && (
        <div className="grid-2">
          <section className="card">
            <h2>
              <Terminal size={18} color="#38bdf8" />
              {t.qemuTitle}
            </h2>

            <div className="field-row">
              <span>KernelSU Next Root</span>
              <input
                type="checkbox"
                checked={ksuEnabled}
                onChange={(e) => setKsuEnabled(e.target.checked)}
              />
            </div>

            <div className="field-row">
              <span>Accelerator Tier</span>
              <select
                value={accel}
                onChange={(e) => setAccel(e.target.value as typeof accel)}
              >
                <option value="whpx_host">WHPX (-cpu host)</option>
                <option value="whpx_ivy">WHPX (-cpu IvyBridge)</option>
                <option value="tcg_ivy">TCG Safe (-cpu IvyBridge)</option>
              </select>
            </div>

            <div className="field-row">
              <span>Graphics (Intel HD 4000)</span>
              <select
                value={gpu}
                onChange={(e) => setGpu(e.target.value as typeof gpu)}
              >
                <option value="angle">ANGLE DX11 (virtio-vga-gl)</option>
                <option value="virtio_sw">VirtIO Software (virtio-vga, gl=off)</option>
                <option value="software">Standard VGA (-vga std)</option>
              </select>
            </div>

            <div className="field-row">
              <span>CPU Cores: {cores}</span>
              <input
                type="range"
                min={1}
                max={4}
                value={cores}
                onChange={(e) => setCores(Number(e.target.value))}
              />
            </div>

            <div className="field-row">
              <span>RAM: {ramGb} GB</span>
              <input
                type="range"
                min={2}
                max={6}
                value={ramGb}
                onChange={(e) => setRamGb(Number(e.target.value))}
              />
            </div>

            <button
              type="button"
              className="btn btn-primary"
              onClick={() => handleCopy(qemuCmd)}
            >
              <Copy size={15} />
              {copied ? t.copied : t.copyCmd}
            </button>
          </section>

          <section className="card">
            <h2>
              <Terminal size={18} color="#16a34a" />
              Generated Launch Command
            </h2>
            <pre className="code-box">{qemuCmd}</pre>
          </section>
        </div>
      )}

      {tab === "spoof" && (
        <div className="grid-2">
          <section className="card">
            <h2>
              <ShieldCheck size={18} color="#38bdf8" />
              Device Spoof Profile
            </h2>
            <div className="field-row">
              <span>Target Device</span>
              <select
                value={selectedDevice}
                onChange={(e) => setSelectedDevice(e.target.value)}
              >
                {Object.keys(DEVICE_PROFILES).map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </select>
            </div>
            <pre className="code-box">{JSON.stringify(activeProfile, null, 2)}</pre>
          </section>

          <section className="card">
            <h2>
              <ShieldCheck size={18} color="#16a34a" />
              PlayIntegrityFix Payload (pif.json)
            </h2>
            <pre className="code-box">{pifJson}</pre>
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => handleCopy(pifJson)}
            >
              <Copy size={15} />
              {copied ? t.copied : "Copy pif.json"}
            </button>
          </section>
        </div>
      )}
    </div>
  );
}
