#!/system/bin/sh
# Android init redirects this service stdout/stderr to kmsg_debug via stdio_to_kmsg.
# Use logcat directly so no shell pipeline, external seq/grep applet, or shell
# redirection can hide an exec/linker/socket failure from the serial artifact.
exec /system/bin/logcat -b all -v threadtime
