#!/system/bin/sh
# CI-only log bridge. Host ADB may be unauthorized on a headless guest; mirror
# high-value Android service/crash records to the existing serial /dev/kmsg tap.
LOGCAT=/system/bin/logcat
KMSG=/dev/kmsg

emit() {
    printf '<6>PORTABLE-LOGCAT %.900s\n' "$1" > "$KMSG" 2>/dev/null || true
}

emit "mirror starting"
# Init creates socket nodes before logd finishes binding them. Wait for a live socket.
for _ in $(/system/bin/seq 1 60); do
    [ -S /dev/socket/logdr ] && break
    /system/bin/sleep 1
done
if [ ! -S /dev/socket/logdr ]; then
    emit "logdr socket unavailable after 60s"
fi

# Capture logcat's stderr too: a denied socket/exec used to make the service
# exit with status 1 without leaving any explanation in the serial artifact.
# Retry inside this process so init does not rapidly restart a failing service.
while true; do
    # Stream records immediately; command substitution would buffer logcat.
    "$LOGCAT" -b all -v threadtime 2>&1 | while IFS= read -r line; do
        case "$line" in
            *netd*|*BpfLoader*|*LibBpfLoader*|*libc*|*crash_dump*|*tombstoned*|*debuggerd*|*DEBUG*|*Fatal signal*|*Abort message*|*backtrace*|*SIGABRT*|*SIGSEGV*|*SurfaceFlinger*|*surfaceflinger*|*hwcomposer*|*HWC*|*adbd*|*AndroidRuntime*|*ConnectivityService*|*NetworkStack*|*system_server*)
                emit "$line"
                ;;
            *error*|*Error*|*ERROR*|*failed*|*Failed*|*FAILED*|*"Permission denied"*|*"not allowed"*|*"Unknown option"*|*"cannot connect"*)
                emit "logcat-client-error: $line"
                ;;
        esac
    done
    emit "logcat stream ended; retrying in 2 seconds"
    /system/bin/sleep 2
done
