# Preview32 exact-artifact validation — Studio lane

Date: 2026-11-04. Disposable VM scenp32s (QEMU UEFI, 60 GiB). Artifact identity, SHA-256, signature and provenance: see `../preview32-desktop/RESULT.md` (same ISO, SHA-256 `b8cd0f86…45aec`).

Fresh install: UEFI, Erase, Btrfs, unencrypted, `HorneroOS Studio — Hyprland`, user `hornero`.

| Item | Result | Evidence |
|---|---|---|
| Install All done | PASS | 07-progress |
| First boot + graphical login | PASS | 08-desktop |
| Versions OOTB: config 0.3.18-1, horneroctl-bin preview40-1, pipewire 1:1.6.9-1, wireplumber 0.5.18-1, obs-studio 32.2.2-1 | PASS | 09-probes |
| Session polkit agent running OOTB | PASS | 09 (PID 550) |
| `horneroctl studio doctor` — all 5 checks passed | PASS | 09-probes |

Observation (cosmetic): the Studio choice preview image in Calamares is a generic archive icon, not a Studio screenshot (03-studio-selected).
