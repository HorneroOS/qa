# desktop-uefi — offline qualification run (RESULT, operator-reviewed)

Scenario: `install/desktop-uefi-unencrypted`
ISO: `horneroos-2026.10-preview32-x86_64.iso`
SHA-256: `b8cd0f8604bc69f7d2112fb8bccd97115d32d197e9c92c62e02faf5de6345aec`
Executed: 2026-11-05T15:29:24Z by scripts/offline-qualification/run.py (scripted QMP drive, timed phases).

## Scenario probes typed on the installed system

- `pgrep -x Hyprland >/dev/null && echo up`
- `qs -c hornero ipc call drawers list`
- `hyprctl configerrors -j | python3 -c "import json,sys;print(len([e for e in json.load(sys.stdin) if len(e)>0]))"`
- `python3 -c "import json;print(json.load(open('/usr/lib/hornero/system-profile.json'))['edition']['edition'])"`
- `horneroctl system info --json | python3 -c "import json,sys;print(json.load(sys.stdin)['data']['edition'])"`
- `grep -c hornero-installer /etc/pacman.conf; true`

## Screenshots (in order)

- 01-boot.png
- 01-installed-boot.png
- 02-installed-desktop.png
- 02-partitions.png
- 03-partition-choice.png
- 03-probe-1.png
- 04-probe-2.png
- 04-users.png
- 05-edition.png
- 05-probe-3.png
- 06-probe-4.png
- 06-summary.png
- 07-installing.png
- 07-probe-5.png
- 08-installing.png
- 08-probe-6.png
- 09-installing.png
- 09-parity.png
- 10-installing.png
- 11-installing.png
- 12-installing.png
- 13-installing.png
- 14-installing.png
- 15-installing.png
- 16-installing.png
- 17-installing.png
- 18-installing.png
- 19-installing.png
- 20-installing.png
- 21-installing.png
- 22-installing.png
- 23-installing.png
- 24-installing.png
- 25-installing.png
- 26-installing.png
- 27-installing.png
- 28-installing.png
- 29-installing.png
- 30-installing.png
- 31-installing.png
- 32-installing.png
- 33-installing.png
- 34-installing.png
- 35-installing.png
- 36-install-final-state.png

## Verdict

PASS — operator visual review 2026-11-05 (review session for run smoke-preview32-r2).

Evidence inspected frame-by-frame:
- 03-partition-choice.png: Erase disk selected on /dev/vda (60 GiB, EFI), "Encrypt system" unchecked — correct for the unencrypted scenario. This is the frame the qa#76 fix (checkbox-centre click) repaired; r1 attempt-1 never reached install.
- 06-summary.png: GPT on /dev/vda; 512 MiB FAT32 EFI (/boot), 8 MiB bios-grub, 59.49 GiB Btrfs root; timezone America/Argentina/Buenos_Aires.
- 04-users.png / 05-edition.png: user hornero / hostname hornero-test valid; edition "HorneroOS Desktop — Hyprland" selected.
- 36-install-final-state.png (and 20-installing.png): Calamares Finish "All done." — install completed. Cosmetic note: the sentence reads " has been installed on your computer." (product name missing before "has") — recorded as a cosmetic observation, not a scenario failure.
- 01-installed-boot.png: installed system boots without ISO to the Hyprland greeter.
- 02-installed-desktop.png: Hornero Welcome on the installed desktop; shell bar/dock visible.
- Probes (all as written in the scenario):
  - PROBE1 `pgrep -x Hyprland` -> up
  - PROBE2 `qs -c hornero ipc call drawers list` -> bar, osd, session, launcher, dashboard, utilities, sidebar, layoutPicker
  - PROBE3 Hyprland config errors -> 0
  - PROBE4 /usr/lib/hornero/system-profile.json edition -> desktop
  - PROBE5 `horneroctl system info --json` edition -> desktop
  - PROBE6 `grep -c hornero-installer /etc/pacman.conf` -> 0 (installer repo removed)
- 09-parity.png: horneroctl horneroctl-v0.2.0-preview40 (a449641) matches sidecar productRevision a44964197c456fa44faeaff675206705c7bbdf1b; manifest hornero-0.2.0-preview23; 509 packages.

Scope: this PASS is for install/desktop-uefi-unencrypted on the signed Preview 32 ISO only. Preview 32 installerRevision 329e6683 predates installer#94, so the cancel-contract is not applicable here. r1 attempt-1 (smoke-preview32/) was an infrastructure failure and is not imported.
