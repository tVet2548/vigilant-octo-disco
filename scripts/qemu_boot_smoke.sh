#!/usr/bin/env bash
set -Eeuo pipefail

QEMU_BIN="${QEMU_BIN:-qemu-system-x86_64}"
ADB_BIN="${ADB_BIN:-adb}"
BOOT_TIMEOUT_SECONDS="${BOOT_TIMEOUT_SECONDS:-900}"
ADB_TIMEOUT_SECONDS="${ADB_TIMEOUT_SECONDS:-120}"
SOAK_SECONDS="${SOAK_SECONDS:-90}"
BOOT_MARKER='[PORTABLE-BOOT] BOOT_COMPLETED=1'
NETD_FAIL_RE="Service 'netd'.*(exited with status [1-9][0-9]*|received signal (6|11))"
SERVICE_FAIL_RE="Service '(vendor\.hwcomposer[^']*|surfaceflinger|zygote(_secondary)?)'.*(exited with status [1-9][0-9]*|received signal (6|11))"
FATAL_RE='\[INIT-WRAPPER\] FATAL:|Kernel panic - not syncing|InitFatalReboot|Init encountered errors|Attempted to kill init|reboot: Restarting system|has incorrect label or no domain transition|vrend_decode_ctx_submit_cmd|Illegal command buffer|Fatal signal (6|11)|SIGSEGV|SIGABRT'
ADB_SERIAL="127.0.0.1:5556"
SMOKE_FAIL=0

if [[ "${1:-}" == "--self-test" ]]; then
    printf "%s\n" "init: Service 'vendor.hwcomposer-2-1.drmfb' (pid 123) received signal 6" | grep -qE "$SERVICE_FAIL_RE"
    printf "%s\n" "init: Service 'surfaceflinger' (pid 124) received signal 11" | grep -qE "$SERVICE_FAIL_RE"
    printf "%s\n" "init: Service 'netd' (pid 125) exited with status 1" | grep -qE "$NETD_FAIL_RE"
    printf "%s\n" "inet 10.0.2.15/24" | grep -qE 'inet 10\.0\.2\.[0-9]+/[0-9]+'
    printf "%s\n" "default via 10.0.2.2 dev eth0" | grep -qE 'default via 10\.0\.2\.2( |$)'
    echo "QEMU smoke regex self-test passed."
    exit 0
fi

BUNDLE_DIR="$(realpath -m "${1:-dist_bundle}")"
DIAG_DIR="$(realpath -m "${2:-${RUNNER_TEMP:-/tmp}/qemu-android-diagnostics}")"

mkdir -p "$DIAG_DIR"

test -s "$BUNDLE_DIR/images/system.img"
test -s "$BUNDLE_DIR/images/vendor.img"
test -s "$BUNDLE_DIR/images/data.img"
command -v "$QEMU_BIN" >/dev/null
command -v xvfb-run >/dev/null
command -v "$ADB_BIN" >/dev/null
"$ADB_BIN" start-server >/dev/null

capture_guest_state() {
    local out="$1"
    {
        echo "===== getprop ====="
        timeout 20s "$ADB_BIN" -s "$ADB_SERIAL" shell getprop 2>&1 || true
        echo "===== interface addresses ====="
        timeout 20s "$ADB_BIN" -s "$ADB_SERIAL" shell ip addr 2>&1 || true
        echo "===== default routes ====="
        timeout 20s "$ADB_BIN" -s "$ADB_SERIAL" shell ip route show default 2>&1 || true
        echo "===== SurfaceFlinger ====="
        timeout 30s "$ADB_BIN" -s "$ADB_SERIAL" shell dumpsys SurfaceFlinger 2>&1 || true
        echo "===== tombstone directory ====="
        timeout 20s "$ADB_BIN" -s "$ADB_SERIAL" shell ls -la /data/tombstones 2>&1 || true
        echo "===== crash buffer ====="
        timeout 30s "$ADB_BIN" -s "$ADB_SERIAL" logcat -b crash -d -v threadtime 2>&1 || true
    } > "$out"
}

run_boot_smoke() {
    local kname="$1"
    local iname="$2"
    local serial_log="$DIAG_DIR/${kname}.serial.log"
    local stderr_log="$DIAG_DIR/${kname}.qemu.stderr.log"
    local debug_log="$DIAG_DIR/${kname}.qemu.debug.log"
    local logcat_log="$DIAG_DIR/${kname}.guest.logcat.log"
    local state_log="$DIAG_DIR/${kname}.guest-state.log"
    local qpid=""
    local logcat_pid=""
    local boot_ok=0
    local adb_ready=0
    local failure=""
    local elapsed=0
    local adb_elapsed=0
    local soak_elapsed=0

    rm -f "$serial_log" "$stderr_log" "$debug_log" "$logcat_log" "$state_log"
    "$ADB_BIN" disconnect "$ADB_SERIAL" >/dev/null 2>&1 || true
    echo "=== Android full boot: $kname / $iname; TCG IvyBridge; SELinux Enforcing; E1000; SDL software display under Xvfb ==="

    xvfb-run -a --server-args="-screen 0 1280x720x24 -nolisten tcp" \
        "$QEMU_BIN" \
        -name "CI-Smoke-$kname" \
        -no-reboot -snapshot \
        -machine pc,hpet=off \
        -smp 2,cores=2,threads=1,sockets=1 \
        -m 2048 \
        -accel tcg,thread=multi \
        -cpu IvyBridge,-ht,-tsc-deadline,+ssse3,+sse4.1,+sse4.2,+popcnt \
        -device virtio-rng-pci \
        -vga none -device virtio-vga -display sdl,gl=off \
        -netdev user,id=net0,hostfwd=tcp:127.0.0.1:5556-:5555 \
        -device e1000,netdev=net0 \
        -drive "file=$BUNDLE_DIR/images/system.img,if=virtio,format=qcow2,readonly=on" \
        -drive "file=$BUNDLE_DIR/images/vendor.img,if=virtio,format=qcow2,readonly=on" \
        -drive "file=$BUNDLE_DIR/images/data.img,if=virtio,format=qcow2" \
        -kernel "$BUNDLE_DIR/images/$kname" \
        -initrd "$BUNDLE_DIR/images/$iname" \
        -append "root=/dev/ram0 androidboot.hardware=android_x86_64 androidboot.selinux=enforcing HWACCEL=0 MESA_LLVMPIPE=1 EGL=mesa HWC_HIDL=drmfb DATA=/dev/vdc printk.devkmsg=on printk.always_kmsg_dump=1 nokaslr panic=0 earlycon=uart8250,io,0x3f8,115200 earlyprintk=serial,ttyS0,115200,keep console=ttyS0,115200 loglevel=7" \
        -serial "file:$serial_log" \
        -d guest_errors,cpu_reset -D "$debug_log" >"$stderr_log" 2>&1 &
    qpid=$!

    for ((elapsed=0; elapsed<BOOT_TIMEOUT_SECONDS; elapsed+=2)); do
        if ! kill -0 "$qpid" 2>/dev/null; then
            failure="QEMU/Xvfb exited before Android reported BOOT_COMPLETED"
            break
        fi
        if grep -qE "$NETD_FAIL_RE" "$serial_log" 2>/dev/null; then
            failure="netd exited or aborted; Android init may restart zygote"
            break
        fi
        if grep -qE "$SERVICE_FAIL_RE" "$serial_log" 2>/dev/null; then
            failure="HWC, SurfaceFlinger or zygote exited or crashed (SIGABRT/SIGSEGV)"
            break
        fi
        if grep -qE "$FATAL_RE" "$serial_log" 2>/dev/null; then
            failure="Fatal init/kernel/graphics marker detected"
            break
        fi
        if grep -Fq "$BOOT_MARKER" "$serial_log" 2>/dev/null; then
            boot_ok=1
            break
        fi
        if (( elapsed % 10 == 0 )); then
            "$ADB_BIN" connect "$ADB_SERIAL" >/dev/null 2>&1 || true
            if "$ADB_BIN" -s "$ADB_SERIAL" get-state >/dev/null 2>&1; then
                if [[ "$adb_ready" -eq 0 ]]; then
                    adb_ready=1
                    "$ADB_BIN" -s "$ADB_SERIAL" logcat -b all -v threadtime >"$logcat_log" 2>&1 &
                    logcat_pid=$!
                    echo "ADB connected; full guest logcat capture started."
                fi
            fi
        fi
        sleep 2
    done

    if [[ "$boot_ok" -eq 1 && -z "$failure" && "$adb_ready" -eq 0 ]]; then
        for ((adb_elapsed=0; adb_elapsed<ADB_TIMEOUT_SECONDS; adb_elapsed+=5)); do
            "$ADB_BIN" connect "$ADB_SERIAL" >/dev/null 2>&1 || true
            if "$ADB_BIN" -s "$ADB_SERIAL" get-state >/dev/null 2>&1; then
                adb_ready=1
                "$ADB_BIN" -s "$ADB_SERIAL" logcat -b all -v threadtime >"$logcat_log" 2>&1 &
                logcat_pid=$!
                echo "ADB connected after boot; full guest logcat capture started."
                break
            fi
            sleep 5
        done
        if [[ "$adb_ready" -eq 0 ]]; then
            failure="Android reached BOOT_COMPLETED but ADB TCP/5555 was not reachable through loopback forwarding"
        fi
    fi

    if [[ "$boot_ok" -eq 1 && -z "$failure" ]]; then
        local boot_property=""
        boot_property=$("$ADB_BIN" -s "$ADB_SERIAL" shell getprop sys.boot_completed 2>/dev/null | tr -d '\r' || true)
        if [[ "$boot_property" != "1" ]]; then
            failure="Serial boot marker was present but ADB getprop sys.boot_completed returned '$boot_property'"
        fi
    fi

    if [[ "$boot_ok" -eq 1 && -z "$failure" ]]; then
        local eth0_addr=""
        local default_route=""
        eth0_addr=$("$ADB_BIN" -s "$ADB_SERIAL" shell ip -4 addr show dev eth0 2>/dev/null | tr -d '\r' | grep -oE 'inet 10\.0\.2\.[0-9]+/[0-9]+' | head -n1 || true)
        default_route=$("$ADB_BIN" -s "$ADB_SERIAL" shell ip route show default 2>/dev/null | tr -d '\r' || true)
        if [[ -z "$eth0_addr" ]]; then
            failure="E1000 eth0 did not obtain a QEMU-user-network DHCP IPv4 address"
        elif ! grep -qE 'default via 10\.0\.2\.2( |$)' <<<"$default_route"; then
            failure="eth0 has IPv4 $eth0_addr but no default route via QEMU gateway 10.0.2.2"
        else
            echo "Network passed: eth0=$eth0_addr; $default_route"
        fi
    fi

    if [[ -n "$failure" && "$adb_ready" -eq 1 ]]; then
        capture_guest_state "$state_log"
    fi
    if [[ "$boot_ok" -eq 1 && -z "$failure" ]]; then
        capture_guest_state "$state_log"
        echo "Android BOOT_COMPLETED + ADB + DHCP/default-route passed; starting ${SOAK_SECONDS}s stability soak."
        while [[ "$soak_elapsed" -lt "$SOAK_SECONDS" ]]; do
            if ! kill -0 "$qpid" 2>/dev/null; then
                failure="QEMU/Xvfb exited during post-boot stability soak"
                break
            fi
            if grep -qE "$NETD_FAIL_RE" "$serial_log"; then
                failure="netd exited or aborted during post-boot stability soak"
                break
            fi
            if grep -qE "$SERVICE_FAIL_RE" "$serial_log"; then
                failure="HWC, SurfaceFlinger or zygote crashed during post-boot stability soak"
                break
            fi
            if grep -qE "$FATAL_RE" "$serial_log"; then
                failure="Fatal marker detected during post-boot stability soak"
                break
            fi
            sleep 5
            soak_elapsed=$((soak_elapsed + 5))
        done
    fi
    if [[ -n "$failure" && "$adb_ready" -eq 1 ]]; then
        capture_guest_state "$state_log"
    fi

    if [[ -n "$logcat_pid" ]]; then
        kill "$logcat_pid" 2>/dev/null || true
        wait "$logcat_pid" 2>/dev/null || true
    fi
    kill "$qpid" 2>/dev/null || true
    wait "$qpid" 2>/dev/null || true
    "$ADB_BIN" disconnect "$ADB_SERIAL" >/dev/null 2>&1 || true

    echo "--- $kname serial diagnostics ---"
    grep -iE 'PORTABLE-BOOT|INIT-WRAPPER|netd|zygote|surfaceflinger|hwcomposer|bootanim|e1000|eth0|dhcp|bpfloader|avc: denied|panic|FATAL|exited with status|received signal' "$serial_log" 2>/dev/null | tail -n 180 || true
    echo "--- $kname serial tail ---"
    tail -n 100 "$serial_log" 2>/dev/null || true
    echo "--- $kname QEMU stderr ---"
    cat "$stderr_log" 2>/dev/null || true
    echo "--- $kname QEMU guest debug tail ---"
    tail -n 100 "$debug_log" 2>/dev/null || true
    [[ ! -s "$logcat_log" ]] || { echo "--- $kname guest logcat tail ---"; tail -n 160 "$logcat_log" || true; }
    [[ ! -s "$state_log" ]] || { echo "--- $kname guest state diagnostics ---"; tail -n 180 "$state_log" || true; }

    if [[ "$boot_ok" -ne 1 && -z "$failure" ]]; then
        failure="Android did not report BOOT_COMPLETED within ${BOOT_TIMEOUT_SECONDS}s"
    fi
    if [[ "$boot_ok" -eq 1 && "$soak_elapsed" -lt "$SOAK_SECONDS" && -z "$failure" ]]; then
        failure="Post-boot stability soak did not finish"
    fi
    if [[ -n "$failure" ]]; then
        echo "ERROR: $kname full-boot smoke test failed: $failure" >&2
        SMOKE_FAIL=1
        return 0
    fi
    echo "PASSED: $kname reached BOOT_COMPLETED, ADB, E1000 DHCP/default route and survived ${SOAK_SECONDS}s."
}

run_boot_smoke "kernel_ksunext" "initrd_ksunext.img"
run_boot_smoke "kernel_stock" "initrd_stock.img"

if [[ "$SMOKE_FAIL" -ne 0 ]]; then
    echo "QEMU Android smoke test failed; diagnostics preserved in $DIAG_DIR" >&2
    exit 1
fi
echo "Both KernelSU and stock Android boots passed."
