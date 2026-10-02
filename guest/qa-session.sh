#!/usr/bin/env bash
# tty1 autologin -> Hyprland session (QA ready image).
printf 'HORNERO-SESSION-START uptime=%s\n' "$(cut -d' ' -f1 /proc/uptime)" > /dev/ttyS0 2> /dev/null || true
export XDG_SESSION_TYPE=wayland XDG_CURRENT_DESKTOP=Hyprland
if command -v start-hyprland > /dev/null; then
    exec start-hyprland > /tmp/hypr.log 2>&1
fi
exec Hyprland > /tmp/hypr.log 2>&1
