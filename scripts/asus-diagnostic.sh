#!/usr/bin/env bash
# Read-only ASUS ROG Strix G16 diagnostic for HorneroOS Studio.
# Collects hardware/driver facts for the compatibility matrix.
# Never modifies the system. Review output before sharing: it contains
# serial-adjacent identifiers (PCI IDs, firmware versions) but no secrets.
set -u
echo "== system =="; hostnamectl 2>/dev/null | head -8
echo "== os =="; grep -E '^(NAME|PRETTY_NAME|ID)=' /etc/os-release
echo "== kernel =="; uname -r
echo "== cpu/mem =="; lscpu | grep -E 'Model name|^CPU\(s\)'; free -h | head -2
echo "== gpu pci =="; lspci -nn | grep -iE 'vga|3d|display'
echo "== gpu drivers =="; lsmod | grep -iE 'nvidia|i915|xe' ; nvidia-smi 2>&1 | head -12
echo "== vulkan =="; vulkaninfo --summary 2>/dev/null | grep -E 'deviceName|driverName|apiVersion' | head -8
echo "== displays =="; ls /sys/class/drm/*/status 2>/dev/null; for f in /sys/class/drm/*/modes; do echo "$f: $(head -1 $f 2>/dev/null)"; done 2>/dev/null | head -5
echo "== block/NVMe =="; lsblk -d -o NAME,MODEL,SIZE,TRAN; lsblk -o NAME,FSTYPE,LABEL,MOUNTPOINTS | head -20
echo "== storage controller (Intel VMD/RST hides NVMe when enabled) =="; lspci -nn | grep -iE 'sata|raid|vmd|non-volatile'; ls /dev/nvme* 2>/dev/null || echo "no /dev/nvme* nodes: check Intel VMD/RST setting in firmware (do not delete partitions)"
echo "== kernel coherence =="; echo "running: $(uname -r)"; echo "installed: $(ls /usr/lib/modules 2>/dev/null | tr '\n' ' ')"; cat /sys/module/nvidia/version 2>/dev/null || echo "nvidia module: not loaded"; df -h /boot 2>/dev/null | tail -1
echo "== secure boot =="; mokutil --sb-state 2>&1 | head -2; bootctl status 2>/dev/null | grep -E 'Secure Boot|Firmware' | head -3
echo "== audio =="; aplay -l 2>/dev/null | grep card; pactl info 2>/dev/null | grep -E 'Server Name|Default S|Sample' ; wpctl status 2>/dev/null | head -20
echo "== video devices =="; ls -l /dev/video* 2>/dev/null; v4l2-ctl --list-devices 2>/dev/null | head -15
echo "== usb =="; lsusb | grep -viE 'root hub'
echo "== network =="; ip -br link; networkctl list 2>/dev/null | head -6
echo "== power/thermal =="; upower -e 2>/dev/null; sensors 2>/dev/null | grep -E 'Core|Tctl|edge|fan' | head -8
echo "== studio =="; horneroctl studio doctor 2>&1 | head -15; pacman -Q hyprland obs-studio pipewire wireplumber 2>/dev/null
echo "== done (read-only) =="
