# Pairwise install acceptance

Status: **NOT RUN.** No candidate ISO with kernel/bootloader selection
exists yet, so every scenario in `scenarios/install-pairwise/` and
`scenarios/install-pairwise-negative/` is a declaration only. Nothing
here is a PASS. The unit/contract tests in
`tests/test_install_pairwise.py` run now and must stay green.

## Design

`src/hornero_qa/install_matrix.py` owns the QA factor model. The
canonical package catalogue lives in HorneroOS/hornero; this repo
declares only factor levels and constraints, never edition package
lists.

| Factor | Levels |
|---|---|
| kernels | `linux`, `linux-lts`, `dual-primary-linux`, `dual-primary-lts` (single/multi, primary first) |
| bootloader | `grub`, `systemd-boot` |
| firmware | `uefi`, `bios` |
| encryption | `none`, `luks` |
| edition | `desktop`, `studio` (combined specializations), `gaming` |
| bluetooth capability | on, off |

Constraints (never offer an unbootable combination):

- `systemd-boot` + BIOS is invalid and refused with an actionable
  message; Limine is not offered (deferred in the design contract).
- The primary kernel is always one of the installed kernels; every
  kernel ships its matching headers, initramfs and fallback initramfs.
- LUKS (luks1, unencrypted ESP at `/boot`, openswap behaviour) is
  orthogonal to the bootloader except for the firmware rule above.
- ESP recommendation: GRUB 512 MiB, systemd-boot 1024 MiB, plus
  256 MiB per additional kernel.

`pairwise_rows()` builds a deterministic greedy pairwise covering
array over all valid combinations, then appends the mandatory rows:
the default Desktop UEFI path with LUKS and without, every valid
bootloader × firmware pair with LUKS, Gaming UEFI LUKS and Gaming
BIOS none, a dual-kernel row booted via the LTS fallback entry, and a
combined Studio row (`complete-creative-workstation`). A test verifies
zero uncovered pairs. The nine pre-existing `scenarios/install/`
cells are retained unchanged.

Bluetooth reuses the concurrent Bluetooth workstream's contract —
capability `bluetooth`, packages `bluez`/`bluez-utils`, service
`bluetooth.service`, and `horneroctl hardware bluetooth doctor
--json` — and does not duplicate its implementation or scenarios in
`scenarios/connectivity/`.

## Execution (when an ISO exists)

Scenarios are executed manually with the existing harness, as the
retained install cells are today (the `hornero-qa` runner has no
install engine):

```sh
~/.local/share/hornero/install-test/run-install-vm.sh <name> <uefi|bios> 40 iso
# install, then reboot into the installed system:
~/.local/share/hornero/install-test/run-install-vm.sh <name> <uefi|bios> 40 noiso
```

Each scenario's proofs check, on the rebooted installed system:
running/session state, per-kernel `vmlinuz`/initramfs/fallback/headers,
boot entries per kernel (GRUB `grub.cfg` menuentries or systemd-boot
`loader/entries/`), ESP filesystem and size on UEFI, LUKS/crypttab
state, edition and specializations in the installed profile,
representative composition packages, proprietary opt-in absences
(REAPER, Steam), and the bluetooth capability state. Negative rows
cover cancellation during install, a wrong LUKS passphrase, and
systemd-boot not being offered on BIOS.

Regenerate the declarations after changing the factor model:

```sh
uv run python scripts/generate-install-pairwise.py
uv run hornero-qa matrix
```
