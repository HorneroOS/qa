# Desktop BIOS unencrypted — install-to-first-boot acceptance

Scenario: `install/desktop-bios-unencrypted` (covers installer#11, qa#19)
Executed: 2026-11-04, disposable QEMU/KVM VM (legacy SeaBIOS, no OVMF
pflash, 4 GiB RAM, 4 vCPU, 60 GiB virtio disk), manual QMP install harness.
ISO: `horneroos-2026.10-preview32-x86_64.iso`
SHA-256: `b8cd0f8604bc69f7d2112fb8bccd97115d32d197e9c92c62e02faf5de6345aec`
(verified with `sha256sum -c` before the Stage D queue: OK)

## Procedure

1. Booted the signed preview32 ISO under legacy BIOS (00-boot.png);
   Calamares open on the live desktop.
2. Location America/Argentina/Buenos Aires, keyboard English (US)
   defaults.
3. Partitions: firmware shown as **BIOS**, **Erase disk** on `/dev/vda`,
   **Encrypt system unchecked**, bootloader location "Master Boot
   Record of vda (/dev/vda)" (01-partitions.png, 02-erase.png,
   03-unencrypted.png). Layout: 512 MiB FAT32 Boot, 8 MiB bios-grub,
   59.49 GiB Btrfs.
4. Users: `hornero` / hostname `hornero-test` (04-users.png).
5. Edition and compositor: **HorneroOS Desktop — Hyprland**
   (05-edition.png).
6. Summary reviewed (06-summary.png): GPT with bios-grub partition,
   "Install boot loader on /dev/vda". Install completed: **"All done."**
   (07-installing.png, 08-installing.png).
7. VM stopped and relaunched **without the ISO** under SeaBIOS; the
   installed system booted from the MBR to the greeter (09-greeter.png);
   authenticated as `hornero`; installed desktop running (10-desktop.png,
   13-installed-desktop.png).

## Scenario proofs

| # | Proof | Result |
|---|---|---|
| 1 | Hyprland session running (`up`) | PASS (12-probe-p1.png) |
| 2 | Shell IPC drawers include `launcher` | PASS (11-probes.png) |
| 3 | No Hyprland config errors | Equivalent executed: plain `hyprctl configerrors` printed nothing (11-probes.png). The as-written probe required `jq`, absent from the Desktop composition (HorneroOS/qa#63) |
| 4 | Profile `.edition.edition` = `desktop` | Equivalent grep shows `"edition": "desktop"` (11-probes.png); `jq` missing as written (qa#63) |
| 5 | `horneroctl system info` `.data.edition` = `desktop` | Equivalent grep shows `"edition":"desktop"` (11-probes.png); `jq` missing as written (qa#63) |
| 6 | `hornero-installer` absent from `pacman.conf` (`0`) | PASS (11-probes.png) |

## Extra recorded facts

- `horneroctl version`: `horneroctl-v0.2.0-preview40 (a449641)` — matches
  the preview32 product pin `a44964197c456fa44faeaff675206705c7bbdf1b`.
- `lsblk`: `vda3` is plain `btrfs` (no LUKS layer), as selected.
- `/sys/firmware/efi` absent → `bios-legacy` boot confirmed on the
  installed system.

## Verdict (operator)

INCONCLUSIVE as a formal scenario execution, for the same reason as the
UEFI+LUKS run (#64): the installation succeeded end to end under legacy
BIOS/MBR boot and every asserted fact is proven, but three probes are
not executable as written without `jq` (qa#63). A formal PASS re-run of
the probes follows once the jq-free probes land; the installed disk is
preserved for that re-execution.

## Addendum — formal probe re-execution after qa#65 (2026-11-04)

HorneroOS/qa#65 landed the jq-free install probes (#63 closed). The
same installed disk was booted again under SeaBIOS, authenticated at
the greeter, and all six scenario probes were executed **exactly as
written** in the updated `scenarios/install/desktop-bios-unencrypted.yaml`:
`up`; drawers include `launcher`; config-error count `0`; profile
`.edition.edition` = `desktop`; `horneroctl system info`
`.data.edition` = `desktop`; `hornero-installer` count in
`pacman.conf` = `0`. Evidence: 15-formal-probes.png. The run is
therefore recorded as **PASS**; the original INCONCLUSIVE phase above
is kept verbatim for the record.
