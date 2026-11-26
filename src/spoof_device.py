#!/usr/bin/env python3
"""
ADB Device Spoofing, Keybox Injection & Boot-Loop Safe Mode Engine
Supports dual-kernel detection (KernelSU Next resetprop vs Stock runtime properties).
"""
from __future__ import annotations

import argparse
import json
import random
import re
import secrets
import subprocess
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional


ADB_TARGET = "127.0.0.1:5555"

DEVICE_PROFILES: Dict[str, Dict[str, str]] = {
    "Google Pixel 8 Pro": {
        "key": "pixel8pro",
        "brand": "google",
        "manufacturer": "Google",
        "model": "Pixel 8 Pro",
        "device": "husky",
        "product": "husky",
        "board": "husky",
        "platform": "zuma",
        "hardware": "husky",
        "fingerprint": "google/husky/husky:14/AP2A.240905.003/12231197:user/release-keys",
        "description": "husky-user 14 AP2A.240905.003 12231197 release-keys",
        "security_patch": "2024-09-05",
        "build_id": "AP2A.240905.003",
        "incremental": "12231197",
        "gl_renderer": "Mali-G715",
        "gl_vendor": "ARM",
        "first_api_level": "34",
    },
    "Xiaomi 14": {
        "key": "xiaomi14",
        "brand": "Xiaomi",
        "manufacturer": "Xiaomi",
        "model": "23127PN0CG",
        "device": "houji",
        "product": "houji_global",
        "board": "pineapple",
        "platform": "pineapple",
        "hardware": "qcom",
        "fingerprint": "Xiaomi/houji_global/houji:14/UKQ1.231003.002/V816.0.14.0.UNCMIXM:user/release-keys",
        "description": "houji_global-user 14 UKQ1.231003.002 V816.0.14.0.UNCMIXM release-keys",
        "security_patch": "2024-08-01",
        "build_id": "UKQ1.231003.002",
        "incremental": "V816.0.14.0.UNCMIXM",
        "gl_renderer": "Adreno (TM) 750",
        "gl_vendor": "Qualcomm",
        "first_api_level": "34",
    },
    "Samsung Galaxy S24 Ultra": {
        "key": "s24ultra",
        "brand": "samsung",
        "manufacturer": "samsung",
        "model": "SM-S928B",
        "device": "e3q",
        "product": "e3qxxx",
        "board": "pineapple",
        "platform": "pineapple",
        "hardware": "qcom",
        "fingerprint": "samsung/e3qxxx/e3q:14/UP1A.231005.007/S928BXXS3AXH7:user/release-keys",
        "description": "e3qxxx-user 14 UP1A.231005.007 S928BXXS3AXH7 release-keys",
        "security_patch": "2024-08-01",
        "build_id": "UP1A.231005.007",
        "incremental": "S928BXXS3AXH7",
        "gl_renderer": "Adreno (TM) 750",
        "gl_vendor": "Qualcomm",
        "first_api_level": "34",
    },
    "ROG Phone 8": {
        "key": "rog8",
        "brand": "asus",
        "manufacturer": "ASUSTeK COMPUTER INC.",
        "model": "ASUS_AI2401",
        "device": "ASUS_AI2401",
        "product": "WW_AI2401",
        "board": "pineapple",
        "platform": "pineapple",
        "hardware": "qcom",
        "fingerprint": "asus/WW_AI2401/ASUS_AI2401:14/UKQ1.230924.001/34.1420.1420.415:user/release-keys",
        "description": "WW_AI2401-user 14 UKQ1.230924.001 34.1420.1420.415 release-keys",
        "security_patch": "2024-08-05",
        "build_id": "UKQ1.230924.001",
        "incremental": "34.1420.1420.415",
        "gl_renderer": "Adreno (TM) 750",
        "gl_vendor": "Qualcomm",
        "first_api_level": "34",
    },
}

EMULATOR_TRACE_PROPS_TO_DELETE: List[str] = [
    "ro.kernel.qemu",
    "ro.kernel.qemu.gles",
    "ro.kernel.android.qemud",
    "ro.boot.qemu",
    "qemu.hw.mainkeys",
    "qemu.sf.fake_camera",
    "qemu.sf.lcd_density",
    "init.svc.qemu-props",
    "ro.lineage.version",
    "ro.lineage.display.version",
    "ro.lineage.build.version",
    "ro.lineage.device",
    "ro.modversion",
    "ro.bliss.version",
    "ro.bliss.display.version",
    "ro.bliss.device",
]


def _no_window_flags() -> int:
    if sys.platform == "win32":
        return getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return 0


def run_adb(adb_exe: str, args: List[str], timeout: int = 20) -> subprocess.CompletedProcess:
    cmd = [adb_exe, "-s", ADB_TARGET] + args
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        creationflags=_no_window_flags(),
    )


def ensure_adb_connected(adb_exe: str, log_fn: Callable[[str], None]) -> bool:
    res = subprocess.run(
        [adb_exe, "connect", ADB_TARGET],
        capture_output=True,
        text=True,
        timeout=15,
        creationflags=_no_window_flags(),
    )
    out = (res.stdout or "").strip()
    err = (res.stderr or "").strip()
    if out:
        log_fn(f"[ADB] {out}")
    if err:
        log_fn(f"[ADB] {err}")

    state = run_adb(adb_exe, ["get-state"])
    if state.returncode != 0 or "device" not in (state.stdout or ""):
        log_fn("[SPOOF] Android VM is not reachable on 127.0.0.1:5555. Wait for boot to finish.")
        return False
    return True


def detect_kernel_mode(adb_exe: str, log_fn: Callable[[str], None]) -> Dict[str, Optional[str]]:
    uname_res = run_adb(adb_exe, ["shell", "uname -r"])
    kernel_rel = (uname_res.stdout or "").strip()

    su_check = run_adb(adb_exe, ["shell", "su -c 'id' 2>/dev/null"])
    has_root = su_check.returncode == 0 and "uid=0" in (su_check.stdout or "")

    resetprop_bin = None
    if has_root:
        for candidate in [
            "/data/adb/ksu/bin/resetprop",
            "/data/adb/ksud",
            "/system/bin/resetprop",
            "resetprop",
        ]:
            chk = run_adb(adb_exe, ["shell", f"su -c 'command -v {candidate} || test -x {candidate}'"])
            if chk.returncode == 0:
                resetprop_bin = "/data/adb/ksu/bin/resetprop" if candidate == "/data/adb/ksud" else candidate
                break

    mode = "ksunext" if has_root else "stock"
    log_fn(f"[SPOOF] Kernel: {kernel_rel} | Mode: {mode.upper()} | resetprop: {resetprop_bin or 'N/A'}")
    return {
        "mode": mode,
        "kernel_release": kernel_rel,
        "resetprop": resetprop_bin,
    }


def apply_spoof(
    adb_exe: str,
    profile_name: str,
    log_fn: Callable[[str], None] = print,
) -> bool:
    if profile_name not in DEVICE_PROFILES:
        log_fn(f"[SPOOF] Unknown profile: {profile_name}")
        return False

    profile = DEVICE_PROFILES[profile_name]
    log_fn(f"[SPOOF] Disguising VM as -> {profile_name} ({profile['model']})")

    if not ensure_adb_connected(adb_exe, log_fn):
        return False

    env_info = detect_kernel_mode(adb_exe, log_fn)

    prop_updates: Dict[str, str] = {
        "ro.product.brand": profile["brand"],
        "ro.product.system.brand": profile["brand"],
        "ro.product.vendor.brand": profile["brand"],
        "ro.product.odm.brand": profile["brand"],
        "ro.product.product.brand": profile["brand"],
        "ro.product.manufacturer": profile["manufacturer"],
        "ro.product.system.manufacturer": profile["manufacturer"],
        "ro.product.vendor.manufacturer": profile["manufacturer"],
        "ro.product.model": profile["model"],
        "ro.product.system.model": profile["model"],
        "ro.product.vendor.model": profile["model"],
        "ro.product.odm.model": profile["model"],
        "ro.product.device": profile["device"],
        "ro.product.system.device": profile["device"],
        "ro.product.vendor.device": profile["device"],
        "ro.product.name": profile["product"],
        "ro.product.system.name": profile["product"],
        "ro.product.board": profile["board"],
        "ro.board.platform": profile["platform"],
        "ro.hardware": profile["hardware"],
        "ro.boot.hardware": profile["hardware"],
        "ro.build.fingerprint": profile["fingerprint"],
        "ro.system.build.fingerprint": profile["fingerprint"],
        "ro.vendor.build.fingerprint": profile["fingerprint"],
        "ro.odm.build.fingerprint": profile["fingerprint"],
        "ro.bootimage.build.fingerprint": profile["fingerprint"],
        "ro.build.description": profile["description"],
        "ro.build.id": profile["build_id"],
        "ro.build.version.incremental": profile["incremental"],
        "ro.build.version.security_patch": profile["security_patch"],
        "ro.vendor.build.security_patch": profile["security_patch"],
        "ro.build.type": "user",
        "ro.build.tags": "release-keys",
        "ro.debuggable": "0",
        "ro.secure": "1",
        "ro.boot.verifiedbootstate": "green",
        "ro.boot.flash.locked": "1",
        "ro.boot.vbmeta.device_state": "locked",
        "ro.product.first_api_level": profile["first_api_level"],
        "ro.kernel.qemu": "0",
        "ro.boot.qemu": "0",
        "ro.hardware.egl": "mesa",
        "ro.hwui.use_vulkan": "false",
        "debug.hwui.renderer": "opengl",
        "persist.sys.ui.hw": "1",
    }

    if env_info["mode"] == "ksunext" and env_info["resetprop"]:
        rp = env_info["resetprop"]
        log_fn("[SPOOF] KernelSU Next active: scrubbing emulator/Bliss/Lineage traces via resetprop...")
        cmds: List[str] = []
        for dead_prop in EMULATOR_TRACE_PROPS_TO_DELETE:
            cmds.append(f"{rp} --delete {dead_prop} 2>/dev/null || true")

        for k, v in prop_updates.items():
            safe_v = v.replace('"', '\\"')
            cmds.append(f'{rp} -n "{k}" "{safe_v}"')

        pif_payload = {
            "MANUFACTURER": profile["manufacturer"],
            "MODEL": profile["model"],
            "BRAND": profile["brand"],
            "PRODUCT": profile["product"],
            "DEVICE": profile["device"],
            "FINGERPRINT": profile["fingerprint"],
            "SECURITY_PATCH": profile["security_patch"],
            "FIRST_API_LEVEL": profile["first_api_level"],
            "ID": profile["build_id"],
            "INCREMENTAL": profile["incremental"],
            "TYPE": "user",
            "TAGS": "release-keys",
        }
        pif_json_str = json.dumps(pif_payload, separators=(",", ":")).replace("'", "'\\''")
        cmds.append(
            f"if [ -d /data/adb/modules/playintegrityfix ]; then echo '{pif_json_str}' > /data/adb/modules/playintegrityfix/pif.json; fi"
        )
        cmds.append(f"echo '{pif_json_str}' > /data/adb/pif.json")
        cmds.append(
            "mkdir -p /data/adb/tricky_store && printf 'com.google.android.gms\\ncom.google.android.gsf\\ncom.android.vending\\n' > /data/adb/tricky_store/target.txt"
        )

        batched = " && ".join(cmds)
        res = run_adb(adb_exe, ["shell", f"su -c '{batched}'"], timeout=45)
        if res.returncode != 0:
            log_fn(f"[SPOOF] resetprop batch returned code {res.returncode}: {res.stderr.strip()}")
        else:
            log_fn("[SPOOF] resetprop + pif.json + TrickyStore target.txt applied.")
    else:
        log_fn("[SPOOF] Stock Kernel active (no root): applying runtime ADB settings & non-ro props...")
        runtime_cmds = [
            f"settings put global device_name '{profile['manufacturer']} {profile['model']}'",
            f"settings put secure bluetooth_name '{profile['model']}'",
            "setprop debug.hwui.renderer opengl",
            "setprop ro.hwui.use_vulkan false",
            "setprop persist.sys.ui.hw 1",
        ]
        for rc in runtime_cmds:
            run_adb(adb_exe, ["shell", rc])
        log_fn("[SPOOF] Applied runtime device_name & OpenGL props (deep fingerprint spoofing needs KSU Next ON).")

    verify_model = (run_adb(adb_exe, ["shell", "getprop ro.product.model"]).stdout or "").strip()
    verify_fp = (run_adb(adb_exe, ["shell", "getprop ro.build.fingerprint"]).stdout or "").strip()
    verify_qemu = (run_adb(adb_exe, ["shell", "getprop ro.kernel.qemu"]).stdout or "").strip()
    log_fn(f"[VERIFY] ro.product.model     = {verify_model}")
    log_fn(f"[VERIFY] ro.build.fingerprint = {verify_fp}")
    log_fn(f"[VERIFY] ro.kernel.qemu       = {verify_qemu or '<deleted>'}")
    return True


def inject_keybox_and_check_safety(
    adb_exe: str,
    keybox_path: Optional[Path],
    profile_name: str,
    log_fn: Callable[[str], None] = print,
) -> bool:
    """1-Click Keybox injection + TrickyStore/PIF/Zygisk safety verification."""
    if not ensure_adb_connected(adb_exe, log_fn):
        return False

    env_info = detect_kernel_mode(adb_exe, log_fn)
    if env_info["mode"] != "ksunext":
        log_fn("[SAFETY] Stock clean kernel detected (no root). Running basic safety audit...")
        boot_state = (run_adb(adb_exe, ["shell", "getprop ro.boot.verifiedbootstate"]).stdout or "").strip()
        log_fn(f"[SAFETY] VerifiedBoot={boot_state or 'unknown'} | Root Binary=ABSENT (Clean Stock)")
        return True

    if keybox_path and keybox_path.exists():
        log_fn(f"[KEYBOX] Pushing {keybox_path.name} -> /sdcard/Download/keybox_tmp.xml...")
        run_adb(adb_exe, ["push", str(keybox_path), "/sdcard/Download/keybox_tmp.xml"])
        res = run_adb(
            adb_exe,
            [
                "shell",
                "su -c 'mkdir -p /data/adb/tricky_store && cp -f /sdcard/Download/keybox_tmp.xml /data/adb/tricky_store/keybox.xml && chmod 600 /data/adb/tricky_store/keybox.xml && rm -f /sdcard/Download/keybox_tmp.xml'",
            ],
        )
        if res.returncode == 0:
            log_fn("[KEYBOX] Installed keybox.xml into /data/adb/tricky_store/keybox.xml")
        else:
            log_fn(f"[KEYBOX] Error installing keybox.xml: {res.stderr.strip()}")

    # Refresh PIF + TrickyStore targets
    apply_spoof(adb_exe, profile_name, log_fn)

    # Check active modules & status
    mods_out = (
        run_adb(adb_exe, ["shell", "su -c 'ls -1 /data/adb/modules 2>/dev/null'"]).stdout or ""
    ).strip()
    kb_chk = run_adb(adb_exe, ["shell", "su -c 'test -s /data/adb/tricky_store/keybox.xml && echo PRESENT || echo MISSING'"])
    kb_status = (kb_chk.stdout or "").strip()
    log_fn(f"[SAFETY] Installed KSU Modules: {', '.join(mods_out.splitlines()) or 'None'}")
    log_fn(f"[SAFETY] TrickyStore keybox.xml : {kb_status}")
    log_fn(f"[SAFETY] TrickyStore target.txt : Configured for GMS / GSF / Play Store")
    return True


def ensure_selinux_boot_health(
    adb_exe: str,
    target_mode: str,
    log_fn: Callable[[str], None] = print,
) -> bool:
    """Run restorecon -R /data, apply KernelSU Next sepolicy patches, and transition SELinux post-boot."""
    if not ensure_adb_connected(adb_exe, log_fn):
        return False

    desired = "enforcing" if target_mode.lower() == "enforcing" else "permissive"
    env_info = detect_kernel_mode(adb_exe, log_fn)

    if env_info["mode"] == "ksunext":
        log_fn(f"[SELINUX] Stage-1 booted Permissive -> running restorecon & KSU Next sepolicy patches (target: {desired})...")
        sepolicy_cmds = [
            "restorecon -R /data/adb /data/local /data/data /data/system /data/misc 2>/dev/null || restorecon -R /data",
            "if [ -x /data/adb/ksud ]; then "
            "/data/adb/ksud sepolicy patch "
            "'allow hal_graphics_composer_default * * *' "
            "'allow surfaceflinger * * *' "
            "'allow untrusted_app hal_graphics_allocator_default * *' "
            "'allow su * * *' 2>/dev/null || true; "
            "fi",
            "setenforce 1" if desired == "enforcing" else "setenforce 0",
        ]
        res = run_adb(adb_exe, ["shell", f"su -c '{' && '.join(sepolicy_cmds)}'"], timeout=45)
        if res.returncode != 0:
            log_fn(f"[SELINUX] Note during restorecon/sepolicy: {res.stderr.strip()}")
    else:
        log_fn(f"[SELINUX] Stock kernel active (stage-1 Permissive -> target: {desired})...")
        switched_adb_root = False
        if desired == "enforcing":
            root_res = run_adb(adb_exe, ["root"], timeout=10)
            root_out = ((root_res.stdout or "") + " " + (root_res.stderr or "")).lower()
            if "adbd is already running as root" in root_out or "restarting adbd as root" in root_out:
                switched_adb_root = True
                import time as _t
                _t.sleep(1.5)
                ensure_adb_connected(adb_exe, log_fn)

        id_out = (run_adb(adb_exe, ["shell", "id"], timeout=10).stdout or "").lower()
        if "uid=0" in id_out:
            run_adb(
                adb_exe,
                [
                    "shell",
                    "restorecon -R /data/adb /data/local /data/data /data/system /data/misc 2>/dev/null || restorecon -R /data/local/tmp 2>/dev/null || true",
                ],
                timeout=35,
            )
            if desired == "enforcing":
                run_adb(adb_exe, ["shell", "setenforce 1 2>/dev/null || true"], timeout=10)
        else:
            run_adb(adb_exe, ["shell", "restorecon -R /data/local/tmp 2>/dev/null || true"], timeout=15)
            if desired == "enforcing":
                run_adb(adb_exe, ["shell", "setenforce 1 2>/dev/null || true"], timeout=10)

        if switched_adb_root:
            run_adb(adb_exe, ["unroot"], timeout=10)
            import time as _t
            _t.sleep(1.0)
            ensure_adb_connected(adb_exe, log_fn)

    cur = (run_adb(adb_exe, ["shell", "getenforce"]).stdout or "").strip()
    log_fn(f"[SELINUX] Active kernel enforcement (getenforce): {cur or desired}")
    return True


def disable_ksu_modules_safe_mode(
    adb_exe: str,
    log_fn: Callable[[str], None] = print,
) -> bool:
    """Disable all KernelSU Next modules via ADB to recover from module boot-loops."""
    if not ensure_adb_connected(adb_exe, log_fn):
        log_fn("[SAFE MODE] ADB unreachable right now. Switch Kernel Mode to 'Stock Clean' to boot safely.")
        return False

    cmd = (
        "su -c 'for d in /data/adb/modules/*; do "
        "if [ -d \"$d\" ]; then touch \"$d/disable\"; echo \"Disabled: $d\"; fi; "
        "done; sync'"
    )
    res = run_adb(adb_exe, ["shell", cmd], timeout=20)
    if res.returncode == 0:
        log_fn("[SAFE MODE] All KSU Next modules marked 'disable':")
        for line in (res.stdout or "").splitlines():
            log_fn(f"  {line}")
        log_fn("[SAFE MODE] Rebooting VM cleanly...")
        run_adb(adb_exe, ["shell", "reboot"])
        return True

    log_fn(f"[SAFE MODE] Could not execute su module disable: {res.stderr.strip()}")
    return False


def _generate_luhn_imei() -> str:
    tac = random.choice(["35824005", "35391211", "86485204", "35512909"])
    body = tac + "".join(str(random.randint(0, 9)) for _ in range(6))
    digits = [int(d) for d in body]
    total = 0
    for idx, val in enumerate(digits):
        if idx % 2 == 1:
            doubled = val * 2
            total += doubled - 9 if doubled > 9 else doubled
        else:
            total += val
    check = (10 - (total % 10)) % 10
    return f"{body}{check}"


def _generate_mac() -> str:
    first = random.choice([0x02, 0x06, 0x0A, 0x0E])
    rest = [random.randint(0, 255) for _ in range(5)]
    return ":".join(f"{b:02x}" for b in [first] + rest)


def fetch_gsf_whitelist_id(
    adb_exe: str,
    log_fn: Callable[[str], None] = print,
) -> Optional[str]:
    """Read Google Services Framework android_id from gservices.db (or content provider fallback)."""
    if not ensure_adb_connected(adb_exe, log_fn):
        return None

    sql_cmd = (
        "su -c 'sqlite3 /data/data/com.google.android.gsf/databases/gservices.db "
        "\"select value from main where name = \\\"android_id\\\";\" 2>/dev/null'"
    )
    res = run_adb(adb_exe, ["shell", sql_cmd], timeout=15)
    raw_out = (res.stdout or "").strip()
    m = re.search(r"\b(\d{15,21})\b", raw_out)
    if m:
        gsf_id = m.group(1)
        log_fn(f"[GSF] Read android_id from gservices.db: {gsf_id}")
        return gsf_id

    # Fallback via Android content query if sqlite3 binary is absent
    cp_cmd = (
        "content query --uri content://com.google.android.gsf.gservices "
        "--projection value --where \"name='android_id'\""
    )
    res2 = run_adb(adb_exe, ["shell", cp_cmd], timeout=15)
    m2 = re.search(r"(\d{15,21})", (res2.stdout or ""))
    if m2:
        gsf_id = m2.group(1)
        log_fn(f"[GSF] Read android_id via content provider: {gsf_id}")
        return gsf_id

    # Fallback: read raw gservices.db strings if sqlite3 is missing
    raw_scan = run_adb(
        adb_exe,
        ["shell", "su -c 'strings /data/data/com.google.android.gsf/databases/gservices.db 2>/dev/null | grep -A1 android_id'"],
        timeout=15,
    )
    m3 = re.search(r"\b(\d{15,21})\b", (raw_scan.stdout or ""))
    if m3:
        gsf_id = m3.group(1)
        log_fn(f"[GSF] Extracted android_id from gservices.db: {gsf_id}")
        return gsf_id

    log_fn("[GSF] Could not find GSF android_id yet (sign in or open Google Play once, then retry).")
    return None


def randomize_device_identity(
    adb_exe: str,
    profile_name: str,
    log_fn: Callable[[str], None] = print,
) -> Optional[Dict[str, str]]:
    """Randomize IMEI, Serial Number, Wi-Fi MAC, and Android ID live via ADB."""
    if not ensure_adb_connected(adb_exe, log_fn):
        return None

    new_imei = _generate_luhn_imei()
    new_serial = "".join(random.choices("ABCDEFGHJKLMNPQRSTUVWXYZ0123456789", k=12))
    new_mac = _generate_mac()
    new_android_id = secrets.token_hex(8)

    env_info = detect_kernel_mode(adb_exe, log_fn)
    cmds = [
        f"settings put secure android_id {new_android_id}",
        f"settings put global device_name '{profile_name}-{new_serial[:4]}'",
    ]

    if env_info["mode"] == "ksunext" and env_info["resetprop"]:
        rp = env_info["resetprop"]
        prop_map = {
            "ro.serialno": new_serial,
            "ro.boot.serialno": new_serial,
            "persist.radio.imei": new_imei,
            "ro.ril.oem.imei": new_imei,
            "ro.ril.oem.imei1": new_imei,
            "wifi.interface.mac": new_mac,
            "ro.boot.wifimacaddr": new_mac,
        }
        root_cmds = [f'{rp} -n "{k}" "{v}"' for k, v in prop_map.items()]
        root_cmds.append(
            f"if [ -d /sys/class/net/wlan0 ]; then ip link set wlan0 down 2>/dev/null || true; "
            f"ip link set wlan0 address {new_mac} 2>/dev/null || true; "
            f"ip link set wlan0 up 2>/dev/null || true; fi"
        )
        run_adb(adb_exe, ["shell", f"su -c '{' && '.join(root_cmds)}'"], timeout=25)

    for c in cmds:
        run_adb(adb_exe, ["shell", c], timeout=10)

    log_fn(f"[IDENTITY] New Serial     : {new_serial}")
    log_fn(f"[IDENTITY] New IMEI       : {new_imei}")
    log_fn(f"[IDENTITY] New Wi-Fi MAC  : {new_mac}")
    log_fn(f"[IDENTITY] New Android ID : {new_android_id}")
    return {
        "imei": new_imei,
        "serial": new_serial,
        "mac": new_mac,
        "android_id": new_android_id,
    }


def toggle_wifi_lan_simulation(
    adb_exe: str,
    enable_wifi: bool,
    log_fn: Callable[[str], None] = print,
) -> bool:
    """Switch virtual Wi-Fi (wlan0 / Home_WiFi_5G) ON or revert cleanly to raw LAN (eth0)."""
    if not ensure_adb_connected(adb_exe, log_fn):
        return False

    if enable_wifi:
        script = (
            "rm -f /data/adb/portable_stealth_wifi_disabled && "
            "(ip link add link eth0 name wlan0 type virt_wifi 2>/dev/null || true) && "
            "(ip link set wlan0 up 2>/dev/null || true) && "
            "svc wifi enable 2>/dev/null || true"
        )
        run_adb(adb_exe, ["shell", f"su -c '{script}'"], timeout=15)
        run_adb(adb_exe, ["shell", "cmd wifi connect-network 'Home_WiFi_5G' open 2>/dev/null || true"], timeout=10)
        log_fn("[NETWORK] Switched to Virtual Wi-Fi mode (wlan0: Home_WiFi_5G).")
    else:
        script = (
            "touch /data/adb/portable_stealth_wifi_disabled && "
            "svc wifi disable 2>/dev/null || true && "
            "(ip link set wlan0 down 2>/dev/null || true)"
        )
        run_adb(adb_exe, ["shell", f"su -c '{script}'"], timeout=15)
        log_fn("[NETWORK] Switched to direct Wired LAN mode (eth0).")
    return True


def trim_vm_ram(
    adb_exe: str,
    log_fn: Callable[[str], None] = print,
) -> bool:
    """Drop guest Linux caches and trim background processes so virtio-balloon reclaims RAM for Windows 11."""
    if not ensure_adb_connected(adb_exe, log_fn):
        return False

    before_out = (run_adb(adb_exe, ["shell", "grep MemAvailable /proc/meminfo"]).stdout or "").strip()
    run_adb(adb_exe, ["shell", "am kill-all"], timeout=15)
    run_adb(adb_exe, ["shell", "pm trim-caches 512M"], timeout=15)
    run_adb(adb_exe, ["shell", "su -c 'sync && echo 3 > /proc/sys/vm/drop_caches' 2>/dev/null || sync"], timeout=15)
    after_out = (run_adb(adb_exe, ["shell", "grep MemAvailable /proc/meminfo"]).stdout or "").strip()

    log_fn(f"[RAM-TRIM] Before: {before_out or 'unknown'} -> After: {after_out or 'trimmed'}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Portable Android 13 Device Spoofer")
    parser.add_argument("--adb", default="bin/adb.exe", help="Path to adb executable")
    parser.add_argument(
        "--profile",
        default="Google Pixel 8 Pro",
        choices=list(DEVICE_PROFILES.keys()),
        help="Target device profile to spoof",
    )
    args = parser.parse_args()
    ok = apply_spoof(args.adb, args.profile, print)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
