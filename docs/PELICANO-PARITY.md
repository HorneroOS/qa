# Pelicano — user-verified reference and native parity ledger

ASUS ROG Strix G16 G615LR (`pelicano`), HorneroOS Studio Preview 24 plus
additional packages, graphics drivers, Linux LTS, and the maintainer's
personal dotfiles. The maintainer has personally used this machine and
confirms it works for the real use cases below. Evidence classes:

- **USER-VERIFIED** — the maintainer personally confirmed functionality.
- **AUTOMATED-VERIFIED** — executed automated/VM QA evidence exists.
- **NOT SPECIFICALLY TESTED** — no individual test evidence; do not infer.

## Physical hardware acceptance (Preview 24 + post-install fixes)

| Capability | Status | Note |
|---|---|---|
| Studio first boot and login | USER-VERIFIED | After installer fixes/workarounds during setup |
| Hyprland desktop | USER-VERIFIED | |
| Linux LTS boot | USER-VERIFIED | Installed post-install; kernel 6.18.59-1-lts observed |
| NVIDIA RTX 5070 Ti + `nvidia-smi` | USER-VERIFIED | Driver 615.78.08 after manual module install |
| OBS Studio usability | USER-VERIFIED | |
| Focusrite Scarlett usability | USER-VERIFIED | |
| Studio applications | USER-VERIFIED | |
| Dotfiles-enhanced workstation | USER-VERIFIED | The golden reference experience |
| NVENC encoding | NOT SPECIFICALLY TESTED | No encoder-specific evidence |
| Vulkan correctness | NOT SPECIFICALLY TESTED | |
| HDMI capture | NOT SPECIFICALLY TESTED | |
| Suspend/resume, external display | NOT SPECIFICALLY TESTED | |

These results do **not** prove the clean ISO delivers the same result:
Preview 24 needed post-install packages, drivers, LTS, and dotfiles.

## Installation incident ledger

| ID | Root cause | Fix | Release status | Hardware |
|---|---|---|---|---|
| P0-01 VMD hides NVMe | Intel RST/VMD controller mode | Docs guidance (docs#95/#96), diagnostic (qa#50) | Source only | USER-VERIFIED workaround (VMD disabled) |
| P0-02 copytoram | Archiso unmounts payload after copy-to-RAM | installer#48 preflight + `copytoram=n` default | preview28 (8 GiB VM); ≥16 GiB NOT TESTED (host 15 GiB) | Bug proven on 32 GiB machine; fixed ISO not yet proven at 32 GiB |
| P0-03 openswap | Calamares emitted nonexistent `openswap` hook | installer#49 `userSwapChoices: [ none ]`, root cause docs#95 | preview28 | Successful install used No Swap |
| P0-04 failed-install state | Active swap/LUKS/mounts hid Erase Disk | Cleanup on cancel; VM cancel/retry PASS preview28 | preview28 | Observed originally; VM-verified fix |
| P0-05 pacman no servers | `[multilib]` include lost in cleanup | installer#47 | preview28 VM sync PASS | Manual repair originally required |
| P0-06 XFCE Live | Live used XFCE, not Hornero Desktop | installer#51; lock fix #53; terminal #57; firstboot #59 | #51 in preview28; #57/#59 next ISO | — |
| P0-07 missing zsh/nano | Not in composition/account defaults | hornero#336, installer#50 | preview28 VM | USER-VERIFIED after dotfiles era |
| P0-08 NVIDIA userspace only | Hardware-neutral composition ships no vendor module | hornero#342 doctor coherence check | Next horneroctl tag | USER-VERIFIED after manual install |
| P0-09 LIBVA=nvidia | Universal env forced NVIDIA VA-API | config#114 | Next config package | — |
| P0-10/11/12 LTS/GRUB/EFI | No LTS by default; GRUB state unverified | gaming doctor recovery check; installer#60 verify step | installer#60 next ISO | LTS USER-VERIFIED manually installed |
| P1-13 kernel not rebooted | Running vs installed kernel confusion | hornero#342 `gpu-driver-coherence` | Next horneroctl tag | Observed on pelicano |
| P1-15 preview24 identity | Preview 24 keeps `ID=arch` | installer#55 (new installs); `HORNERO_NATIVE=1` for preview24 | preview28 new installs | pelicano itself is the preview24 case |

## Native parity matrix (dotfiles → HorneroOS)

| Capability | Clean HorneroOS | Dotfiles | Native owner | Action |
|---|---|---|---|---|
| Zsh + login shell | Yes (preview28) | historical installer | hornero/installer | Done; keep |
| Kitty terminal + defaults | Yes | one-shot migration #392 | config/hornero | Done; keep |
| nano + `EDITOR` | Yes (preview28) | — | hornero | Done |
| Hyprland Lua config | Yes | legacy scripts retired | config | Done |
| Hornero Shell/Control Center | Yes | must not override | shell | Guarded by native detection |
| PipeWire/WirePlumber | Yes (hornero#334) | must not duplicate | hornero | Done |
| Studio apps + OBS | Yes (Studio composition) | personal presets stay personal | hornero | Done; presets personal |
| NVIDIA driver | Diagnostics only (hornero#342) | manual install was used | horneroctl doctor + docs | No silent install; actionable diagnosis |
| LTS recovery kernel | Not by default; doctor reports it | manual install was used | installer/hornero policy | Product decision pending; do not force |
| Dev tools (git, gh, uv, etc.) | Partial | full personal set | Developer profile (planned) | Keep personal until profile ships |
| SSH/Git identity, aliases | No (personal) | yes | dotfiles (personal) | Never migrate to OS |
| OBS production profile | No (personal) | yes | dotfiles (personal) | Keep secret-free template only in docs |

## Addendum — read-only SSH diagnostic, 2026-11-04 (Preview 33)

Maintainer-authorized read-only session (`qa/scripts/asus-diagnostic.sh`
run from `/tmp` on `pelicano.local`, remote artifacts removed; no
configuration changed). Observed facts, not a clean-ISO certification:

| Check | Observed | Class |
|---|---|---|
| Running kernel | Linux 6.18.60-1-lts (also installed: 7.2.14-arch1-1) | AUTOMATED-VERIFIED (read-only probe) |
| NVIDIA driver coherence | 615.78.08 kernel module + userspace on RTX 5070 Ti (GB205M); `nvidia-smi` healthy | AUTOMATED-VERIFIED |
| Vulkan ICD | NVIDIA device visible, apiVersion 1.4.351 | AUTOMATED-VERIFIED (ICD registration only; rendering workloads NOT SPECIFICALLY TESTED) |
| FFmpeg NVENC | h264/hevc/av1 test encodes passed in the same SSH session (probe output not retained in the diagnostic file) | Operator-observed; OBS NVENC remains NOT SPECIFICALLY TESTED |
| Studio doctor | `horneroctl studio doctor`: all 5 checks passed | AUTOMATED-VERIFIED |
| Audio graph | PipeWire 1.6.10 + WirePlumber up; Scarlett NOT CONNECTED during the session | AUTOMATED-VERIFIED (stack only) |
| Internal display | eDP 2560x1600 mode present (card1-eDP-1) | AUTOMATED-VERIFIED |
| Secure Boot | disabled | AUTOMATED-VERIFIED |
| Storage | 1 TB WD SN5000S, LUKS + Btrfs subvolumes; `/boot` at 62% of 511 MiB | AUTOMATED-VERIFIED; watch ESP headroom |
| Package freshness | Machine lags the published channel (observed `hornero-config 0.3.17-1`, `horneroctl-bin 0.2.0_preview39-1` vs published 0.3.18-1 / preview40-1 at the time) | Maintainer action: normal full upgrade |

Still NOT SPECIFICALLY TESTED on hardware: OBS NVENC recording/stream
finalization, HDMI capture and output, Bluetooth pairing (Intel BE200
adapter present), suspend/resume, external displays and refresh modes,
Scarlett routing, clean-ISO installation on this machine.

## Outstanding specialized qualification (not goal blockers)

NVENC encode proof, Vulkan correctness, HDMI capture stability,
suspend/resume, external displays, ≥16 GiB copytoram on the fixed ISO,
and installer#57/#59/#60 validation against the exact next ISO artifact.
