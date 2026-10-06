#!/usr/bin/env bash
# tty1 autologin -> compositor session (QA ready image).
printf 'HORNERO-SESSION-START uptime=%s\n' "$(cut -d' ' -f1 /proc/uptime)" > /dev/ttyS0 2> /dev/null || true
compositor="$(cat /etc/hornero-qa/compositor 2>/dev/null || printf hyprland)"
export XDG_SESSION_TYPE=wayland
export HORNERO_SHELL_LOG_FILE=/tmp/qs.log
export QML2_IMPORT_PATH="$HOME/.local/lib/qt6/qml${QML2_IMPORT_PATH:+:$QML2_IMPORT_PATH}"
case "$compositor" in
    niri)
        export XDG_CURRENT_DESKTOP=niri XDG_SESSION_DESKTOP=niri
        # niri-session launches a nested login shell before it starts the
        # compositor. That shell can re-enter the QA profile on tty1, so the
        # disposable acceptance session uses Niri's documented direct session
        # mode. It imports the Wayland environment into systemd and D-Bus.
        exec niri --session > /tmp/niri.log 2>&1
        ;;
    hyprland)
        export XDG_CURRENT_DESKTOP=Hyprland XDG_SESSION_DESKTOP=Hyprland
        if command -v start-hyprland > /dev/null; then
            exec start-hyprland > /tmp/hypr.log 2>&1
        fi
        exec Hyprland > /tmp/hypr.log 2>&1
        ;;
    *)
        printf 'Unsupported QA compositor: %s\n' "$compositor" > /dev/ttyS0
        exit 64
        ;;
esac
