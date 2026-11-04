# Desktop UEFI encrypted (LUKS) — install-to-first-boot acceptance

Scenario: `install/desktop-uefi-encrypted` (covers installer#11, qa#19)
Executed: 2026-11-04, disposable QEMU/KVM VM (UEFI/OVMF, 4 GiB RAM, 4 vCPU,
60 GiB virtio disk), manual QMP install harness.
ISO: `horneroos-2026.10-preview32-x86_64.iso`
SHA-256: `b8cd0f8604bc69f7d2112fb8bccd97115d32d197e9c92c62e02faf5de6345aec`
(verified with `sha256sum -c` before the run: OK)

## Procedure

1. Booted the signed preview32 ISO (00-boot.png); Calamares provisional
   installer open on the live desktop (01-calamares.png).
2. Location America/Argentina/Buenos Aires (02-location.png), keyboard
   English (US) default (03-keyboard.png).
3. Partitions: **Erase disk** on `/dev/vda` with **Encrypt system**
   checked; LUKS passphrase set (test passphrase, VM-only)
   (04-partitions.png, 05-erase.png, 06-luks-pass.png). Layout preview:
   512 MiB FAT32 `/boot` (EFI), 8 MiB bios-grub, 59.49 GiB LUKS root.
4. Users: `hornero` / hostname `hornero-test` (07-users.png,
   08-users-filled.png).
5. Edition and compositor: **HorneroOS Desktop — Hyprland**
   (09-edition.png).
6. Summary reviewed (10-summary.png): GPT, 512 MiB EFI, 8 MiB bios-grub,
   60917 MiB LUKS root, btrfs system partition. Install confirmed
   (11-install-start.png); progress 15% "Filling up filesystems"
   (12-installing.png); **"All done."** (13-installing.png).
7. VM stopped and relaunched **without the ISO**; boot stopped at the
   initramfs LUKS prompt `Enter passphrase for /dev/vda3`
   (14-boot-installed.png). Passphrase entered; greeter reached
   (15-greeter.png, 16-login-form.png); authenticated as `hornero`;
   installed Hornero desktop running (17-desktop.png,
   22-installed-desktop.png).

## Scenario proofs

| # | Proof (as written) | Result |
|---|---|---|
| 1 | `pgrep -x Hyprland` → `up` | PASS — output `up` (19-probes-1.png) |
| 2 | `qs -c hornero ipc call drawers list` contains `launcher` | PASS — list: bar, osd, session, **launcher**, dashboard, utilities, sidebar, layoutPicker (19-probes-1.png) |
| 3 | `hyprctl configerrors -j \| jq …` equals `0` | NOT EXECUTABLE AS WRITTEN — `zsh: command not found: jq` (19-probes-1.png). Equivalent `hyprctl configerrors` printed nothing (no config errors) (20-probes-2.png) |
| 4 | `jq -r .edition.edition /usr/lib/hornero/system-profile.json` equals `desktop` | jq missing as written; path-scoped equivalent `python3 -c "import json;print(json.load(open('/usr/lib/hornero/system-profile.json'))['edition']['edition'])"` prints `desktop` (24-pathscoped.png) |
| 5 | `horneroctl system info --json \| jq -r .data.edition` equals `desktop` | jq missing as written; path-scoped equivalent `horneroctl system info --json \| python3 -c "import json,sys;print(json.load(sys.stdin)['data']['edition'])"` prints `desktop` (24-pathscoped.png) |
| 6 | `grep -c hornero-installer /etc/pacman.conf` equals `0` | PASS — output `0` (20-probes-2.png) |

`jq` is absent from the installed system because the canonical catalogue
only ships it in the `server` package set (hornero
`editions/catalogue.yaml`), not in Desktop. The installed composition
therefore matches the canonical choice; the scenario probes assume a
tool Desktop does not ship. Follow-up filed to make the install-scenario
probes jq-free.

## Extra recorded facts

- `horneroctl version`: `horneroctl-v0.2.0-preview40 (a449641)` — matches
  the preview32 product pin `a44964197c456fa44faeaff675206705c7bbdf1b`.
- `lsblk`: `vda3` is `crypto_LUKS`, opened as
  `luks-aa46ac3a-8ef4-4ade-949e-eafe2112cda8` (crypt, btrfs).
- `horneroctl recovery doctor` stays truthful: snapshot backend
  unavailable (`no OS snapshot backend ships yet`), root is btrfs,
  `./.snapshots` mounted, snapper absent (opt-in capability). No fake
  rollback is exposed.

## Verdict (operator)

INCONCLUSIVE as a formal scenario execution. The installation itself
succeeded end to end — install with LUKS, reboot without ISO, LUKS
unlock, greeter authentication and every asserted system fact are
proven (three of them through the documented jq-free equivalents
above). But `pass` in this repository means the scenario proofs pass
as written, and three probes (3, 4 and 5) are not executable as
written on a Desktop composition because `jq` is not shipped there;
the as-written failure is preserved above and in 19-probes-1.png.
Once HorneroOS/qa#63 makes the install probes jq-free (or Desktop
ships `jq`), this scenario can be re-run for a formal PASS without
repeating the installation evidence gathered here.

## Addendum — formal probe re-execution after qa#65 (2026-11-04)

HorneroOS/qa#65 landed the jq-free install probes (#63 closed). The
same installed disk was booted again (23-reluks.png), unlocked and
authenticated, and all six scenario probes were executed **exactly
as written** in the updated `scenarios/install/desktop-uefi-encrypted.yaml`:

- `pgrep -x Hyprland >/dev/null && echo up` → `up`
- `qs -c hornero ipc call drawers list` → contains `launcher`
- `hyprctl configerrors -j | python3 -c "…len([e for e in … if len(e)>0])"` → `0`
- profile `.edition.edition` (python3) → `desktop`
- `horneroctl system info --json` `.data.edition` (python3) → `desktop`
- `grep -c hornero-installer /etc/pacman.conf` → `0`

Evidence: 26-formal-1.png, 27-formal-2.png. With the proofs now
passing as written on the system installed in this run, the run is
recorded as **PASS**; the original INCONCLUSIVE phase above is kept
verbatim for the record.
