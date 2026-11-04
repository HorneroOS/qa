# Preview32 exact-artifact validation — Gaming lane

Date: 2026-11-04. Disposable VM scenp32g (QEMU UEFI, 60 GiB). Artifact identity, SHA-256, signature and provenance: see `../preview32-desktop/RESULT.md` (same ISO, SHA-256 `b8cd0f86…45aec`).

Fresh install: UEFI, Erase, Btrfs, unencrypted, `HorneroOS Gaming — Hyprland`, user `hornero`.

| Item | Result | Evidence |
|---|---|---|
| Install All done | PASS | 04-progress |
| First boot + graphical login | PASS | 05-probes (terminal in session) |
| Versions OOTB: config 0.3.18-1, horneroctl-bin preview40-1, gamescope 3.16.31-1, gamemode 1.8.2-3, mangohud 0.8.4-1 | PASS | 05-probes |
| Steam not installed (explicit opt-in only, by design) | PASS (intended) | 05-probes |
| Session polkit agent running OOTB | PASS | 05 (PID 550) |
| `horneroctl gaming doctor` — 12/14 ok; honest FAILs: no Vulkan ICD in VM, no LTS fallback kernel/snapshot tool | PASS (honest) | 05-probes |

No gameplay, Proton, controller or GPU-acceleration claim is made from this VM run.
