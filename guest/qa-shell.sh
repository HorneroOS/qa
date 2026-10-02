#!/usr/bin/env bash
# Start the Hornero shell inside the QA session and print a serial readiness
# marker once its IPC answers. The marker is a diagnostic timestamp only:
# scenario proof is always visual or a probe.
export QML2_IMPORT_PATH="$HOME/.local/lib/qt6/qml${QML2_IMPORT_PATH:+:$QML2_IMPORT_PATH}"
cd "$HOME/.config/quickshell" || exit 1
qs > /tmp/qs.log 2>&1 &
for _ in $(seq 1 240); do
    qs ipc call drawers list > /dev/null 2>&1 && break
    sleep 0.25
done
printf 'HORNERO-SHELL-READY uptime=%s\n' "$(cut -d' ' -f1 /proc/uptime)" > /dev/ttyS0 2> /dev/null || true
wait
