# Signal VM evidence, 2026-11-17

Captured in the disposable QA VM (not the host). Image
`signal-s433acea-cf1e98b1-hdaa03b0` (shell 433acea, config f1e98b1,
horneroctl daa03b0) unless the file says 02cc16b below. Run bundles are under
`docs/evidence/runs/`. Frames are labelled VM evidence.

| File | Image | Shows |
|---|---|---|
| shell-clear-ink-{iguazu-detailed,quebrada-vivid,ibera-bright}.png | 433acea | Cockpit Clear ink illegible over bright/detailed wallpapers |
| shell-clear-ink-nocturno-dark-ok.png | 433acea | same layout over a dark wallpaper (legible) |
| shell-mode-{everyday,signal}.png | 433acea | Signal mode differs from Everyday only by a "SIG" chip |
| shell-appearance-pane-chips-overlap.png | 433acea | theme names truncated, chips overlap text |
| shell-closed-popout-notch-crop-10x.png | 02cc16b | amber 6 px mark at x=0 while no popout is open (still present on 433acea) |
| shell-power-popout-text-clipped.png | 02cc16b | "Power profile: E..." clipped in the Power popout |
| shell-contrast-theme-bar-edge.png / shell-night-reference.png | 02cc16b | Signal Contrast bar vs ground 1.02:1 |
| shell-scaled-output-*.png | 02cc16b | popout and utilities drawer on a 1.5x second output |
| config-deprecated-banner-boot.png | 02cc16b | Hyprland deprecated-config banner at boot |

## Installer (rootless QEMU), preview32 ISO

`installer-preview32-live-3gib-ram-gate.png`: the signed preview32 ISO
(sha256 b8cd0f86..., GPG good) boots rootless under user QEMU/KVM with OVMF on a
throwaway disk and reaches Calamares, which refuses to continue at 3 GiB
("does not have enough working memory. At least 4 ..."; installer
`welcome.conf` requiredRam: 4.0). Install-to-first-boot needs a 4 GiB guest,
above the mission's 3 GiB VM cap, so it was not run. Host resolv.conf must be
shadowed in a user+mount namespace for DNS (script in VM-HOWTO).
