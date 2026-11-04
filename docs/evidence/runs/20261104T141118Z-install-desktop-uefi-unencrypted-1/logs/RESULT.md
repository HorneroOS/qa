# Preview32 exact-artifact validation — Desktop lane

Date: 2026-11-04. Disposable VMs (QEMU UEFI, 60 GiB). VM results are not physical-hardware evidence.

## Artifact (shared by all three lanes)

- Built ISO: `horneroos-2026.10-provisional-x86_64.iso` → published as `horneroos-2026.10-preview32-x86_64.iso`
- SHA-256: `b8cd0f8604bc69f7d2112fb8bccd97115d32d197e9c92c62e02faf5de6345aec` (guest = host). Size 2931294208 bytes.
- Signature: detached `.sig`, Good signature from `FCFBEE43925AB5429362278AE59EAB44AA2498DC`; 1-byte-tampered copy verifies BAD and SHA-mismatches.
- Provenance: installer `329e66831ad5a31e48c466771f015ef05568e571` (#91), product `a44964197c456fa44faeaff675206705c7bbdf1b`, `hornero-config 0.3.18-1` (AUR `a5428ad`), `horneroctl-bin 0.2.0_preview40-1` (AUR `fc98727`), `hornero-shell 1.2.60-1`, Calamares 3.4.3, Arch snapshot 2026/10/10. Build flags: `HORNEROS_INSTALLER_CANDIDATE_STUDIO=1` (same public composition as preview31; no recovery-candidate choice).

## Desktop lane (this directory, VM scenp32)

Fresh install: UEFI, Erase, Btrfs, unencrypted, `HorneroOS Desktop — Hyprland`, user `hornero`.

| Item | Result | Evidence |
|---|---|---|
| Install All done | PASS | 15-progress |
| First boot greeter (Hyprland preselected, user prefilled) | PASS | 16–17 |
| Graphical login (Hyprland + Shell) | PASS | 18-desktop |
| Versions OOTB: config 0.3.18-1, horneroctl-bin preview40-1, shell 1.2.60-1, polkit-gnome 0.105-12 | PASS | 19-versions |
| Session polkit agent running OOTB | PASS | 19 (PID 554) |
| `pkexec whoami` GUI round-trip → root | PASS | 20–21 |
| No encryption-mapping ERROR on unencrypted boot | PASS | 21 (count 0) |
| `horneroctl recovery doctor` honest: btrfs ok, /.snapshots ok, backend/snapper unavailable FAILs | PASS (honest) | 22/23 |
| `horneroctl package status` (108 pending, reboot not required) | PASS | 23-status |

Studio and Gaming lanes of the same artifact: see `../preview32-studio/RESULT.md`, `../preview32-gaming/RESULT.md`.

Not executed on this artifact: LUKS encrypted lane (PASS on recovery candidates v3/v4; encrypted hook path unchanged), Niri sessions, BIOS lane, snapshot restore (backend remains none; no rollback claimed).

Test disks scenp32/scenp32s/scenp32g deleted after the runs per cleanup policy.
