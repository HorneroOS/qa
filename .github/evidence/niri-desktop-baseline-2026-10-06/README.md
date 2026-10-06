# Niri and GTK visual evidence — 2026-10-06

`niri-appearance.png` is the Appearance pane from the real Niri graphical acceptance run `20261006T062348Z-compositors-niri-desktop-baseline-1`. The JSON sidecar preserves capture resolution and session provenance.

`host-gtk-dark.png` is a cropped capture of a real GTK3 Thunar window on the development host. Thunar opened a temporary empty directory containing only `Read-me.txt`; the captured pane excludes the desktop, home sidebar, and unrelated windows. At capture time, both `gsettings` and `horneroctl appearance status` reported `Hornero-Dark` and `prefer-dark`.

The screenshots document the tested desktop state; they are not marketing mockups.
