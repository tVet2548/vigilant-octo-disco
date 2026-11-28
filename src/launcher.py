#!/usr/bin/env python3
"""
AndroidLauncher.exe - Waydroid-Style Portable Android 13 Launcher for Windows 11
Optimized for Intel Core i5-3475S (Ivy Bridge) & Intel HD Graphics 4000 (ANGLE DX11 / OpenGL 4.0).
Features:
  - Always opens attached Windows CMD console streaming QEMU, dmesg, and adb logcat
  - Bilingual Vietnamese / English (VI / EN) plain-language UI
  - Dual (Kernel + Initrd) hot-switch: Clean Stock vs KernelSU Next + x86_64 ksud
  - Waydroid Multi-Window App Launcher (scrcpy --new-display --start-app) + Desktop .ico/.lnk creator
  - Smart Explorer Drag-and-Drop (.apk / .zip / media) & 2-Way Clipboard Sync
  - Multi-Profile data.img Manager (Clone / Switch / +10GB Expand)
  - 1-Click Keybox & Safety Audit + Boot-Loop Safe Mode Rescue
"""
from __future__ import annotations

import ctypes
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import webbrowser
import zipfile
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Dict, List, Optional

import customtkinter as ctk
from PIL import Image

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    HAS_DND = True
except Exception:
    HAS_DND = False
    DND_FILES = None
    TkinterDnD = None

# Resolve portable paths cleanly regardless of drive letter or PyInstaller frozen bundle
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
    BUNDLE_DATA_DIR = Path(getattr(sys, "_MEIPASS", BASE_DIR))
    if str(BUNDLE_DATA_DIR) not in sys.path:
        sys.path.insert(0, str(BUNDLE_DATA_DIR))
else:
    BASE_DIR = Path(__file__).resolve().parent.parent
    SRC_DIR = Path(__file__).resolve().parent
    if str(SRC_DIR) not in sys.path:
        sys.path.insert(0, str(SRC_DIR))

import spoof_device  # noqa: E402


TEXTS: Dict[str, Dict[str, str]] = {
    "vi": {
        "win_title": "Android 13 Portable · Chạy Mượt Trên Windows 11",
        "header_title": "Android 13 Portable (LineageOS 20 GApps · Intel HD 4000)",
        "header_sub": "Tối ưu cho chip Intel i5-3475S (Ivy Bridge) · Dual Initrd & Native SELinux Enforcing",
        "lang_btn": "Ngôn ngữ: VI / EN",
        "tab_main": "Điều Khiển Chính",
        "tab_apps": "Mở App Riêng Lẻ",
        "tab_tools": "Kéo-Thả & Cứu Hộ",
        "kernel_label": "Chế độ hệ thống (Root / An toàn):",
        "kernel_on": "BẬT Root (KernelSU Next — Cài module & giả lập máy)",
        "kernel_off": "TẮT Root (Máy sạch hoàn toàn — Chơi game/Ngân hàng)",
        "selinux_label": "Mức bảo mật (SELinux):",
        "selinux_enf": "Enforcing (Chặt chẽ — Game/Bank)",
        "selinux_perm": "Permissive (Mở rộng — Vọc sâu)",
        "profile_label": "Hồ sơ bộ nhớ (Lưu app & dữ liệu):",
        "profile_switch": "Đổi Hồ Sơ",
        "profile_clone": "Nhân Bản (+)",
        "profile_expand": "Mở Rộng Bộ Nhớ (+10GB)",
        "spoof_label": "Biến hình thành điện thoại thật:",
        "accel_label": "Chế độ tăng tốc (WHPX / TCG):",
        "gpu_label": "Chế độ đồ họa (Intel HD 4000):",
        "gpu_angle": "VirtIO-SW llvmpipe (An toàn HD 4000)",
        "gpu_soft": "Experimental VirGL (3D GLES/OpenGL)",
        "cpu_label": "Số nhân CPU sử dụng (i5-3475S):",
        "ram_label": "Dung lượng RAM cấp cho máy ảo:",
        "btn_start": "Bật Máy Ảo Android",
        "btn_stop": "Tắt Máy Ảo",
        "btn_install_ksu": "Cài Công Cụ Root & Ẩn Root",
        "btn_spoof": "Biến Hình Điện Thoại Ngay",
        "btn_adb": "Mở Cửa Sổ Lệnh ADB",
        "btn_reset": "Xóa Dữ Liệu Làm Mới",
        "apps_hint": "Chế độ Waydroid: Mở từng app Android thành cửa sổ Windows riêng hoặc ghim ra màn hình chính.",
        "btn_refresh_apps": "Tải Danh Sách App",
        "search_apps": "Tìm tên gói app (ví dụ: youtube, facebook, zing...)",
        "btn_launch_app": "Mở App Thành Cửa Sổ Riêng",
        "btn_shortcut": "Tạo Lối Tắt Ngoài Desktop",
        "dnd_title": "Kéo & Thả File Thẳng Vào Đây (Hoặc Bấm Để Chọn File)",
        "dnd_sub": "Hỗ trợ: .APK (tự cài app) · .ZIP (nạp module KernelSU) · Ảnh / Video (chép vào Android)",
        "btn_pick_file": "Chọn File Từ Máy Tính...",
        "clip_title": "Đồng Bộ Copy-Paste 2 Chiều (Windows <-> Android)",
        "btn_clip_win_to_and": "Gửi Clipboard Windows -> Android",
        "btn_clip_and_to_win": "Lấy Clipboard Android -> Windows",
        "clip_auto": "Tự động đồng bộ mỗi 3 giây (khi VM đang chạy)",
        "safety_title": "Bơm Keybox & Kiểm Tra An Toàn / Cứu Hộ Treo Logo",
        "btn_keybox": "Bơm Keybox & Kiểm Tra An Toàn 1-Click",
        "btn_safemode": "Cứu Hộ Treo Logo (Safe Mode)",
        "quick_hub_title": "Tiện Ích Nhanh 1-Click (Quick Action Hub):",
        "btn_gsf_id": "Lấy mã GSF Whitelist",
        "btn_rand_id": "Đổi Danh Tính Mới",
        "btn_snap_save": "Lưu Điểm Khôi Phục (Snapshot)",
        "btn_snap_load": "Quay Lại Điểm Lưu",
        "btn_wifi_on": "Chuyển Mạng: Wi-Fi (wlan0)",
        "btn_wifi_off": "Chuyển Mạng: LAN (eth0)",
        "btn_trim_ram": "Dọn RAM Máy Ảo",
        "status_idle": "Đang nghỉ · Sẵn sàng khởi động",
    },
    "en": {
        "win_title": "Portable Android 13 · Windows 11 Launcher",
        "header_title": "Portable Android 13 (LineageOS 20 GApps · Intel HD 4000)",
        "header_sub": "Tuned for Intel i5-3475S (Ivy Bridge) · Dual Initrd & Native SELinux Enforcing",
        "lang_btn": "Language: EN / VI",
        "tab_main": "Main Control",
        "tab_apps": "Multi-Window Apps",
        "tab_tools": "Drop & Rescue",
        "kernel_label": "System Mode (Root / Clean):",
        "kernel_on": "Root ON (KernelSU Next — Modules & Spoofing)",
        "kernel_off": "Clean Stock (No Root — Strict Games & Banking)",
        "selinux_label": "Security Level (SELinux):",
        "selinux_enf": "Enforcing (Strict — Games/Banking)",
        "selinux_perm": "Permissive (Relaxed — Modding)",
        "profile_label": "Storage Profile (Saves apps & data):",
        "profile_switch": "Switch Profile",
        "profile_clone": "Clone (+)",
        "profile_expand": "Expand Storage (+10GB)",
        "spoof_label": "Disguise as Real Phone:",
        "accel_label": "CPU Acceleration (WHPX / TCG):",
        "gpu_label": "Graphics Mode (Intel HD 4000):",
        "gpu_angle": "VirtIO-SW llvmpipe (HD 4000 Safe)",
        "gpu_soft": "Experimental VirGL (3D GLES/OpenGL)",
        "cpu_label": "CPU Cores (Intel i5-3475S):",
        "ram_label": "System RAM Allocation:",
        "btn_start": "Start Android VM",
        "btn_stop": "Stop VM",
        "btn_install_ksu": "Install Root & Hiding Tools",
        "btn_spoof": "Apply Phone Disguise Now",
        "btn_adb": "Open ADB Command Window",
        "btn_reset": "Reset Data (Fresh Wipe)",
        "apps_hint": "Waydroid Mode: Launch any Android app in its own Windows window or pin a Desktop shortcut.",
        "btn_refresh_apps": "Refresh Installed Apps",
        "search_apps": "Filter package name (e.g. youtube, settings, chrome...)",
        "btn_launch_app": "Open App in New Window",
        "btn_shortcut": "Create Desktop Shortcut",
        "dnd_title": "Drag & Drop Any File Here (Or Click to Browse)",
        "dnd_sub": "Supports: .APK (auto install) · .ZIP (flash KSU module) · Photos/Videos (copy to Downloads)",
        "btn_pick_file": "Choose File From PC...",
        "clip_title": "2-Way Clipboard Sync (Windows <-> Android)",
        "btn_clip_win_to_and": "Send PC Clipboard -> Android",
        "btn_clip_and_to_win": "Pull Android Clipboard -> PC",
        "clip_auto": "Auto-sync clipboard every 3s while VM runs",
        "safety_title": "1-Click Keybox Safety Audit & Boot-Loop Rescue",
        "btn_keybox": "Inject Keybox & 1-Click Safety Check",
        "btn_safemode": "Boot-Loop Rescue (Safe Mode)",
        "quick_hub_title": "Quick Action Hub (1-Click Utilities):",
        "btn_gsf_id": "Get GSF Whitelist ID",
        "btn_rand_id": "Randomize Identity",
        "btn_snap_save": "Save Snapshot",
        "btn_snap_load": "Restore Snapshot",
        "btn_wifi_on": "Network: Wi-Fi (wlan0)",
        "btn_wifi_off": "Network: Wired LAN (eth0)",
        "btn_trim_ram": "Trim VM RAM",
        "status_idle": "Idle · Ready to start",
    },
}

DEFAULT_PROFILES = ["Clean_Gaming", "Root_Modding"]


_LOG_LOCK = threading.Lock()
_BOOT_LOG_PATH = BASE_DIR / "last_boot.log"


def _disable_windows_console_quick_edit() -> None:
    """Prevent accidental CMD clicks ('Select ...' QuickEdit Mode) from freezing stdout across threads."""
    if sys.platform != "win32":
        return
    try:
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        std_input_handle = -10
        h_in = kernel32.GetStdHandle(std_input_handle)
        if not h_in or h_in == -1:
            return
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(h_in, ctypes.byref(mode)):
            enable_quick_edit = 0x0040
            enable_extended_flags = 0x0080
            new_mode = (mode.value & ~enable_quick_edit) | enable_extended_flags
            kernel32.SetConsoleMode(h_in, new_mode)
    except Exception:
        pass


def console_log(msg: str) -> None:
    ts = time.strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    with _LOG_LOCK:
        try:
            print(line, flush=True)
        except Exception:
            pass
        try:
            with _BOOT_LOG_PATH.open("a", encoding="utf-8", errors="replace") as lf:
                lf.write(line + "\n")
        except Exception:
            pass


def _no_window_flags() -> int:
    if sys.platform == "win32":
        return getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return 0


# Mix TkinterDnD when available so native Windows Explorer Drag & Drop works on CTk
if HAS_DND and TkinterDnD is not None:
    class BaseCTk(ctk.CTk, TkinterDnD.DnDWrapper):  # type: ignore[misc]
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.TkdndVersion = TkinterDnD._require(self)
else:
    class BaseCTk(ctk.CTk):
        pass


class PortableAndroidLauncher(BaseCTk):
    def __init__(self) -> None:
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.bin_dir = BASE_DIR / "bin"
        self.scrcpy_exe = self.bin_dir / "scrcpy" / "scrcpy.exe"
        self.qemu_exe = self.bin_dir / "qemu-system-x86_64.exe"
        self.qemu_img_exe = self.bin_dir / "qemu-img.exe"
        self.adb_exe = self.bin_dir / "adb.exe"
        self.images_dir = BASE_DIR / "images"
        self.profiles_dir = self.images_dir / "profiles"
        self.modules_dir = BASE_DIR / "modules"
        self.assets_dir = BASE_DIR / "assets"
        self.config_path = BASE_DIR / "launcher_config.json"

        self.profiles_dir.mkdir(parents=True, exist_ok=True)
        self.assets_dir.mkdir(parents=True, exist_ok=True)

        self.vm_process: Optional[subprocess.Popen] = None
        self.logcat_process: Optional[subprocess.Popen] = None
        self.stop_log_threads = threading.Event()
        self.adb_connected = False
        self.active_kernel_name = "kernel_ksunext"
        self.installed_packages: List[str] = []
        self.selected_package = ctk.StringVar(value="")
        self.last_win_clip = ""
        self.last_and_clip = ""

        cfg = self._load_config()
        self.lang: str = cfg.get("lang", "vi")
        self.ksu_enabled = ctk.BooleanVar(value=bool(cfg.get("ksu_enabled", True)))
        self.selinux_mode = ctk.StringVar(value=cfg.get("selinux_mode", "enforcing"))
        self.cpu_cores = ctk.IntVar(value=int(cfg.get("cpu_cores", 3)))
        self.ram_gb = ctk.IntVar(value=int(cfg.get("ram_gb", 4)))
        self.selected_device = ctk.StringVar(value=cfg.get("device", "Google Pixel 8 Pro"))
        self.accel_mode = ctk.StringVar(value=cfg.get("accel_mode", "auto"))
        raw_gpu = cfg.get("gpu", "software")
        if raw_gpu == "angle":
            raw_gpu = "software"
        self.gpu_choice = ctk.StringVar(value=raw_gpu if raw_gpu in ("software", "virgl") else "software")
        self.active_profile = ctk.StringVar(value=cfg.get("profile", "Root_Modding"))
        self.loaded_profile: str = ""
        self.auto_clip_var = ctk.BooleanVar(value=bool(cfg.get("auto_clip", True)))
        self.wifi_sim_enabled = ctk.BooleanVar(value=bool(cfg.get("wifi_sim_enabled", True)))
        self.app_filter_var = ctk.StringVar(value="")
        self.status_text = ctk.StringVar(value=self.t("status_idle"))

        self._init_storage_profiles()

        self.geometry("790x815")
        self.minsize(750, 740)
        self._build_ui()
        self._apply_language()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        console_log("==================================================================")
        console_log(" Portable Android 13 Launcher (Intel i5-3475S / HD Graphics 4000) ")
        console_log(f" Portable Root Dir : {BASE_DIR}")
        console_log(f" Native Drag & Drop: {'ENABLED' if HAS_DND else 'Fallback File Picker'}")
        console_log(" Live CMD console attached for QEMU, Kernel dmesg & ADB logcat.")
        console_log("==================================================================")

        # Start gentle clipboard polling loop
        self.after(3000, self._clipboard_poll_tick)

    def t(self, key: str) -> str:
        return TEXTS.get(self.lang, TEXTS["vi"]).get(key, key)

    def _load_config(self) -> dict:
        if self.config_path.exists():
            try:
                return json.loads(self.config_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def _save_config(self) -> None:
        data = {
            "lang": self.lang,
            "ksu_enabled": self.ksu_enabled.get(),
            "selinux_mode": self.selinux_mode.get(),
            "cpu_cores": self.cpu_cores.get(),
            "ram_gb": self.ram_gb.get(),
            "device": self.selected_device.get(),
            "accel_mode": self.accel_mode.get(),
            "gpu": self.gpu_choice.get(),
            "profile": self.active_profile.get(),
            "auto_clip": self.auto_clip_var.get(),
            "wifi_sim_enabled": self.wifi_sim_enabled.get(),
        }
        try:
            self.config_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _init_storage_profiles(self) -> None:
        """Keep multi-profile qcow2 disks synced with pre-formatted images/data.img."""
        data_img = self.images_dir / "data.img"
        clean_tpl = self.images_dir / "data_clean.qcow2"
        if not data_img.exists() and clean_tpl.exists():
            shutil.copy2(clean_tpl, data_img)
        existing = sorted([p.stem for p in self.profiles_dir.glob("*.qcow2")])
        if not existing and data_img.exists():
            for preset in DEFAULT_PROFILES:
                target = self.profiles_dir / f"{preset}.qcow2"
                shutil.copy2(data_img, target)
            existing = DEFAULT_PROFILES.copy()
        if existing and self.active_profile.get() not in existing:
            self.active_profile.set(existing[0])
        self.loaded_profile = self.active_profile.get()

    def _list_profiles(self) -> List[str]:
        found = sorted([p.stem for p in self.profiles_dir.glob("*.qcow2")])
        return found if found else DEFAULT_PROFILES

    def _build_ui(self) -> None:
        self.configure(fg_color="#0F172A")

        # Top Header Bar with VI / EN Toggle
        header = ctk.CTkFrame(self, fg_color="#1E293B", corner_radius=10, border_width=1, border_color="#334155")
        header.pack(fill="x", padx=18, pady=(14, 10))

        title_col = ctk.CTkFrame(header, fg_color="transparent")
        title_col.pack(side="left", fill="x", expand=True, padx=14, pady=10)

        self.lbl_header_title = ctk.CTkLabel(
            title_col,
            text="",
            font=ctk.CTkFont(family="Segoe UI", size=17, weight="bold"),
            text_color="#F8FAFC",
            anchor="w",
        )
        self.lbl_header_title.pack(anchor="w")

        self.lbl_header_sub = ctk.CTkLabel(
            title_col,
            text="",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="#94A3B8",
            anchor="w",
        )
        self.lbl_header_sub.pack(anchor="w")

        self.btn_lang = ctk.CTkButton(
            header,
            text="",
            width=130,
            height=32,
            fg_color="#0F172A",
            hover_color="#334155",
            border_width=1,
            border_color="#38BDF8",
            text_color="#38BDF8",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self.toggle_language,
        )
        self.btn_lang.pack(side="right", padx=14)

        # Tabview
        self.tabs = ctk.CTkTabview(
            self,
            fg_color="#1E293B",
            segmented_button_fg_color="#0F172A",
            segmented_button_selected_color="#2563EB",
            segmented_button_selected_hover_color="#1D4ED8",
            border_width=1,
            border_color="#334155",
        )
        self.tabs.pack(fill="both", expand=True, padx=18, pady=(0, 8))

        self.tab_main_frame = self.tabs.add("Main")
        self.tab_apps_frame = self.tabs.add("Apps")
        self.tab_tools_frame = self.tabs.add("Tools")

        self._build_tab_main(self.tab_main_frame)
        self._build_tab_apps(self.tab_apps_frame)
        self._build_tab_tools(self.tab_tools_frame)

        # Bottom Status Bar
        status_frame = ctk.CTkFrame(self, fg_color="#0B1120", corner_radius=8, border_width=1, border_color="#334155")
        status_frame.pack(fill="x", padx=18, pady=(0, 12))

        ctk.CTkLabel(
            status_frame,
            textvariable=self.status_text,
            font=ctk.CTkFont(family="Consolas", size=12),
            text_color="#38BDF8",
        ).pack(anchor="w", padx=12, pady=7)

    def _build_tab_main(self, parent: ctk.CTkFrame) -> None:
        # Kernel Mode Row
        r_ksu = ctk.CTkFrame(parent, fg_color="transparent")
        r_ksu.pack(fill="x", padx=12, pady=(10, 6))
        self.lbl_kernel = ctk.CTkLabel(r_ksu, text="", font=ctk.CTkFont(size=13, weight="bold"))
        self.lbl_kernel.pack(side="left")
        self.ksu_switch = ctk.CTkSwitch(
            r_ksu,
            text="",
            variable=self.ksu_enabled,
            command=self._on_ksu_toggle,
            progress_color="#2563EB",
            font=ctk.CTkFont(size=12),
        )
        self.ksu_switch.pack(side="right")

        # SELinux Mode Row
        r_sel = ctk.CTkFrame(parent, fg_color="transparent")
        r_sel.pack(fill="x", padx=12, pady=4)
        self.lbl_selinux = ctk.CTkLabel(r_sel, text="", font=ctk.CTkFont(size=13, weight="bold"))
        self.lbl_selinux.pack(side="left")
        self.selinux_seg = ctk.CTkSegmentedButton(
            r_sel,
            values=["Enforcing", "Permissive"],
            command=self._on_selinux_change,
            selected_color="#16A34A",
            selected_hover_color="#15803D",
            fg_color="#0F172A",
        )
        self.selinux_seg.set("Enforcing" if self.selinux_mode.get() == "enforcing" else "Permissive")
        self.selinux_seg.pack(side="right")

        # Storage Profile Manager Row
        r_prof = ctk.CTkFrame(parent, fg_color="transparent")
        r_prof.pack(fill="x", padx=12, pady=6)
        self.lbl_profile = ctk.CTkLabel(r_prof, text="", font=ctk.CTkFont(size=13, weight="bold"))
        self.lbl_profile.pack(side="left")

        prof_controls = ctk.CTkFrame(r_prof, fg_color="transparent")
        prof_controls.pack(side="right")
        self.profile_menu = ctk.CTkOptionMenu(
            prof_controls,
            values=self._list_profiles(),
            variable=self.active_profile,
            width=155,
            fg_color="#0F172A",
            button_color="#334155",
            command=self._on_profile_select,
        )
        self.profile_menu.pack(side="left", padx=(0, 6))
        self.btn_prof_switch = ctk.CTkButton(
            prof_controls, text="", width=95, height=28, fg_color="#2563EB", command=self.switch_profile
        )
        self.btn_prof_switch.pack(side="left", padx=(0, 6))
        self.btn_prof_clone = ctk.CTkButton(
            prof_controls, text="", width=95, height=28, fg_color="#334155", command=self.clone_profile
        )
        self.btn_prof_clone.pack(side="left", padx=(0, 6))
        self.btn_prof_expand = ctk.CTkButton(
            prof_controls, text="", width=140, height=28, fg_color="#0284C7", command=self.expand_storage_10gb
        )
        self.btn_prof_expand.pack(side="left")

        # Spoof Profile Row
        r_spoof = ctk.CTkFrame(parent, fg_color="transparent")
        r_spoof.pack(fill="x", padx=12, pady=6)
        self.lbl_spoof = ctk.CTkLabel(r_spoof, text="", font=ctk.CTkFont(size=13, weight="bold"))
        self.lbl_spoof.pack(side="left")
        self.device_menu = ctk.CTkOptionMenu(
            r_spoof,
            values=list(spoof_device.DEVICE_PROFILES.keys()),
            variable=self.selected_device,
            width=290,
            fg_color="#0F172A",
            button_color="#2563EB",
            command=lambda _: self._save_config(),
        )
        self.device_menu.pack(side="right")

        # Accelerator Mode Row
        r_acc = ctk.CTkFrame(parent, fg_color="transparent")
        r_acc.pack(fill="x", padx=12, pady=6)
        self.lbl_accel = ctk.CTkLabel(r_acc, text="", font=ctk.CTkFont(size=13, weight="bold"))
        self.lbl_accel.pack(side="left")
        self.accel_seg = ctk.CTkSegmentedButton(
            r_acc,
            values=["Auto (WHPX -> TCG)", "WHPX", "TCG (Safe)"],
            command=self._on_accel_change,
            selected_color="#2563EB",
            fg_color="#0F172A",
        )
        _acc_map = {"auto": "Auto (WHPX -> TCG)", "whpx": "WHPX", "tcg": "TCG (Safe)"}
        self.accel_seg.set(_acc_map.get(self.accel_mode.get(), "Auto (WHPX -> TCG)"))
        self.accel_seg.pack(side="right")

        # Graphics Mode Row
        r_gpu = ctk.CTkFrame(parent, fg_color="transparent")
        r_gpu.pack(fill="x", padx=12, pady=6)
        self.lbl_gpu = ctk.CTkLabel(r_gpu, text="", font=ctk.CTkFont(size=13, weight="bold"))
        self.lbl_gpu.pack(side="left")
        self.gpu_seg = ctk.CTkSegmentedButton(
            r_gpu,
            values=["VirtIO-SW (HD 4000 Safe)", "Experimental VirGL"],
            command=self._on_gpu_change,
            selected_color="#2563EB",
            fg_color="#0F172A",
        )
        self.gpu_seg.set("Experimental VirGL" if self.gpu_choice.get() == "virgl" else "VirtIO-SW (HD 4000 Safe)")
        self.gpu_seg.pack(side="right")

        # CPU Slider
        r_cpu = ctk.CTkFrame(parent, fg_color="transparent")
        r_cpu.pack(fill="x", padx=12, pady=(8, 4))
        self.lbl_cpu = ctk.CTkLabel(r_cpu, text="", font=ctk.CTkFont(size=13))
        self.lbl_cpu.pack(side="left")
        self.cpu_slider = ctk.CTkSlider(
            r_cpu, from_=1, to=4, number_of_steps=3, variable=self.cpu_cores, width=290,
            command=lambda _: self._update_slider_labels(), progress_color="#2563EB"
        )
        self.cpu_slider.pack(side="right")

        # RAM Slider
        r_ram = ctk.CTkFrame(parent, fg_color="transparent")
        r_ram.pack(fill="x", padx=12, pady=(4, 10))
        self.lbl_ram = ctk.CTkLabel(r_ram, text="", font=ctk.CTkFont(size=13))
        self.lbl_ram.pack(side="left")
        self.ram_slider = ctk.CTkSlider(
            r_ram, from_=2, to=6, number_of_steps=4, variable=self.ram_gb, width=290,
            command=lambda _: self._update_slider_labels(), progress_color="#2563EB"
        )
        self.ram_slider.pack(side="right")

        # Action Grid
        actions = ctk.CTkFrame(parent, fg_color="#0F172A", corner_radius=8, border_width=1, border_color="#334155")
        actions.pack(fill="x", padx=12, pady=(4, 8))
        actions.grid_columnconfigure((0, 1), weight=1)

        self.btn_start = ctk.CTkButton(
            actions, text="", height=42, fg_color="#16A34A", hover_color="#15803D",
            font=ctk.CTkFont(size=14, weight="bold"), command=self.start_vm
        )
        self.btn_start.grid(row=0, column=0, padx=(10, 5), pady=(10, 6), sticky="ew")

        self.btn_stop = ctk.CTkButton(
            actions, text="", height=42, fg_color="#DC2626", hover_color="#B91C1C",
            font=ctk.CTkFont(size=14, weight="bold"), state="disabled", command=self.stop_vm
        )
        self.btn_stop.grid(row=0, column=1, padx=(5, 10), pady=(10, 6), sticky="ew")

        self.btn_install_ksu = ctk.CTkButton(
            actions, text="", height=36, fg_color="#2563EB", hover_color="#1D4ED8",
            command=self.install_ksu_and_modules
        )
        self.btn_install_ksu.grid(row=1, column=0, padx=(10, 5), pady=5, sticky="ew")

        self.btn_spoof = ctk.CTkButton(
            actions, text="", height=36, fg_color="#0284C7", hover_color="#0369A1",
            command=self.run_apply_spoof
        )
        self.btn_spoof.grid(row=1, column=1, padx=(5, 10), pady=5, sticky="ew")

        self.btn_adb_shell = ctk.CTkButton(
            actions, text="", height=36, fg_color="#334155", hover_color="#475569",
            command=self.open_adb_shell
        )
        self.btn_adb_shell.grid(row=2, column=0, padx=(10, 5), pady=(5, 10), sticky="ew")

        self.btn_reset_data = ctk.CTkButton(
            actions, text="", height=36, fg_color="#475569", hover_color="#B45309",
            command=self.reset_data_img
        )
        self.btn_reset_data.grid(row=2, column=1, padx=(5, 10), pady=(5, 10), sticky="ew")

        # Quick Action Hub (5 1-Click Actions)
        hub = ctk.CTkFrame(parent, fg_color="#0F172A", corner_radius=8, border_width=1, border_color="#334155")
        hub.pack(fill="x", padx=12, pady=(0, 8))
        hub.grid_columnconfigure((0, 1, 2), weight=1)

        self.lbl_quick_hub = ctk.CTkLabel(
            hub, text="", font=ctk.CTkFont(size=12, weight="bold"), text_color="#38BDF8", anchor="w"
        )
        self.lbl_quick_hub.grid(row=0, column=0, columnspan=3, sticky="w", padx=10, pady=(8, 4))

        self.btn_gsf_id = ctk.CTkButton(
            hub, text="", height=32, fg_color="#1E293B", hover_color="#2563EB",
            border_width=1, border_color="#334155", font=ctk.CTkFont(size=11, weight="bold"),
            command=self.quick_fetch_gsf_whitelist
        )
        self.btn_gsf_id.grid(row=1, column=0, padx=(10, 4), pady=4, sticky="ew")

        self.btn_rand_id = ctk.CTkButton(
            hub, text="", height=32, fg_color="#1E293B", hover_color="#0284C7",
            border_width=1, border_color="#334155", font=ctk.CTkFont(size=11, weight="bold"),
            command=self.quick_randomize_identity
        )
        self.btn_rand_id.grid(row=1, column=1, padx=4, pady=4, sticky="ew")

        self.btn_trim_ram = ctk.CTkButton(
            hub, text="", height=32, fg_color="#1E293B", hover_color="#16A34A",
            border_width=1, border_color="#334155", font=ctk.CTkFont(size=11, weight="bold"),
            command=self.quick_trim_ram
        )
        self.btn_trim_ram.grid(row=1, column=2, padx=(4, 10), pady=4, sticky="ew")

        self.btn_snap_save = ctk.CTkButton(
            hub, text="", height=32, fg_color="#1E293B", hover_color="#2563EB",
            border_width=1, border_color="#334155", font=ctk.CTkFont(size=11, weight="bold"),
            command=self.quick_save_snapshot
        )
        self.btn_snap_save.grid(row=2, column=0, padx=(10, 4), pady=(4, 9), sticky="ew")

        self.btn_snap_load = ctk.CTkButton(
            hub, text="", height=32, fg_color="#1E293B", hover_color="#D97706",
            border_width=1, border_color="#334155", font=ctk.CTkFont(size=11, weight="bold"),
            command=self.quick_restore_snapshot
        )
        self.btn_snap_load.grid(row=2, column=1, padx=4, pady=(4, 9), sticky="ew")

        self.btn_wifi_toggle = ctk.CTkButton(
            hub, text="", height=32, fg_color="#1E293B", hover_color="#0284C7",
            border_width=1, border_color="#334155", font=ctk.CTkFont(size=11, weight="bold"),
            command=self.quick_toggle_wifi_lan
        )
        self.btn_wifi_toggle.grid(row=2, column=2, padx=(4, 10), pady=(4, 9), sticky="ew")

    def _build_tab_apps(self, parent: ctk.CTkFrame) -> None:
        self.lbl_apps_hint = ctk.CTkLabel(
            parent, text="", font=ctk.CTkFont(size=12), text_color="#CBD5E1", wraplength=700, justify="left"
        )
        self.lbl_apps_hint.pack(anchor="w", padx=12, pady=(10, 8))

        top_bar = ctk.CTkFrame(parent, fg_color="transparent")
        top_bar.pack(fill="x", padx=12, pady=(0, 8))

        self.entry_app_search = ctk.CTkEntry(
            top_bar, textvariable=self.app_filter_var, placeholder_text=""
        )
        self.entry_app_search.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.entry_app_search.bind("<KeyRelease>", lambda _e: self._render_app_list())

        self.btn_refresh_apps = ctk.CTkButton(
            top_bar, text="", width=170, fg_color="#2563EB", command=self.refresh_installed_apps
        )
        self.btn_refresh_apps.pack(side="right")

        self.apps_scroll = ctk.CTkScrollableFrame(
            parent, height=290, fg_color="#0F172A", border_width=1, border_color="#334155"
        )
        self.apps_scroll.pack(fill="both", expand=True, padx=12, pady=(0, 10))

        bottom_bar = ctk.CTkFrame(parent, fg_color="transparent")
        bottom_bar.pack(fill="x", padx=12, pady=(0, 10))
        bottom_bar.grid_columnconfigure((0, 1), weight=1)

        self.btn_launch_app = ctk.CTkButton(
            bottom_bar, text="", height=40, fg_color="#16A34A", hover_color="#15803D",
            font=ctk.CTkFont(size=13, weight="bold"), command=self.launch_selected_app_window
        )
        self.btn_launch_app.grid(row=0, column=0, padx=(0, 6), sticky="ew")

        self.btn_shortcut = ctk.CTkButton(
            bottom_bar, text="", height=40, fg_color="#0284C7", hover_color="#0369A1",
            font=ctk.CTkFont(size=13, weight="bold"), command=self.create_desktop_shortcut
        )
        self.btn_shortcut.grid(row=0, column=1, padx=(6, 0), sticky="ew")

    def _build_tab_tools(self, parent: ctk.CTkFrame) -> None:
        # Drag & Drop Box
        self.drop_box = ctk.CTkFrame(
            parent, height=130, fg_color="#0F172A", corner_radius=10, border_width=2, border_color="#38BDF8"
        )
        self.drop_box.pack(fill="x", padx=12, pady=(10, 10))
        self.drop_box.pack_propagate(False)

        self.lbl_dnd_title = ctk.CTkLabel(
            self.drop_box, text="", font=ctk.CTkFont(size=14, weight="bold"), text_color="#F8FAFC"
        )
        self.lbl_dnd_title.pack(pady=(16, 4))

        self.lbl_dnd_sub = ctk.CTkLabel(
            self.drop_box, text="", font=ctk.CTkFont(size=11), text_color="#94A3B8"
        )
        self.lbl_dnd_sub.pack(pady=(0, 8))

        self.btn_pick_file = ctk.CTkButton(
            self.drop_box, text="", width=200, height=30, fg_color="#2563EB", command=self.browse_drop_file
        )
        self.btn_pick_file.pack()

        if HAS_DND and DND_FILES is not None:
            try:
                self.drop_target_register(DND_FILES)
                self.dnd_bind("<<Drop>>", self._on_file_drop)
            except Exception as exc:
                console_log(f"[DND] Drop registration note: {exc}")

        # 2-Way Clipboard Sync Box
        clip_box = ctk.CTkFrame(parent, fg_color="#0F172A", corner_radius=8, border_width=1, border_color="#334155")
        clip_box.pack(fill="x", padx=12, pady=(0, 10))

        self.lbl_clip_title = ctk.CTkLabel(
            clip_box, text="", font=ctk.CTkFont(size=13, weight="bold"), text_color="#F8FAFC"
        )
        self.lbl_clip_title.pack(anchor="w", padx=12, pady=(10, 6))

        clip_btns = ctk.CTkFrame(clip_box, fg_color="transparent")
        clip_btns.pack(fill="x", padx=12, pady=(0, 6))
        clip_btns.grid_columnconfigure((0, 1), weight=1)

        self.btn_clip_w2a = ctk.CTkButton(
            clip_btns, text="", height=34, fg_color="#334155", command=self.push_clipboard_to_android
        )
        self.btn_clip_w2a.grid(row=0, column=0, padx=(0, 5), sticky="ew")

        self.btn_clip_a2w = ctk.CTkButton(
            clip_btns, text="", height=34, fg_color="#334155", command=self.pull_clipboard_from_android
        )
        self.btn_clip_a2w.grid(row=0, column=1, padx=(5, 0), sticky="ew")

        self.chk_auto_clip = ctk.CTkCheckBox(
            clip_box, text="", variable=self.auto_clip_var, command=self._save_config, font=ctk.CTkFont(size=12)
        )
        self.chk_auto_clip.pack(anchor="w", padx=12, pady=(2, 10))

        # Safety & Boot-Loop Rescue Box
        safe_box = ctk.CTkFrame(parent, fg_color="#0F172A", corner_radius=8, border_width=1, border_color="#334155")
        safe_box.pack(fill="x", padx=12, pady=(0, 10))

        self.lbl_safety_title = ctk.CTkLabel(
            safe_box, text="", font=ctk.CTkFont(size=13, weight="bold"), text_color="#F8FAFC"
        )
        self.lbl_safety_title.pack(anchor="w", padx=12, pady=(10, 8))

        safe_btns = ctk.CTkFrame(safe_box, fg_color="transparent")
        safe_btns.pack(fill="x", padx=12, pady=(0, 12))
        safe_btns.grid_columnconfigure((0, 1), weight=1)

        self.btn_keybox = ctk.CTkButton(
            safe_btns, text="", height=40, fg_color="#0284C7", hover_color="#0369A1",
            font=ctk.CTkFont(size=12, weight="bold"), command=self.run_keybox_safety_1click
        )
        self.btn_keybox.grid(row=0, column=0, padx=(0, 5), sticky="ew")

        self.btn_safemode = ctk.CTkButton(
            safe_btns, text="", height=40, fg_color="#B45309", hover_color="#92400E",
            font=ctk.CTkFont(size=12, weight="bold"), command=self.run_bootloop_safe_mode
        )
        self.btn_safemode.grid(row=0, column=1, padx=(5, 0), sticky="ew")

    def toggle_language(self) -> None:
        self.lang = "en" if self.lang == "vi" else "vi"
        self._save_config()
        self._apply_language()

    def _apply_language(self) -> None:
        self.title(self.t("win_title"))
        self.lbl_header_title.configure(text=self.t("header_title"))
        self.lbl_header_sub.configure(text=self.t("header_sub"))
        self.btn_lang.configure(text=self.t("lang_btn"))

        # Update Tab labels cleanly
        seg_btns = getattr(self.tabs, "_segmented_button", None)
        if seg_btns is not None:
            for key, tab_key in [("Main", "tab_main"), ("Apps", "tab_apps"), ("Tools", "tab_tools")]:
                if key in seg_btns._buttons_dict:
                    seg_btns._buttons_dict[key].configure(text=self.t(tab_key))

        self.lbl_kernel.configure(text=self.t("kernel_label"))
        self.ksu_switch.configure(text=self.t("kernel_on") if self.ksu_enabled.get() else self.t("kernel_off"))
        self.lbl_selinux.configure(text=self.t("selinux_label"))
        self.lbl_profile.configure(text=self.t("profile_label"))
        self.btn_prof_switch.configure(text=self.t("profile_switch"))
        self.btn_prof_clone.configure(text=self.t("profile_clone"))
        self.btn_prof_expand.configure(text=self.t("profile_expand"))
        self.lbl_spoof.configure(text=self.t("spoof_label"))
        self.lbl_accel.configure(text=self.t("accel_label"))
        self.lbl_gpu.configure(text=self.t("gpu_label"))
        self._update_slider_labels()

        self.btn_start.configure(text=self.t("btn_start"))
        self.btn_stop.configure(text=self.t("btn_stop"))
        self.btn_install_ksu.configure(text=self.t("btn_install_ksu"))
        self.btn_spoof.configure(text=self.t("btn_spoof"))
        self.btn_adb_shell.configure(text=self.t("btn_adb"))
        self.btn_reset_data.configure(text=self.t("btn_reset"))

        self.lbl_quick_hub.configure(text=self.t("quick_hub_title"))
        self.btn_gsf_id.configure(text=self.t("btn_gsf_id"))
        self.btn_rand_id.configure(text=self.t("btn_rand_id"))
        self.btn_snap_save.configure(text=self.t("btn_snap_save"))
        self.btn_snap_load.configure(text=self.t("btn_snap_load"))
        self.btn_wifi_toggle.configure(text=self.t("btn_wifi_on") if self.wifi_sim_enabled.get() else self.t("btn_wifi_off"))
        self.btn_trim_ram.configure(text=self.t("btn_trim_ram"))

        self.lbl_apps_hint.configure(text=self.t("apps_hint"))
        self.btn_refresh_apps.configure(text=self.t("btn_refresh_apps"))
        self.entry_app_search.configure(placeholder_text=self.t("search_apps"))
        self.btn_launch_app.configure(text=self.t("btn_launch_app"))
        self.btn_shortcut.configure(text=self.t("btn_shortcut"))

        self.lbl_dnd_title.configure(text=self.t("dnd_title"))
        self.lbl_dnd_sub.configure(text=self.t("dnd_sub"))
        self.btn_pick_file.configure(text=self.t("btn_pick_file"))
        self.lbl_clip_title.configure(text=self.t("clip_title"))
        self.btn_clip_w2a.configure(text=self.t("btn_clip_win_to_and"))
        self.btn_clip_a2w.configure(text=self.t("btn_clip_and_to_win"))
        self.chk_auto_clip.configure(text=self.t("clip_auto"))
        self.lbl_safety_title.configure(text=self.t("safety_title"))
        self.btn_keybox.configure(text=self.t("btn_keybox"))
        self.btn_safemode.configure(text=self.t("btn_safemode"))

        if self.vm_process is None or self.vm_process.poll() is not None:
            self.status_text.set(self.t("status_idle"))

    def _update_slider_labels(self) -> None:
        c = int(round(self.cpu_cores.get()))
        r = int(round(self.ram_gb.get()))
        self.lbl_cpu.configure(text=f"{self.t('cpu_label')} {c} Cores")
        self.lbl_ram.configure(text=f"{self.t('ram_label')} {r} GB")
        self._save_config()

    def _on_ksu_toggle(self) -> None:
        self.ksu_switch.configure(text=self.t("kernel_on") if self.ksu_enabled.get() else self.t("kernel_off"))
        self._save_config()

    def _on_selinux_change(self, val: str) -> None:
        self.selinux_mode.set("enforcing" if "Enforcing" in val else "permissive")
        self._save_config()

    def _on_accel_change(self, val: str) -> None:
        if "TCG" in val and "Auto" not in val:
            self.accel_mode.set("tcg")
        elif val == "WHPX":
            self.accel_mode.set("whpx")
        else:
            self.accel_mode.set("auto")
        self._save_config()

    def _on_gpu_change(self, val: str) -> None:
        self.gpu_choice.set("virgl" if "VirGL" in val else "software")
        self._save_config()

    # ---------------- Storage Profile Actions ----------------
    def _on_profile_select(self, chosen: str) -> None:
        if chosen == self.loaded_profile:
            return
        if self.vm_process and self.vm_process.poll() is None:
            if self.loaded_profile:
                self.active_profile.set(self.loaded_profile)
            messagebox.showwarning("VM Running", "Tắt máy ảo trước khi đổi hồ sơ bộ nhớ / Stop VM first.")
            return
        self._activate_profile(chosen, force_reload=False)

    def _activate_profile(self, chosen: str, force_reload: bool = False) -> None:
        src = self.profiles_dir / f"{chosen}.qcow2"
        data_img = self.images_dir / "data.img"
        if not src.exists():
            if self.loaded_profile:
                self.active_profile.set(self.loaded_profile)
            messagebox.showerror("Missing Profile", f"Not found: {src}")
            return
        if not force_reload and self.loaded_profile and self.loaded_profile != chosen and data_img.exists():
            prev_dst = self.profiles_dir / f"{self.loaded_profile}.qcow2"
            try:
                shutil.copy2(data_img, prev_dst)
            except Exception as exc:
                console_log(f"[PROFILE] Warning: could not sync previous profile {self.loaded_profile}: {exc}")
        shutil.copy2(src, data_img)
        self.loaded_profile = chosen
        self.active_profile.set(chosen)
        self._save_config()
        console_log(f"[PROFILE] Switched active data.img -> {chosen}")
        self.status_text.set(f"Profile active: {chosen}")

    def switch_profile(self) -> None:
        if self.vm_process and self.vm_process.poll() is None:
            messagebox.showwarning("VM Running", "Tắt máy ảo trước khi đổi hồ sơ bộ nhớ / Stop VM first.")
            return
        self._activate_profile(self.active_profile.get(), force_reload=True)

    def clone_profile(self) -> None:
        if self.vm_process and self.vm_process.poll() is None:
            messagebox.showwarning("VM Running", "Tắt máy ảo trước khi nhân bản / Stop VM first.")
            return
        data_img = self.images_dir / "data.img"
        if not data_img.exists():
            return
        dialog = ctk.CTkInputDialog(text="Tên hồ sơ mới / New profile name:", title="Clone Profile")
        new_name = (dialog.get_input() or "").strip()
        safe_name = re.sub(r"[^A-Za-z0-9_-]", "_", new_name)
        if not safe_name:
            return
        if self.loaded_profile and self.loaded_profile != safe_name:
            try:
                shutil.copy2(data_img, self.profiles_dir / f"{self.loaded_profile}.qcow2")
            except Exception:
                pass
        dst = self.profiles_dir / f"{safe_name}.qcow2"
        shutil.copy2(data_img, dst)
        self.profile_menu.configure(values=self._list_profiles())
        self.active_profile.set(safe_name)
        self.loaded_profile = safe_name
        self._save_config()
        console_log(f"[PROFILE] Cloned current data.img -> {dst.name}")
        self.status_text.set(f"Cloned profile: {safe_name}")

    def expand_storage_10gb(self) -> None:
        if self.vm_process and self.vm_process.poll() is None:
            messagebox.showwarning("VM Running", "Tắt máy ảo trước khi mở rộng bộ nhớ / Stop VM first.")
            return
        if not self.qemu_img_exe.exists():
            messagebox.showerror("Missing Tool", f"Not found: {self.qemu_img_exe}")
            return
        data_img = self.images_dir / "data.img"
        try:
            subprocess.run(
                [str(self.qemu_img_exe), "resize", str(data_img), "+10G"],
                check=True,
                capture_output=True,
                text=True,
                creationflags=_no_window_flags(),
            )
            chosen = self.loaded_profile or self.active_profile.get()
            prof_img = self.profiles_dir / f"{chosen}.qcow2"
            if prof_img.exists():
                shutil.copy2(data_img, prof_img)
            console_log("[STORAGE] Expanded images/data.img by +10GB successfully.")
            self.status_text.set("Storage expanded (+10GB)")
        except Exception as exc:
            console_log(f"[STORAGE] Resize failed: {exc}")
            messagebox.showerror("Resize Failed", str(exc))

    # ---------------- VM Lifecycle ----------------
    def _detect_whpx_available(self) -> bool:
        if sys.platform != "win32":
            return False
        try:
            probe = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "(Get-WindowsOptionalFeature -Online -FeatureName HypervisorPlatform -ErrorAction SilentlyContinue).State",
                ],
                capture_output=True,
                text=True,
                timeout=6,
                creationflags=_no_window_flags(),
            )
            if "Enabled" in (probe.stdout or ""):
                return True
        except Exception:
            pass
        try:
            si = subprocess.run(
                ["systeminfo"], capture_output=True, text=True, timeout=8, creationflags=_no_window_flags()
            )
            if "A hypervisor has been detected" in (si.stdout or ""):
                return True
        except Exception:
            pass
        return False

    def _detect_accelerators(self) -> Dict[str, bool]:
        """Detect available Windows hypervisors (WHPX, AEHD, HAXM) without assuming unsupported features."""
        caps = {"whpx": self._detect_whpx_available(), "aehd": False, "haxm": False}
        if sys.platform != "win32":
            return caps
        qemu_help = ""
        if self.qemu_exe.exists():
            try:
                res = subprocess.run(
                    [str(self.qemu_exe), "-accel", "help"],
                    capture_output=True, text=True, timeout=5, creationflags=_no_window_flags(),
                )
                qemu_help = ((res.stdout or "") + "\n" + (res.stderr or "")).lower()
            except Exception:
                pass
        for svc, key in (("aehd", "aehd"), ("intelhaxm", "haxm")):
            try:
                sc = subprocess.run(
                    ["sc", "query", svc], capture_output=True, text=True, timeout=4, creationflags=_no_window_flags()
                )
                if sc.returncode == 0 and "RUNNING" in (sc.stdout or "").upper():
                    if not qemu_help or key in qemu_help or (key == "haxm" and "hax" in qemu_help):
                        caps[key] = True
            except Exception:
                pass
        return caps

    def _stream_file_serial(self, serial_path: Path, boot_state: dict, tier_done: threading.Event) -> None:
        """Tail QEMU -serial file output from byte 0 so zero early boot/panic bytes are dropped."""
        offset = 0
        carry = ""

        def _consume_chunk(chunk: str) -> None:
            nonlocal carry
            text = carry + chunk
            lines = text.splitlines(keepends=True)
            if lines and not lines[-1].endswith(("\n", "\r")):
                carry = lines.pop()
            else:
                carry = ""
            for raw in lines:
                clean = raw.rstrip("\r\n")
                if not clean:
                    continue
                low = clean.lower()
                netd_exit = re.search(r"Service 'netd'.*exited with status ([1-9]\d*)", clean, re.IGNORECASE)
                if netd_exit:
                    boot_state["netd_fail_count"] = boot_state.get("netd_fail_count", 0) + 1
                    boot_state["last_netd_exit_status"] = int(netd_exit.group(1))
                    console_log(
                        f"[NETWORK/FATAL] netd exited with status {netd_exit.group(1)}; "
                        "Android init may restart zygote. Preserve logs/android-logcat.log for root-cause analysis."
                    )
                if "[portable-boot] boot_completed=1" in low:
                    boot_state["boot_complete_seen"] = True
                    console_log("[ANDROID/BOOT] sys.boot_completed=1 confirmed by init marker.")
                if "early console in extract_kernel" in low:
                    boot_state["decompressor_count"] = boot_state.get("decompressor_count", 0) + 1
                if "executing: exec" in low and "switch_root" in low:
                    boot_state["switch_root_seen"] = True
                    boot_state["switch_root_ts"] = time.time()
                if "[init-wrapper]" in low:
                    boot_state["init_wrapper_seen"] = True
                if "[android/kmsg]" in low or "init first stage" in low or "init second stage" in low or "selinux_setup" in low:
                    boot_state["android_init_seen"] = True
                if "[portable-gfx]" in low:
                    boot_state["gfx_init_seen"] = True
                if "vendor.hwcomposer" in low and ("exited with status" in low or "crashed" in low):
                    if "exited with status 0" not in low:
                        boot_state["hwc_fail_count"] = boot_state.get("hwc_fail_count", 0) + 1
                if "surfaceflinger" in low and ("killed by signal 9" in low or "signal 9" in low or ("restarting" in low and "hwcomposer" not in low)):
                    boot_state["sf_fail_count"] = boot_state.get("sf_fail_count", 0) + 1
                if "has incorrect label or no domain transition" in low or "init encountered errors" in low:
                    boot_state["selinux_domain_errors"] = boot_state.get("selinux_domain_errors", 0) + 1
                if "user-defined mode not supported" in low:
                    boot_state["drm_mode_error"] = True
                if "starting service 'bootanim'" in low:
                    boot_state["bootanim_seen"] = True
                if (
                    "linux version" in low
                    or "[    0." in low
                    or "earlycon:" in low
                    or "booting linux" in low
                    or "kernel panic" in low
                    or "init:" in low
                    or "[initrd]" in low
                    or "[init-wrapper]" in low
                    or "[android/kmsg]" in low
                    or "detecting android-x86" in low
                ):
                    boot_state["kernel_seen"] = True
                boot_state["last_serial_ts"] = time.time()
                tail = boot_state.setdefault("serial_tail", [])
                tail.append(clean)
                if len(tail) > 20:
                    del tail[:-20]
                console_log(f"[KERNEL/SERIAL] {clean}")

        while not self.stop_log_threads.is_set():
            try:
                if serial_path.exists():
                    with serial_path.open("r", encoding="utf-8", errors="replace") as f:
                        f.seek(offset)
                        data = f.read()
                        if data:
                            offset = f.tell()
                            _consume_chunk(data)
            except Exception:
                pass
            if tier_done.is_set():
                break
            time.sleep(0.08)

        if carry.strip():
            console_log(f"[KERNEL/SERIAL] {carry.strip()}")

    def _get_windows_free_ram_mb(self) -> Optional[tuple[int, int]]:
        if sys.platform != "win32":
            return None
        try:
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):  # type: ignore[attr-defined]
                avail_phys_mb = int(stat.ullAvailPhys // (1024 * 1024))
                avail_commit_mb = int(stat.ullAvailPageFile // (1024 * 1024))
                return (avail_phys_mb, avail_commit_mb)
        except Exception:
            pass
        return None

    def _resolve_initrd_file(self, kernel_name: str) -> Path:
        """Pair kernel_ksunext -> initrd_ksunext.img and kernel_stock -> initrd_stock.img (fallback initrd.img)."""
        preferred = "initrd_ksunext.img" if kernel_name == "kernel_ksunext" else "initrd_stock.img"
        cand = self.images_dir / preferred
        if cand.exists() and cand.stat().st_size >= 512 * 1024:
            return cand
        return self.images_dir / "initrd.img"

    def _build_qemu_cmd(
        self,
        tier_id: str,
        allow_angle: Optional[bool] = None,
        serial_log_path: Optional[Path] = None,
        ram_mb_override: Optional[int] = None,
        use_hpet_off: bool = True,
        use_pio_fw_cfg: bool = False,
        kernel_name: Optional[str] = None,
        diag_log_path: Optional[Path] = None,
        gl_device_mode: str = "vga_gl",
    ) -> list[str]:
        chosen_kernel = kernel_name or ("kernel_ksunext" if self.ksu_enabled.get() else "kernel_stock")
        kernel_file = self.images_dir / chosen_kernel
        initrd_file = self._resolve_initrd_file(chosen_kernel)
        system_file = self.images_dir / "system.img"
        vendor_file = self.images_dir / "vendor.img"
        data_file = self.images_dir / "data.img"

        cores = max(1, min(4, int(self.cpu_cores.get())))
        ram_mb = ram_mb_override if ram_mb_override is not None else max(1536, min(6144, int(self.ram_gb.get()) * 1024))
        use_virgl = (self.gpu_choice.get() == "virgl") if allow_angle is None else allow_angle
        selinux_arg = (
            "androidboot.selinux=enforcing"
            if self.selinux_mode.get() == "enforcing"
            else "androidboot.selinux=permissive"
        )

        # Intel Core i5-3475S (Ivy Bridge, NO AVX2/AVX512/BMI2) CPU + Hypervisor Matrix
        ivy_cpu = "IvyBridge,-ht,-tsc-deadline,+ssse3,+sse4.1,+sse4.2,+popcnt"
        if tier_id in ("whpx_host", "whpx_host_stock"):
            machine_arg = "q35,hpet=off" if use_hpet_off else "q35"
            accel_args = ["-accel", "whpx,kernel-irqchip=off", "-cpu", "host"]
        elif tier_id in ("whpx_ivy", "whpx_ivy_stock"):
            machine_arg = "q35,hpet=off" if use_hpet_off else "q35"
            accel_args = ["-accel", "whpx,kernel-irqchip=off", "-cpu", ivy_cpu]
        elif tier_id in ("whpx_nehalem", "whpx_pc_stock"):
            machine_arg = "pc,hpet=off" if use_hpet_off else "pc"
            accel_args = ["-accel", "whpx,kernel-irqchip=off", "-cpu", "Nehalem"]
        elif tier_id == "aehd_host":
            machine_arg = "q35,hpet=off" if use_hpet_off else "q35"
            accel_args = ["-accel", "aehd", "-cpu", "host"]
        elif tier_id == "haxm_host":
            machine_arg = "q35,hpet=off" if use_hpet_off else "q35"
            accel_args = ["-accel", "hax", "-cpu", "host"]
        else:
            machine_arg = "pc,hpet=off" if use_hpet_off else "pc"
            accel_args = ["-accel", "tcg,thread=multi", "-cpu", ivy_cpu]

        cmd = [
            str(self.qemu_exe),
            "-name", "Portable-Android13-Win11",
            "-no-reboot",
            "-machine", machine_arg,
            "-smp", f"{cores},cores={cores},threads=1,sockets=1",
            "-m", str(ram_mb),
            *accel_args,
        ]

        if use_pio_fw_cfg:
            cmd += ["-global", "fw_cfg.dma_enabled=off"]

        # Intel HD Graphics 4000 Safe Cascade:
        # Default Auto: virtio-vga (DRM llvmpipe, gl=off, EDID 1280x720) -> -vga std (gl=off)
        # Experimental VirGL: virtio-vga-gl (gl=es/ANGLE) -> virtio-vga-gl (gl=on) -> virtio-vga (llvmpipe) -> -vga std
        if use_virgl and gl_device_mode == "vga_gl":
            cmd += ["-device", "virtio-vga-gl", "-display", "sdl,gl=es"]
            gfx_cmdline = "HWACCEL=1"
        elif gl_device_mode == "vga_gl_desktop":
            cmd += ["-device", "virtio-vga-gl", "-display", "sdl,gl=on"]
            gfx_cmdline = "HWACCEL=1"
        elif gl_device_mode == "gpu_gl_pci":
            cmd += ["-vga", "none", "-device", "virtio-gpu-gl-pci", "-display", "sdl,gl=on"]
            gfx_cmdline = "HWACCEL=1"
        elif gl_device_mode == "virtio_sw":
            cmd += ["-device", "virtio-vga", "-display", "sdl,gl=off"]
            gfx_cmdline = "HWACCEL=0 MESA_LLVMPIPE=1 EGL=mesa HWC_HIDL=drmfb"
        else:
            cmd += ["-vga", "std", "-display", "sdl,gl=off"]
            gfx_cmdline = "HWACCEL=0 EGL=angle HWC_HIDL=drmfb"

        if diag_log_path is not None:
            cmd += ["-d", "guest_errors,cpu_reset", "-D", str(diag_log_path)]

        serial_target = f"file:{serial_log_path}" if serial_log_path is not None else "stdio"
        cmd += [
            "-device", "virtio-rng-pci",
            "-device", "virtio-balloon-pci",
            "-usb",
            "-device", "usb-tablet",
            "-device", "usb-kbd",
            "-audiodev", "dsound,id=snd0",
            "-device", "ich9-intel-hda",
            "-device", "hda-duplex,audiodev=snd0",
            "-netdev", "user,id=net0,hostfwd=tcp:127.0.0.1:5555-:5555",
            "-device", "e1000,netdev=net0",
            "-drive", f"file={system_file},if=virtio,format=qcow2,cache=writeback,readonly=on",
            "-drive", f"file={vendor_file},if=virtio,format=qcow2,cache=writeback,readonly=on",
            "-drive", f"file={data_file},if=virtio,format=qcow2,cache=writeback",
            "-kernel", str(kernel_file),
            "-initrd", str(initrd_file),
            "-append", (
                "root=/dev/ram0 androidboot.hardware=android_x86_64 "
                f"{selinux_arg} androidboot.init_fatal_panic=true "
                f"{gfx_cmdline} "
                "DATA=/dev/vdc androidboot.console=ttyS0 printk.devkmsg=on printk.always_kmsg_dump=1 "
                "nokaslr panic=0 earlycon=uart8250,io,0x3f8,115200 "
                "console=tty0 console=ttyS0,115200 SERIAL=ttyS0 loglevel=7"
            ),
            "-serial", serial_target,
        ]
        return cmd

    def _preflight_check(self) -> tuple[bool, list[str], bool, int]:
        kernel_name = "kernel_ksunext" if self.ksu_enabled.get() else "kernel_stock"
        initrd_file = self._resolve_initrd_file(kernel_name)
        checks = [
            (self.qemu_exe, 1024 * 1024, "QEMU binary"),
            (initrd_file, 512 * 1024, f"Android initrd ({initrd_file.name})"),
            (self.images_dir / "system.img", 50 * 1024 * 1024, "LineageOS 20 GApps system image"),
            (self.images_dir / "vendor.img", 10 * 1024 * 1024, "Bliss OS 16.9 API-33 vendor image"),
            (self.images_dir / "data.img", 64 * 1024, "User data qcow2"),
            (self.images_dir / kernel_name, 1024 * 1024, f"Kernel ({kernel_name})"),
        ]
        issues: list[str] = []
        for path, min_bytes, label in checks:
            if not path.exists():
                issues.append(f"Missing {label}: {path}")
            else:
                size = path.stat().st_size
                if size < min_bytes:
                    issues.append(f"Corrupted/too small {label} ({size} bytes): {path}")

        allow_virgl = self.gpu_choice.get() == "virgl"
        if allow_virgl:
            has_egl = (self.bin_dir / "libEGL.dll").exists() and (self.bin_dir / "libGLESv2.dll").exists()
            if not has_egl:
                console_log("[PREFLIGHT] ANGLE DLLs (libEGL.dll/libGLESv2.dll) missing; Experimental VirGL will use desktop GL or fallback to VirtIO-SW.")

        initial_ram_mb = max(1536, min(6144, int(self.ram_gb.get()) * 1024))
        mem_info = self._get_windows_free_ram_mb()
        if mem_info is not None:
            avail_phys, avail_commit = mem_info
            budget_mb = max(1536, avail_commit - 512)
            if initial_ram_mb > budget_mb:
                for cand in (3072, 2048, 1536):
                    if cand <= budget_mb or cand == 1536:
                        console_log(
                            f"[PREFLIGHT] Windows free RAM/commit tight ({avail_phys} MB phys / {avail_commit} MB commit) "
                            f"-> auto-capping initial VM RAM from {initial_ram_mb} MB to {cand} MB"
                        )
                        initial_ram_mb = cand
                        break

        if not self.adb_exe.exists():
            console_log(f"[PREFLIGHT] Warning: ADB not found at {self.adb_exe}; spoofing/logcat disabled.")
        if not issues:
            console_log(
                f"[PREFLIGHT] OK · Kernel={kernel_name} · Initrd={initrd_file.name} · Accel={self.accel_mode.get().upper()} · "
                f"SELinux={self.selinux_mode.get().upper()} · RAM={initial_ram_mb}MB · "
                f"GPU={'Experimental VirGL' if allow_virgl else 'VirtIO-SW llvmpipe (gl=off)'}"
            )
        return (len(issues) == 0, issues, allow_virgl, initial_ram_mb)

    def start_vm(self) -> None:
        if self.vm_process is not None and self.vm_process.poll() is None:
            console_log("[VM] QEMU is already running.")
            return

        ok, issues, allow_virgl, initial_ram_mb = self._preflight_check()
        if not ok:
            console_log("[PREFLIGHT] Failed:\n  - " + "\n  - ".join(issues))
            messagebox.showerror("Pre-Flight Check Failed", "Cannot start Android VM:\n" + "\n".join(issues))
            return

        self.stop_log_threads.clear()
        self.adb_connected = False
        self.active_kernel_name = "kernel_ksunext" if self.ksu_enabled.get() else "kernel_stock"
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.ksu_switch.configure(state="disabled")
        self.selinux_seg.configure(state="disabled")
        self.accel_seg.configure(state="disabled")
        self.gpu_seg.configure(state="disabled")
        threading.Thread(
            target=self._launch_vm_worker,
            args=(allow_virgl, initial_ram_mb),
            daemon=True,
        ).start()

    def _force_kill_vm(self, proc: Optional[subprocess.Popen]) -> None:
        if proc is None or proc.poll() is not None:
            return
        try:
            proc.terminate()
            proc.wait(timeout=2)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    def _capture_prekernel_diag(self, env: dict, ram_mb: int, kernel_name: str) -> None:
        """Run a fast 6s -no-reboot -d guest_errors,cpu_reset probe to log both serial and CPU fault state."""
        ts = int(time.time() * 1000)
        diag_path = Path(tempfile.gettempdir()) / f"qemu_cpu_reset_{ts}.log"
        diag_serial_path = Path(tempfile.gettempdir()) / f"qemu_diag_serial_{ts}.log"
        diag_serial_path.write_text("", encoding="utf-8")
        cmd = self._build_qemu_cmd(
            "tcg_ivy",
            allow_angle=False,
            serial_log_path=diag_serial_path,
            ram_mb_override=min(ram_mb, 2048),
            use_hpet_off=True,
            use_pio_fw_cfg=True,
            kernel_name=kernel_name,
            diag_log_path=diag_path,
            gl_device_mode="std",
        )
        console_log(f"[DIAG] Running -no-reboot crash capture (serial + -d guest_errors,cpu_reset) for {kernel_name}...")
        proc: Optional[subprocess.Popen] = None
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(self.bin_dir),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            deadline = time.time() + 6.0
            while proc.poll() is None and time.time() < deadline and not self.stop_log_threads.is_set():
                time.sleep(0.25)
            self._force_kill_vm(proc)
            if diag_serial_path.exists():
                ser_lines = [ln.rstrip("\r\n") for ln in diag_serial_path.read_text(encoding="utf-8", errors="replace").splitlines() if ln.strip()]
                if ser_lines:
                    console_log(f"[QEMU/DIAG-SERIAL] --- Captured {len(ser_lines)} serial lines (tail 15) ---")
                    for ln in ser_lines[-15:]:
                        console_log(f"[QEMU/DIAG-SERIAL] {ln}")
            if diag_path.exists():
                lines = [ln.rstrip("\r\n") for ln in diag_path.read_text(encoding="utf-8", errors="replace").splitlines() if ln.strip()]
                if lines:
                    console_log(f"[QEMU/DIAG] --- Captured {len(lines)} CPU reset/guest_error lines (tail 18) ---")
                    for ln in lines[-18:]:
                        console_log(f"[QEMU/DIAG] {ln}")
                else:
                    console_log("[QEMU/DIAG] No CPU reset lines emitted before timeout.")
        except Exception as exc:
            console_log(f"[QEMU/DIAG] Probe note: {exc}")
        finally:
            self._force_kill_vm(proc)
            for p in (diag_path, diag_serial_path):
                try:
                    p.unlink(missing_ok=True)
                except Exception:
                    pass

    def _launch_vm_worker(self, allow_angle: bool = True, initial_ram_mb: int = 4096) -> None:
        primary_kernel = "kernel_ksunext" if self.ksu_enabled.get() else "kernel_stock"
        stock_available = (self.images_dir / "kernel_stock").exists() and (self.images_dir / "kernel_stock").stat().st_size >= 1024 * 1024
        mode = self.accel_mode.get()
        caps = self._detect_accelerators() if mode in ("auto", "whpx") else {"whpx": False, "aehd": False, "haxm": False}

        if mode == "tcg":
            cascade = [("tcg_ivy", allow_angle, primary_kernel)]
            if primary_kernel == "kernel_ksunext" and stock_available:
                cascade.append(("tcg_stock", False, "kernel_stock"))
            console_log("[ACCEL] Forced TCG (-cpu IvyBridge,+ssse3,+sse4.1,+sse4.2,+popcnt, fw_cfg PIO)")
        elif mode == "whpx":
            cascade = [
                ("whpx_host", allow_angle, primary_kernel),
                ("whpx_ivy", allow_angle, primary_kernel),
                ("whpx_nehalem", False, primary_kernel),
            ]
            if primary_kernel == "kernel_ksunext" and stock_available:
                cascade.append(("whpx_pc_stock", False, "kernel_stock"))
        else:
            cascade = []
            if caps["whpx"]:
                console_log("[ACCEL] WHPX detected -> i5-3475S Cascade: WHPX host -> WHPX IvyBridge -> WHPX Nehalem -> TCG IvyBridge -> kernel_stock Rescue")
                cascade.extend([
                    ("whpx_host", allow_angle, primary_kernel),
                    ("whpx_ivy", allow_angle, primary_kernel),
                    ("whpx_nehalem", False, primary_kernel),
                ])
            if caps["aehd"]:
                console_log("[ACCEL] AEHD detected -> Adding AEHD -cpu host tier")
                cascade.append(("aehd_host", allow_angle, primary_kernel))
            if caps["haxm"]:
                console_log("[ACCEL] HAXM detected -> Adding HAXM -cpu host tier")
                cascade.append(("haxm_host", allow_angle, primary_kernel))
            if not cascade:
                console_log("[ACCEL] No Windows hypervisor active -> Using -accel tcg,thread=multi (-cpu IvyBridge,+ssse3,+sse4.1,+sse4.2,+popcnt)")
            cascade.append(("tcg_ivy", allow_angle, primary_kernel))
            if primary_kernel == "kernel_ksunext" and stock_available:
                if caps["whpx"]:
                    cascade.append(("whpx_pc_stock", False, "kernel_stock"))
                cascade.append(("tcg_stock", False, "kernel_stock"))

        base_env = os.environ.copy()
        base_env["PATH"] = f"{self.bin_dir};{base_env.get('PATH', '')}"

        fatal_markers = (
            "unexpected vp exit",
            "vp exit code",
            "unrecoverable",
            "whpx: injection failed",
            "failed to initialize whpx",
            "hv_vmm",
            "hresult",
            "no accelerator",
            "qemu: fatal",
        )
        kernel_boot_markers = (
            "linux version",
            "booting linux",
            "earlycon:",
            "[    0.",
            "[initrd]",
            "[init-wrapper]",
            "[android/kmsg]",
            "detecting android-x86",
        )

        try:
            _BOOT_LOG_PATH.write_text("", encoding="utf-8")
        except Exception:
            pass

        adb_started = False
        diag_captured = False

        for idx, (tier_id, tier_angle, tier_kernel) in enumerate(cascade):
            if self.stop_log_threads.is_set():
                break

            self.active_kernel_name = tier_kernel
            tier_initrd = self._resolve_initrd_file(tier_kernel).name
            tier_ram_mb = initial_ram_mb
            use_hpet_off = True
            use_pio_fw_cfg = not (tier_id.startswith("whpx") or tier_id.startswith("aehd") or tier_id.startswith("haxm"))
            gl_device_mode = "vga_gl" if tier_angle else "virtio_sw"

            if tier_kernel == "kernel_stock" and primary_kernel == "kernel_ksunext":
                console_log(
                    f"[RESCUE] '{primary_kernel}' failed/halted during early boot -> auto-booting verified 'kernel_stock' ({tier_id}, initrd={tier_initrd})!"
                )

            while not self.stop_log_threads.is_set():
                serial_log_path = Path(tempfile.gettempdir()) / f"qemu_serial_{int(time.time() * 1000)}.log"
                try:
                    serial_log_path.write_text("", encoding="utf-8")
                except Exception:
                    pass

                tier_env = base_env.copy()
                if gl_device_mode == "vga_gl":
                    tier_env["SDL_OPENGL_ES_DRIVER"] = "1"
                    tier_env["ANGLE_DEFAULT_PLATFORM"] = "d3d11"
                else:
                    tier_env.pop("SDL_OPENGL_ES_DRIVER", None)
                    tier_env.pop("ANGLE_DEFAULT_PLATFORM", None)

                cmd = self._build_qemu_cmd(
                    tier_id,
                    allow_angle=tier_angle,
                    serial_log_path=serial_log_path,
                    ram_mb_override=tier_ram_mb,
                    use_hpet_off=use_hpet_off,
                    use_pio_fw_cfg=use_pio_fw_cfg,
                    kernel_name=tier_kernel,
                    gl_device_mode=gl_device_mode,
                )
                fw_mode = "PIO" if use_pio_fw_cfg else "DMA"
                console_log(
                    f"[QEMU Tier {idx + 1}/{len(cascade)} · {tier_id} · {tier_kernel} + {tier_initrd} · gpu={gl_device_mode} · fw_cfg={fw_mode} · {tier_ram_mb}MB] Launch: {' '.join(cmd)}"
                )
                self._set_status(f"Booting Android 13 ({tier_id} · {tier_kernel} · {tier_initrd})...")

                proc = subprocess.Popen(
                    cmd,
                    cwd=str(self.bin_dir),
                    env=tier_env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )
                self.vm_process = proc

                if not adb_started:
                    adb_started = True
                    threading.Thread(target=self._adb_logcat_worker, daemon=True).start()

                start_ts = time.time()
                boot_state = {
                    "kernel_seen": False,
                    "switch_root_seen": False,
                    "switch_root_ts": 0.0,
                    "init_wrapper_seen": False,
                    "android_init_seen": False,
                    "gfx_init_seen": False,
                    "hwc_fail_count": 0,
                    "sf_fail_count": 0,
                    "netd_fail_count": 0,
                    "last_netd_exit_status": None,
                    "boot_complete_seen": False,
                    "gfx_loop_detected": False,
                    "last_serial_ts": start_ts,
                    "decompressor_count": 0,
                    "killed_by_watchdog": False,
                    "mem_error": False,
                    "hpet_opt_error": False,
                    "fwcfg_opt_error": False,
                    "gl_opt_error": False,
                    "serial_tail": [],
                }
                tier_done = threading.Event()

                tailer_thread = threading.Thread(
                    target=self._stream_file_serial,
                    args=(serial_log_path, boot_state, tier_done),
                    daemon=True,
                )
                tailer_thread.start()

                _gl_next = {
                    "vga_gl": "vga_gl_desktop",
                    "vga_gl_desktop": "virtio_sw",
                    "gpu_gl_pci": "virtio_sw",
                    "virtio_sw": "std",
                }
                has_gl_fallback = gl_device_mode in _gl_next
                has_next_tier = idx < len(cascade) - 1
                prekernel_secs = 28.0 if tier_id.startswith("tcg") else 18.0
                stall_secs = 150.0 if tier_id.startswith("tcg") else 110.0

                def _watchdog(
                    p: subprocess.Popen = proc,
                    pk_secs: float = prekernel_secs,
                    st_secs: float = stall_secs,
                    tid: str = tier_id,
                    tk: str = tier_kernel,
                    gl_mode: str = gl_device_mode,
                    can_gl_fallback: bool = has_gl_fallback,
                    can_escalate: bool = has_next_tier,
                ) -> None:
                    last_hint_ts = 0.0
                    while not tier_done.wait(0.5):
                        if self.stop_log_threads.is_set() or self.adb_connected or p.poll() is not None:
                            return
                        now = time.time()
                        elapsed_w = now - start_ts

                        # 1) Detect early extract_kernel reboot loop
                        if boot_state.get("decompressor_count", 0) >= 2 and not boot_state["kernel_seen"]:
                            if can_escalate:
                                boot_state["killed_by_watchdog"] = True
                                console_log(
                                    f"[WATCHDOG] {tid} ({tk}) looped after 'Booting the kernel' (extract_kernel ran {boot_state['decompressor_count']}x) -> stopping & rescuing..."
                                )
                                self._force_kill_vm(p)
                                return

                        # 2) Detect pre-kernel hang
                        if not boot_state["kernel_seen"] and elapsed_w >= pk_secs:
                            if can_escalate:
                                boot_state["killed_by_watchdog"] = True
                                console_log(
                                    f"[WATCHDOG] {tid} ({tk}) failed to reach Linux kernel boot after {pk_secs:.0f}s -> stopping & escalating..."
                                )
                                self._force_kill_vm(p)
                                return

                        # 3) Detect silent hang right at switch_root -> droidport_init_wrapper
                        sr_ts = boot_state.get("switch_root_ts", 0.0)
                        if (
                            boot_state.get("switch_root_seen")
                            and not boot_state.get("init_wrapper_seen")
                            and sr_ts > 0
                            and (now - sr_ts) >= 25.0
                        ):
                            if can_escalate:
                                boot_state["killed_by_watchdog"] = True
                                console_log(
                                    f"[WATCHDOG] {tid} ({tk}) stalled for 25s right after switch_root (no [INIT-WRAPPER] output) -> stopping & escalating..."
                                )
                                self._force_kill_vm(p)
                                return
                            elif now - last_hint_ts > 30.0:
                                last_hint_ts = now
                                console_log(
                                    f"[DIAG-HINT] {tid} ({tk}) has not emitted [INIT-WRAPPER] after switch_root. Try toggling 'TCG (Safe)' or 'Software' GPU if frozen."
                                )

                        # 4) Detect post-switch_root Android init stall (zero serial/kmsg activity)
                        idle_secs = now - boot_state.get("last_serial_ts", start_ts)
                        if boot_state.get("switch_root_seen") and idle_secs >= st_secs:
                            if can_escalate:
                                boot_state["killed_by_watchdog"] = True
                                console_log(
                                    f"[WATCHDOG] {tid} ({tk}) had no serial/kmsg activity for {st_secs:.0f}s before ADB online -> escalating..."
                                )
                                self._force_kill_vm(p)
                                return
                            elif now - last_hint_ts > 45.0:
                                last_hint_ts = now
                                console_log(
                                    f"[DIAG-HINT] Still waiting for Android ADB on {tid} ({tk}); no serial logs for {idle_secs:.0f}s."
                                )

                        # 5) Detect vendor.hwcomposer / surfaceflinger graphics HAL crash loop
                        hwc_fails = boot_state.get("hwc_fail_count", 0)
                        sf_fails = boot_state.get("sf_fail_count", 0)
                        if hwc_fails >= 2 or sf_fails >= 3:
                            if can_gl_fallback or can_escalate:
                                boot_state["gfx_loop_detected"] = True
                                boot_state["killed_by_watchdog"] = True
                                console_log(
                                    f"[WATCHDOG] Graphics HAL crash loop on {tid} ({tk}, gpu={gl_mode}: "
                                    f"hwcomposer_fails={hwc_fails}, surfaceflinger_fails={sf_fails}) -> stepping down..."
                                )
                                self._force_kill_vm(p)
                                return

                threading.Thread(target=_watchdog, daemon=True).start()

                assert proc.stdout is not None
                for line in proc.stdout:
                    clean = line.rstrip("\r\n")
                    if clean:
                        console_log(f"[QEMU/DMESG] {clean}")
                        low = clean.lower()
                        if any(km in low for km in kernel_boot_markers):
                            boot_state["kernel_seen"] = True
                        if "cannot set up guest memory" in low or "cannot allocate memory" in low or "pc.ram" in low:
                            boot_state["mem_error"] = True
                        if "hpet" in low and ("invalid" in low or "not found" in low or "unknown" in low):
                            boot_state["hpet_opt_error"] = True
                        if "fw_cfg" in low and ("not found" in low or "invalid" in low or "unknown" in low or "property" in low):
                            boot_state["fwcfg_opt_error"] = True
                        if any(gm in low for gm in ("virtio-vga-gl", "virtio-gpu-gl", "virtio-vga", "opengl is not available", "unable to create opengl context", "vrend", "virgl", "egl", "gl=es", "gl=on", "illegal command buffer", "failed to dispatch", "context error reported")):
                            if any(err in low for err in ("not found", "invalid", "unknown", "unsupported", "could not", "failed", "unable to", "no such", "error", "illegal", "vrend_check_no_error", "vrend_decode_ctx_submit_cmd")):
                                boot_state["gl_opt_error"] = True
                                if gl_device_mode in ("vga_gl", "vga_gl_desktop", "gpu_gl_pci") and any(
                                    vf in low for vf in (
                                        "virgl could not be initialized",
                                        "failed to initialize vrend",
                                        "unable to create opengl context",
                                        "opengl is not available",
                                        "vrend_check_no_error",
                                        "vrend_decode_ctx_submit_cmd",
                                        "illegal command buffer",
                                        "failed to dispatch",
                                        "context error reported",
                                    )
                                ):
                                    console_log(
                                        f"[RETRY-FAST] VirGL/OpenGL command buffer or context failed on '{gl_device_mode}' ({clean}) -> stepping down GPU immediately..."
                                    )
                                    self._force_kill_vm(proc)
                                    break
                        if "invalid option" in low:
                            if use_hpet_off:
                                boot_state["hpet_opt_error"] = True
                            elif use_pio_fw_cfg:
                                boot_state["fwcfg_opt_error"] = True
                        if tier_id.startswith(("whpx", "aehd", "haxm")) and any(fm in low for fm in fatal_markers):
                            boot_state["killed_by_watchdog"] = True
                            console_log(
                                f"[WATCHDOG] Fatal hypervisor error detected ('{clean}') -> closing frozen QEMU window and switching tier..."
                            )
                            self._force_kill_vm(proc)
                            break

                rc = proc.wait()
                tier_done.set()
                tailer_thread.join(timeout=1.5)
                try:
                    serial_log_path.unlink(missing_ok=True)
                except Exception:
                    pass
                elapsed = time.time() - start_ts
                console_log(f"[QEMU · {tier_id} · {tier_kernel}] Exited with code {rc} after {elapsed:.1f}s")

                if not self.stop_log_threads.is_set() and boot_state.get("gfx_loop_detected") and gl_device_mode in _gl_next:
                    next_gl = _gl_next[gl_device_mode]
                    console_log(
                        f"[RETRY] Graphics HAL (hwcomposer/surfaceflinger) crash loop on '{gl_device_mode}' -> stepping down GPU to '{next_gl}'..."
                    )
                    gl_device_mode = next_gl
                    continue

                if not self.stop_log_threads.is_set() and boot_state["gl_opt_error"] and gl_device_mode in _gl_next:
                    next_gl = _gl_next[gl_device_mode]
                    console_log(f"[RETRY] Display/GL device '{gl_device_mode}' unsupported/failed -> stepping down to '{next_gl}'...")
                    gl_device_mode = next_gl
                    continue

                if not self.stop_log_threads.is_set() and boot_state["hpet_opt_error"] and use_hpet_off:
                    use_hpet_off = False
                    console_log(f"[RETRY] QEMU rejected hpet=off on {tier_id} -> retrying same tier without hpet=off...")
                    continue

                if not self.stop_log_threads.is_set() and boot_state["fwcfg_opt_error"] and use_pio_fw_cfg:
                    use_pio_fw_cfg = False
                    console_log(f"[RETRY] QEMU rejected fw_cfg.dma_enabled=off on {tier_id} -> retrying with default fw_cfg...")
                    continue

                if not self.stop_log_threads.is_set() and boot_state["mem_error"]:
                    next_ram = next((r for r in (3072, 2048, 1536) if r < tier_ram_mb), None)
                    if next_ram is not None:
                        console_log(
                            f"[RETRY] Windows could not allocate {tier_ram_mb} MB for pc.ram -> stepping down to {next_ram} MB..."
                        )
                        tier_ram_mb = next_ram
                        self._set_status(f"Retrying {tier_id} with {tier_ram_mb}MB RAM...")
                        time.sleep(0.4)
                        continue

                if (
                    not self.stop_log_threads.is_set()
                    and rc != 0
                    and elapsed < 15.0
                    and not boot_state["killed_by_watchdog"]
                    and gl_device_mode in _gl_next
                ):
                    next_gl = _gl_next[gl_device_mode]
                    console_log(f"[RETRY] Early QEMU crash on '{gl_device_mode}' ({elapsed:.1f}s, rc={rc}) -> stepping down to '{next_gl}'...")
                    gl_device_mode = next_gl
                    continue

                break

            guest_reboot_stopped = (
                not self.stop_log_threads.is_set()
                and not self.adb_connected
                and boot_state["kernel_seen"]
                and not boot_state["killed_by_watchdog"]
                and elapsed < 90.0
            )
            if guest_reboot_stopped:
                console_log(
                    f"[CRASH/NO-REBOOT] {tier_id} ({tier_kernel}) halted cleanly on guest reboot/panic after {elapsed:.1f}s (rc={rc}). Last serial lines:"
                )
                for tail_line in boot_state.get("serial_tail", [])[-10:]:
                    console_log(f"  [TAIL] {tail_line}")

            pre_kernel_failed = (
                not self.stop_log_threads.is_set()
                and not self.adb_connected
                and not boot_state["kernel_seen"]
                and (boot_state["killed_by_watchdog"] or elapsed < 45.0)
            )
            if pre_kernel_failed and not boot_state["killed_by_watchdog"]:
                console_log(
                    f"[PRE-KERNEL/FAULT] {tier_id} ({tier_kernel}) exited before Linux earlycon (elapsed={elapsed:.1f}s, rc={rc}, 0 kernel lines) -> triggering pre-kernel diagnostic."
                )

            if pre_kernel_failed and not diag_captured and (tier_id.startswith("tcg") or idx == len(cascade) - 1 or (idx + 1 < len(cascade) and cascade[idx + 1][2] != tier_kernel)):
                diag_captured = True
                self._capture_prekernel_diag(base_env, tier_ram_mb, tier_kernel)

            early_boot_failed = (
                not self.stop_log_threads.is_set()
                and not self.adb_connected
                and (
                    boot_state["killed_by_watchdog"]
                    or guest_reboot_stopped
                    or pre_kernel_failed
                    or (rc != 0 and elapsed < 60.0)
                )
            )
            has_next = idx < len(cascade) - 1
            if has_next and early_boot_failed:
                next_tier, _, next_kernel = cascade[idx + 1]
                console_log(f"[ACCEL] Escalating cleanly to next tier: {next_tier} ({next_kernel})...")
                self._set_status(f"Recovering via {next_tier} ({next_kernel})...")
                time.sleep(0.6)
                continue
            break

        # Sync updated data.img back into currently loaded profile on shutdown
        chosen = self.loaded_profile or self.active_profile.get()
        data_img = self.images_dir / "data.img"
        if data_img.exists() and chosen:
            try:
                shutil.copy2(data_img, self.profiles_dir / f"{chosen}.qcow2")
            except Exception:
                pass

        self.adb_connected = False
        self.stop_log_threads.set()
        self._stop_logcat()
        self.after(0, self._reset_vm_buttons)

    def _adb_logcat_worker(self) -> None:
        if not self.adb_exe.exists():
            return
        console_log("[ADB] Waiting for Android ADB on 127.0.0.1:5555...")
        connected = False
        while not self.stop_log_threads.is_set():
            proc = self.vm_process
            if proc is None or proc.poll() is not None:
                time.sleep(1.0)
                continue
            try:
                subprocess.run(
                    [str(self.adb_exe), "connect", "127.0.0.1:5555"],
                    capture_output=True, text=True, timeout=5, creationflags=_no_window_flags(),
                )
                chk = subprocess.run(
                    [str(self.adb_exe), "-s", "127.0.0.1:5555", "get-state"],
                    capture_output=True, text=True, timeout=5, creationflags=_no_window_flags(),
                )
                if chk.returncode == 0 and "device" in (chk.stdout or ""):
                    connected = True
                    break
            except Exception:
                pass
            time.sleep(3)

        if not connected or self.stop_log_threads.is_set():
            return

        self.adb_connected = True
        if self.active_kernel_name == "kernel_stock" and self.ksu_enabled.get():
            kernel_tag = "Stock Rescue"
        elif self.active_kernel_name == "kernel_ksunext":
            kernel_tag = "KSU Next"
        else:
            kernel_tag = "Stock"
        sel_tag = self.selinux_mode.get().upper()
        self._set_status(f"Online ({kernel_tag} · SELinux {sel_tag}) · ADB 127.0.0.1:5555")
        console_log(f"[ADB] Connected! Verifying native SELinux & storage labels ({sel_tag})...")
        spoof_device.ensure_selinux_boot_health(str(self.adb_exe), self.selinux_mode.get(), console_log)
        self._set_status(f"Online ({kernel_tag} · SELinux {sel_tag}) · ADB 127.0.0.1:5555")
        console_log("[ADB] Streaming adb logcat...")
        self.after(500, self.refresh_installed_apps)

        log_dir = BASE_DIR / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "android-logcat.log"
        previous_log = log_dir / "android-logcat.previous.log"
        max_log_bytes = 32 * 1024 * 1024
        log_bytes_written = 0
        log_file = None
        try:
            log_file = log_path.open("w", encoding="utf-8", errors="replace", buffering=1)
            self.logcat_process = subprocess.Popen(
                [
                    str(self.adb_exe), "-s", "127.0.0.1:5555",
                    "logcat", "-b", "all", "-v", "threadtime",
                ],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
                creationflags=_no_window_flags(),
            )
            assert self.logcat_process.stdout is not None
            console_log(f"[ADB] Full logcat buffers enabled; writing diagnostics to {log_path}.")
            for line in self.logcat_process.stdout:
                if self.stop_log_threads.is_set():
                    break
                clean = line.rstrip("\r\n")
                if not clean:
                    continue
                log_file.write(clean + "\n")
                log_bytes_written += len((clean + "\n").encode("utf-8", errors="replace"))
                if log_bytes_written >= max_log_bytes:
                    log_file.close()
                    previous_log.unlink(missing_ok=True)
                    if log_path.exists():
                        log_path.replace(previous_log)
                    log_file = log_path.open("w", encoding="utf-8", errors="replace", buffering=1)
                    log_bytes_written = 0
                    console_log("[ADB] Rotated full logcat; previous capture saved as logs/android-logcat.previous.log.")
                if (
                    re.search(r"\s[EWFA]\s", clean)
                    or re.search(
                        r"\b(netd|NetworkStack|ConnectivityService|IpClient|BpfLoader|crash_dump|tombstoned)\b",
                        clean,
                        re.IGNORECASE,
                    )
                ):
                    console_log(f"[LOGCAT] {clean}")
        except Exception as exc:
            console_log(f"[ADB/LOGCAT] Failed to capture full Android logcat: {exc}")
        finally:
            if log_file is not None:
                try:
                    log_file.close()
                except Exception:
                    pass
    def _stop_logcat(self) -> None:
        if self.logcat_process and self.logcat_process.poll() is None:
            try:
                self.logcat_process.terminate()
            except Exception:
                pass
        self.logcat_process = None

    def _reset_vm_buttons(self) -> None:
        self.btn_start.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        self.ksu_switch.configure(state="normal")
        self.selinux_seg.configure(state="normal")
        self.accel_seg.configure(state="normal")
        self.gpu_seg.configure(state="normal")
        self.status_text.set(self.t("status_idle"))

    def _set_status(self, text: str) -> None:
        self.after(0, lambda: self.status_text.set(text))

    def stop_vm(self) -> None:
        self.stop_log_threads.set()
        self._stop_logcat()
        if self.vm_process and self.vm_process.poll() is None:
            console_log("[VM] Stopping QEMU...")
            self._set_status("Stopping VM...")
            if self.adb_exe.exists():
                try:
                    subprocess.run(
                        [str(self.adb_exe), "-s", "127.0.0.1:5555", "shell", "reboot -p"],
                        timeout=4, creationflags=_no_window_flags(),
                    )
                except Exception:
                    pass
            try:
                self.vm_process.terminate()
                self.vm_process.wait(timeout=5)
            except Exception:
                self.vm_process.kill()
        self._reset_vm_buttons()

    # ---------------- Root & Spoof ----------------
    def install_ksu_and_modules(self) -> None:
        def worker() -> None:
            if not self.adb_exe.exists() or not spoof_device.ensure_adb_connected(str(self.adb_exe), console_log):
                return
            self._set_status("Installing KernelSU Next & Modules...")
            apk_path = self.modules_dir / "KernelSU_Next.apk"
            if apk_path.exists():
                res = spoof_device.run_adb(str(self.adb_exe), ["install", "-r", str(apk_path)], timeout=60)
                console_log(f"[KSU] APK: {(res.stdout or res.stderr).strip()}")

            for zname in ["Portable_Stealth_KSU.zip", "ZygiskNext.zip", "PlayIntegrityFix.zip", "TrickyStore.zip"]:
                zpath = self.modules_dir / zname
                if not zpath.exists():
                    continue
                remote = f"/sdcard/Download/{zname}"
                spoof_device.run_adb(str(self.adb_exe), ["push", str(zpath), remote], timeout=45)
                flash = spoof_device.run_adb(
                    str(self.adb_exe), ["shell", f"su -c '/data/adb/ksud module install {remote}'"], timeout=45
                )
                console_log(
                    f"[KSU] {zname}: {'Flashed via ksud' if flash.returncode == 0 else 'Pushed to /sdcard/Download/'}"
                )
            self._set_status("KSU Next & Modules ready")

        threading.Thread(target=worker, daemon=True).start()

    def run_apply_spoof(self) -> None:
        profile = self.selected_device.get()
        def worker() -> None:
            self._set_status(f"Applying disguise: {profile}...")
            ok = spoof_device.apply_spoof(str(self.adb_exe), profile, console_log)
            self._set_status(f"Spoof active: {profile}" if ok else "Spoof failed (check CMD log)")
        threading.Thread(target=worker, daemon=True).start()

    def open_adb_shell(self) -> None:
        if not self.adb_exe.exists():
            return
        if sys.platform == "win32":
            subprocess.Popen(
                ["cmd.exe", "/k", str(self.adb_exe), "-s", "127.0.0.1:5555", "shell"],
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )

    def reset_data_img(self) -> None:
        if self.vm_process and self.vm_process.poll() is None:
            messagebox.showwarning("VM Running", "Tắt máy ảo trước khi xóa dữ liệu / Stop VM first.")
            return
        if not messagebox.askyesno("Reset Data", "Xóa toàn bộ app & dữ liệu Android trong hồ sơ hiện tại?"):
            return
        data_file = self.images_dir / "data.img"
        clean_tpl = self.images_dir / "data_clean.qcow2"
        try:
            if data_file.exists():
                data_file.unlink()
            if clean_tpl.exists():
                shutil.copy2(clean_tpl, data_file)
                console_log("[STORAGE] Reset data.img from pre-formatted ext4 template (data_clean.qcow2).")
            else:
                subprocess.run(
                    [str(self.qemu_img_exe), "create", "-f", "qcow2", str(data_file), "16G"],
                    check=True, capture_output=True, text=True, creationflags=_no_window_flags(),
                )
                console_log("[STORAGE] Created blank 16GB qcow2 data.img (initrd hook will format ext4 on boot).")
            prof_target = self.loaded_profile or self.active_profile.get()
            prof_file = self.profiles_dir / f"{prof_target}.qcow2"
            shutil.copy2(data_file, prof_file)
            self.status_text.set("Data wiped (16GB clean ext4)")
        except Exception as exc:
            messagebox.showerror("Reset Failed", str(exc))

    # ---------------- Quick Action Hub (5 1-Click Actions) ----------------
    def quick_fetch_gsf_whitelist(self) -> None:
        def worker() -> None:
            self._set_status("Reading GSF Android ID from gservices.db...")
            gsf_id = spoof_device.fetch_gsf_whitelist_id(str(self.adb_exe), console_log)
            if not gsf_id:
                self._set_status("GSF ID not found yet (see CMD log)")
                return
            self.after(0, lambda: self._set_windows_clipboard(gsf_id))
            console_log(f"[GSF] Copied to Windows Clipboard: {gsf_id}")
            webbrowser.open("https://www.google.com/android/uncertified")
            self._set_status(f"GSF ID copied ({gsf_id}) · Opened Google Uncertified page")

        threading.Thread(target=worker, daemon=True).start()

    def quick_randomize_identity(self) -> None:
        profile = self.selected_device.get()

        def worker() -> None:
            self._set_status("Generating fresh IMEI, Serial, MAC & Android ID...")
            res = spoof_device.randomize_device_identity(str(self.adb_exe), profile, console_log)
            if res:
                self._set_status(f"New Identity: Serial {res['serial']} · MAC {res['mac']}")
            else:
                self._set_status("Identity randomize failed (check VM running)")

        threading.Thread(target=worker, daemon=True).start()

    def quick_save_snapshot(self) -> None:
        if self.vm_process and self.vm_process.poll() is None:
            messagebox.showwarning("VM Running", "Tắt máy ảo trước khi lưu Điểm Khôi Phục / Stop VM before saving snapshot.")
            return
        if not self.qemu_img_exe.exists():
            messagebox.showerror("Missing Tool", f"Not found: {self.qemu_img_exe}")
            return
        data_img = self.images_dir / "data.img"
        if not data_img.exists():
            return
        try:
            subprocess.run(
                [str(self.qemu_img_exe), "snapshot", "-d", "portable_restore", str(data_img)],
                capture_output=True, text=True, creationflags=_no_window_flags(),
            )
            subprocess.run(
                [str(self.qemu_img_exe), "snapshot", "-c", "portable_restore", str(data_img)],
                check=True, capture_output=True, text=True, creationflags=_no_window_flags(),
            )
            prof_target = self.loaded_profile or self.active_profile.get()
            prof_file = self.profiles_dir / f"{prof_target}.qcow2"
            shutil.copy2(data_img, prof_file)
            console_log("[SNAPSHOT] Saved restore point 'portable_restore' inside data.img.")
            self.status_text.set("Snapshot saved: portable_restore")
        except Exception as exc:
            console_log(f"[SNAPSHOT] Save failed: {exc}")
            messagebox.showerror("Snapshot Save Failed", str(exc))

    def quick_restore_snapshot(self) -> None:
        if self.vm_process and self.vm_process.poll() is None:
            messagebox.showwarning("VM Running", "Tắt máy ảo trước khi khôi phục Điểm Lưu / Stop VM before restoring snapshot.")
            return
        if not self.qemu_img_exe.exists():
            messagebox.showerror("Missing Tool", f"Not found: {self.qemu_img_exe}")
            return
        data_img = self.images_dir / "data.img"
        if not data_img.exists():
            return
        try:
            lst = subprocess.run(
                [str(self.qemu_img_exe), "snapshot", "-l", str(data_img)],
                check=True, capture_output=True, text=True, creationflags=_no_window_flags(),
            )
            if "portable_restore" not in (lst.stdout or ""):
                messagebox.showinfo("No Snapshot", "Chưa có Điểm Khôi Phục nào được lưu / No saved snapshot found yet.")
                return
            subprocess.run(
                [str(self.qemu_img_exe), "snapshot", "-a", "portable_restore", str(data_img)],
                check=True, capture_output=True, text=True, creationflags=_no_window_flags(),
            )
            prof_target = self.loaded_profile or self.active_profile.get()
            prof_file = self.profiles_dir / f"{prof_target}.qcow2"
            shutil.copy2(data_img, prof_file)
            console_log("[SNAPSHOT] Restored data.img to snapshot 'portable_restore'.")
            self.status_text.set("Snapshot restored: portable_restore")
        except Exception as exc:
            console_log(f"[SNAPSHOT] Restore failed: {exc}")
            messagebox.showerror("Snapshot Restore Failed", str(exc))

    def quick_toggle_wifi_lan(self) -> None:
        new_state = not self.wifi_sim_enabled.get()
        self.wifi_sim_enabled.set(new_state)
        self._save_config()
        self.btn_wifi_toggle.configure(text=self.t("btn_wifi_on") if new_state else self.t("btn_wifi_off"))

        def worker() -> None:
            if self.vm_process and self.vm_process.poll() is None:
                ok = spoof_device.toggle_wifi_lan_simulation(str(self.adb_exe), new_state, console_log)
                if ok:
                    self._set_status("Network: Wi-Fi (Home_WiFi_5G)" if new_state else "Network: Wired LAN (eth0)")
            else:
                self._set_status("Saved network preference: " + ("Wi-Fi wlan0" if new_state else "LAN eth0"))

        threading.Thread(target=worker, daemon=True).start()

    def quick_trim_ram(self) -> None:
        def worker() -> None:
            self._set_status("Trimming VM page caches & freeing RAM for Windows 11...")
            ok = spoof_device.trim_vm_ram(str(self.adb_exe), console_log)
            self._set_status("VM RAM trimmed & reclaimed" if ok else "RAM trim skipped (VM offline)")

        threading.Thread(target=worker, daemon=True).start()

    # ---------------- Waydroid Multi-Window (scrcpy) & Desktop Shortcuts ----------------
    def refresh_installed_apps(self) -> None:
        def worker() -> None:
            if not self.adb_exe.exists() or not spoof_device.ensure_adb_connected(str(self.adb_exe), console_log):
                return
            res = spoof_device.run_adb(str(self.adb_exe), ["shell", "pm list packages -3"], timeout=15)
            pkgs = [line.replace("package:", "").strip() for line in (res.stdout or "").splitlines() if line.strip()]
            # Include key system apps useful as standalone windows
            pkgs += ["com.android.settings", "com.android.documentsui", "com.android.vending"]
            self.installed_packages = sorted(set(pkgs))
            if self.installed_packages and not self.selected_package.get():
                self.selected_package.set(self.installed_packages[0])
            self.after(0, self._render_app_list)

        threading.Thread(target=worker, daemon=True).start()

    def _render_app_list(self) -> None:
        for child in self.apps_scroll.winfo_children():
            child.destroy()

        q = self.app_filter_var.get().strip().lower()
        filtered = [p for p in self.installed_packages if not q or q in p.lower()]
        if not filtered:
            ctk.CTkLabel(
                self.apps_scroll,
                text="Chưa có dữ liệu app — hãy bật VM và bấm Tải Danh Sách App / Start VM & Refresh.",
                text_color="#94A3B8",
            ).pack(pady=24)
            return

        for pkg in filtered:
            rb = ctk.CTkRadioButton(
                self.apps_scroll,
                text=pkg,
                variable=self.selected_package,
                value=pkg,
                font=ctk.CTkFont(family="Consolas", size=12),
            )
            rb.pack(anchor="w", padx=10, pady=4)

    def launch_selected_app_window(self) -> None:
        pkg = self.selected_package.get().strip()
        if not pkg:
            messagebox.showinfo("Select App", "Hãy chọn 1 app trong danh sách trước.")
            return
        if not self.scrcpy_exe.exists():
            messagebox.showerror("Missing scrcpy", f"Không tìm thấy {self.scrcpy_exe}")
            return

        env = os.environ.copy()
        env["ADB"] = str(self.adb_exe)
        cmd = [
            str(self.scrcpy_exe),
            "-s", "127.0.0.1:5555",
            "--new-display=1280x720",
            f"--start-app={pkg}",
            f"--window-title={pkg}",
        ]
        console_log(f"[WAYDROID-MODE] Launching standalone window: {' '.join(cmd)}")
        subprocess.Popen(cmd, cwd=str(self.scrcpy_exe.parent), env=env)

    def create_desktop_shortcut(self) -> None:
        pkg = self.selected_package.get().strip()
        if not pkg:
            messagebox.showinfo("Select App", "Hãy chọn 1 app trong danh sách trước.")
            return

        def worker() -> None:
            icon_out = self.assets_dir / f"shortcut_{re.sub(r'[^A-Za-z0-9_.-]', '_', pkg)}.ico"
            if not self._extract_apk_icon_to_ico(pkg, icon_out):
                fallback_ico = self.assets_dir / "app.ico"
                if fallback_ico.exists():
                    icon_out = fallback_ico

            if sys.platform == "win32":
                desktop = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Desktop"
                lnk_path = desktop / f"{pkg.split('.')[-1].title()} (Android).lnk"
                args = f'-s 127.0.0.1:5555 --new-display=1280x720 --start-app={pkg} --window-title="{pkg}"'
                ps_script = (
                    f'$ws = New-Object -ComObject WScript.Shell; '
                    f'$sc = $ws.CreateShortcut("{lnk_path}"); '
                    f'$sc.TargetPath = "{self.scrcpy_exe}"; '
                    f'$sc.Arguments = \'{args}\'; '
                    f'$sc.WorkingDirectory = "{self.scrcpy_exe.parent}"; '
                    f'$sc.IconLocation = "{icon_out}"; '
                    f'$sc.Save()'
                )
                subprocess.run(
                    ["powershell", "-NoProfile", "-Command", ps_script],
                    capture_output=True, text=True, creationflags=_no_window_flags(),
                )
                console_log(f"[SHORTCUT] Created Windows Desktop shortcut: {lnk_path}")
                self._set_status(f"Desktop shortcut created: {lnk_path.name}")

        threading.Thread(target=worker, daemon=True).start()

    def _extract_apk_icon_to_ico(self, pkg: str, out_ico: Path) -> bool:
        """Pull APK via ADB and convert largest launcher PNG inside APK to .ico via Pillow."""
        try:
            path_res = spoof_device.run_adb(str(self.adb_exe), ["shell", f"pm path {pkg}"], timeout=10)
            apk_remote = ""
            for line in (path_res.stdout or "").splitlines():
                if line.startswith("package:") and line.endswith("base.apk"):
                    apk_remote = line.replace("package:", "").strip()
                    break
            if not apk_remote and path_res.stdout:
                apk_remote = path_res.stdout.splitlines()[0].replace("package:", "").strip()
            if not apk_remote:
                return False

            with tempfile.TemporaryDirectory() as tmp:
                local_apk = Path(tmp) / "app.apk"
                spoof_device.run_adb(str(self.adb_exe), ["pull", apk_remote, str(local_apk)], timeout=30)
                if not local_apk.exists():
                    return False
                with zipfile.ZipFile(local_apk, "r") as zf:
                    pngs = [
                        n for n in zf.namelist()
                        if n.endswith(".png") and ("ic_launcher" in n or "app_icon" in n)
                    ]
                    if not pngs:
                        return False
                    best = max(pngs, key=lambda n: zf.getinfo(n).file_size)
                    extracted_png = Path(tmp) / "icon.png"
                    extracted_png.write_bytes(zf.read(best))
                    img = Image.open(extracted_png).convert("RGBA")
                    img.save(out_ico, format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128)])
                    return out_ico.exists()
        except Exception as exc:
            console_log(f"[ICON] Fallback to default icon ({exc})")
            return False

    # ---------------- Drag & Drop, 2-Way Clipboard, Keybox & Rescue ----------------
    def _parse_drop_paths(self, raw: str) -> List[Path]:
        # Handle Windows Tk curly-braced paths containing spaces
        items = re.findall(r"\{([^}]+)\}|(\S+)", raw)
        return [Path(a or b) for a, b in items if (a or b)]

    def _on_file_drop(self, event) -> None:
        paths = self._parse_drop_paths(event.data)
        self._process_dropped_files(paths)

    def browse_drop_file(self) -> None:
        chosen = filedialog.askopenfilenames(
            title="Select APK, KSU Module ZIP, or Media",
            filetypes=[("Supported Files", "*.apk *.zip *.jpg *.jpeg *.png *.webp *.mp4 *.mov *.pdf"), ("All", "*.*")],
        )
        if chosen:
            self._process_dropped_files([Path(p) for p in chosen])

    def _process_dropped_files(self, paths: List[Path]) -> None:
        def worker() -> None:
            if not self.adb_exe.exists() or not spoof_device.ensure_adb_connected(str(self.adb_exe), console_log):
                return
            for p in paths:
                if not p.exists():
                    continue
                ext = p.suffix.lower()
                if ext == ".apk":
                    console_log(f"[DROP] Installing APK: {p.name}")
                    res = spoof_device.run_adb(str(self.adb_exe), ["install", "-r", str(p)], timeout=90)
                    console_log(f"[DROP] APK Result: {(res.stdout or res.stderr).strip()}")
                elif ext == ".zip":
                    remote = f"/sdcard/Download/{p.name}"
                    console_log(f"[DROP] Pushing KSU module ZIP -> {remote}")
                    spoof_device.run_adb(str(self.adb_exe), ["push", str(p), remote], timeout=60)
                    res = spoof_device.run_adb(
                        str(self.adb_exe), ["shell", f"su -c '/data/adb/ksud module install {remote}'"], timeout=60
                    )
                    console_log(
                        f"[DROP] Module flash: {'SUCCESS' if res.returncode == 0 else 'Saved to /sdcard/Download/'}"
                    )
                else:
                    remote = f"/sdcard/Download/{p.name}"
                    console_log(f"[DROP] Copying media -> {remote}")
                    spoof_device.run_adb(str(self.adb_exe), ["push", str(p), remote], timeout=90)
                    spoof_device.run_adb(
                        str(self.adb_exe),
                        ["shell", f"am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d file://{remote}"],
                    )
            self._set_status(f"Processed {len(paths)} file(s) via ADB")

        threading.Thread(target=worker, daemon=True).start()

    def push_clipboard_to_android(self) -> None:
        try:
            win_text = self.clipboard_get()
        except Exception:
            return
        if not win_text:
            return
        escaped = win_text.replace("'", "'\\''")
        threading.Thread(
            target=lambda: spoof_device.run_adb(
                str(self.adb_exe), ["shell", f"cmd clipboard set-text '{escaped}'"], timeout=5
            ),
            daemon=True,
        ).start()
        console_log("[CLIPBOARD] Sent Windows clipboard text -> Android")

    def pull_clipboard_from_android(self) -> None:
        def worker() -> None:
            res = spoof_device.run_adb(str(self.adb_exe), ["shell", "cmd clipboard get-text"], timeout=5)
            txt = (res.stdout or "").strip()
            if txt and "error" not in txt.lower():
                self.after(0, lambda: self._set_windows_clipboard(txt))
                console_log("[CLIPBOARD] Pulled Android clipboard -> Windows")

        threading.Thread(target=worker, daemon=True).start()

    def _set_windows_clipboard(self, txt: str) -> None:
        self.last_win_clip = txt
        self.clipboard_clear()
        self.clipboard_append(txt)

    def _clipboard_poll_tick(self) -> None:
        if (
            self.auto_clip_var.get()
            and self.adb_connected
            and self.vm_process
            and self.vm_process.poll() is None
        ):
            try:
                cur_win = self.clipboard_get()
            except Exception:
                cur_win = ""
            if cur_win and cur_win != self.last_win_clip and len(cur_win) < 4000:
                self.last_win_clip = cur_win
                self.push_clipboard_to_android()
        self.after(3000, self._clipboard_poll_tick)

    def run_keybox_safety_1click(self) -> None:
        chosen = filedialog.askopenfilename(
            title="Chọn keybox.xml (hoặc Cancel để kiểm tra cấu hình hiện tại)",
            filetypes=[("Keybox XML", "*.xml"), ("All files", "*.*")],
        )
        kb_path = Path(chosen) if chosen else None
        profile = self.selected_device.get()

        def worker() -> None:
            self._set_status("Running 1-Click Keybox & Safety Audit...")
            ok = spoof_device.inject_keybox_and_check_safety(str(self.adb_exe), kb_path, profile, console_log)
            self._set_status("Safety check completed (see CMD console)" if ok else "Safety check failed")

        threading.Thread(target=worker, daemon=True).start()

    def run_bootloop_safe_mode(self) -> None:
        def worker() -> None:
            self._set_status("Safe Mode: Disabling KSU modules...")
            ok = spoof_device.disable_ksu_modules_safe_mode(str(self.adb_exe), console_log)
            if not ok:
                # Switch to Clean Stock + Permissive SELinux so next boot recovers cleanly
                def _apply_safe_fallback() -> None:
                    self.ksu_enabled.set(False)
                    self._on_ksu_toggle()
                    self.selinux_mode.set("permissive")
                    self.selinux_seg.set("Permissive")
                    self._save_config()

                self.after(0, _apply_safe_fallback)
                self._set_status("Safe Mode: Switched to Clean Stock + SELinux Permissive")
            else:
                self._set_status("All KSU modules disabled · Rebooting safely")

        threading.Thread(target=worker, daemon=True).start()

    def _on_close(self) -> None:
        self._save_config()
        self.stop_vm()
        self.destroy()


def main() -> int:
    _disable_windows_console_quick_edit()
    try:
        app = PortableAndroidLauncher()
        app.mainloop()
        return 0
    except Exception:
        console_log("================ FATAL LAUNCHER ERROR ================")
        traceback.print_exc()
        if sys.platform == "win32":
            input("\nPress Enter to close this console window...")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
