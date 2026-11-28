#!/system/bin/sh
# CI-only log bridge. Host ADB may be unauthorized on a headless guest; mirror
# high-value Android service/crash records to the existing serial /dev/kmsg tap.
LOGCAT=/system/bin/logcat
KMSG=/dev/kmsg

echo '<6>PORTABLE-LOGCAT mirror starting' > "$KMSG" 2>/dev/null || true
while [ ! -S /dev/socket/logdr ]; do
    /system/bin/sleep 1
done

"$LOGCAT" -b all -v threadtime | while IFS= read -r line; do
    case "$line" in
        *netd*|*BpfLoader*|*LibBpfLoader*|*libc*|*crash_dump*|*tombstoned*|*debuggerd*|*DEBUG*|*Fatal signal*|*Abort message*|*backtrace*|*SIGABRT*|*SIGSEGV*|*SurfaceFlinger*|*surfaceflinger*|*hwcomposer*|*HWC*|*adbd*|*AndroidRuntime*|*ConnectivityService*|*NetworkStack*|*system_server*)
            printf '<6>PORTABLE-LOGCAT %.900s\n' "$line" > "$KMSG" 2>/dev/null || true
            ;;
    esac
done
