# Cancel during install — negative acceptance

Scenario: `install-pairwise-negative/cancel-during-install`
(covers installer#11, qa#19; finding filed as HorneroOS/installer#93)
Executed: 2026-11-04, disposable QEMU/KVM VM (UEFI/OVMF, 4 GiB RAM,
4 vCPU, 60 GiB virtio disk), manual QMP install harness.
ISO: `horneroos-2026.10-preview32-x86_64.iso`
SHA-256: `b8cd0f8604bc69f7d2112fb8bccd97115d32d197e9c92c62e02faf5de6345aec`

## Procedure

1. Booted the signed preview32 ISO (00-boot.png); Desktop — Hyprland,
   Erase disk, unencrypted (01-partitions.png); user `hornero`;
   summary reviewed (02-summary.png); install started.
2. At **56% — "Install packages"** (Calamares job 21/41, the single
   `pacman -S` transaction for the whole edition list, visible in the
   toggled log, 05-before-cancel.png) clicked **Cancel** and confirmed
   **Yes** on "Do you really want to cancel the current install
   process? The installer will quit and all changes will be lost."
   (06-cancel-dialog.png, cancel-clicked.txt).
3. Calamares quit to the live desktop (07-after-cancel.png,
   08-after-cancel-2.png). Cleanup checks in the live session
   (09-cleanup-checks.png): no target mounts (`mount | grep -E
   'vda|calamares'` empty), no swap, no calamares/pacman processes,
   target partitions present but unmounted; only the empty directory
   `/tmp/calamares-root-sd5lxo6x` remained in the live tmpfs.
4. Rebooted with the ISO detached, expecting no installed system:
   **the target booted to the SDDM greeter** (10-noiso-boot.png,
   11-noiso-boot-2.png, 12-partial-greeter-form.png).

## What actually happened

- The target `/var/log/pacman.log` shows the transaction's
  post-transaction hooks finishing at 19:51:13 -0300, ~18 s **after**
  the cancel confirmation (19:50:55): the pacman child completed the
  full transaction after the Calamares UI quit (15-partial-depth.png).
- The "cancelled" target is a working installed system: greeter
  presents user `hornero`, who authenticates (tty3 verified,
  13-partial-tty.png); `/usr/lib/hornero/system-profile.json` exists;
  `horneroctl-bin 0.2.0_preview40-1` and
  `hornero-profile-desktop-hyprland 0.0.0.a449641…-1` are installed
  (509 packages total); `hornero-installer` count in `pacman.conf` is
  0; no `db.lck`; sddm enabled; hostname/locale correct
  (14-partial-state.png, 15-partial-depth.png).
- Which of the remaining ~20 Calamares jobs ran is unknown (the live
  session log is gone with the ramdisk); the bootable result is most
  consistent with the unpackfs-copied base plus the completed pacman
  transaction.

## Scenario proofs

| # | Proof | Result |
|---|---|---|
| 1 | Target does not boot into an installed system after cancel (instruction) | **FAIL — target boots to the greeter and the created user authenticates** |
| 2 | No installed profile after cancelled install (`live-only` probe on the re-attached live session) | NOT RUN — the core assertion already failed at the boot step; the profile in fact exists on the target, so the probe's premise does not hold. Recorded here instead of executing a meaningless live-side check |
| 3 | Cancellation state screenshot | Captured: 06-cancel-dialog.png, 08-after-cancel-2.png |
| — | Live session usable after cancel; no stale mounts/processes/swap (goal-level cleanup check) | PASS (09-cleanup-checks.png) |

## Verdict (operator)

FAIL against the scenario as written. "Cancel" at the package job
does not cancel: the transaction completes behind the quitting UI and
the user ends up with a bootable system they explicitly declined,
with an unknown subset of the remaining installer jobs unexecuted.
Tracked as HorneroOS/installer#93; the provisional-Calamares cancel
contract needs either a real abort or honest wording/behavior, and
this scenario may then need revision to match the decided contract.
No failure class is attributed by the operator (design contract
question for the installer owner).
