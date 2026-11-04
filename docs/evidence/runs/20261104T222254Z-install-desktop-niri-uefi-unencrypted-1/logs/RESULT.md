# Desktop Niri UEFI unencrypted — install-to-first-boot acceptance

Scenario: `install/desktop-niri-uefi-unencrypted`
(covers installer#11, qa#19, config#121)
Executed: 2026-11-04, disposable QEMU/KVM VM (UEFI/OVMF, 4 GiB RAM,
4 vCPU, 60 GiB virtio disk, virtio-vga 1280x800), manual QMP install
harness.
ISO: `horneroos-2026.10-preview32-x86_64.iso`
SHA-256: `b8cd0f8604bc69f7d2112fb8bccd97115d32d197e9c92c62e02faf5de6345aec`
(verified with `sha256sum -c` before the Stage D queue: OK)

## Procedure

1. Booted the signed preview32 ISO (00-boot.png); Calamares on the live
   desktop. Location/keyboard defaults.
2. Partitions: EFI, **Erase disk**, **Encrypt system unchecked**
   (01-erase.png, 02-unencrypted.png).
3. Users: `hornero` / hostname `hornero-test`.
4. Edition and compositor: **HorneroOS Desktop — Niri (Experimental)**
   (03-edition.png, 04-edition-niri.png) — the chooser labels Niri
   EXPERIMENTAL, "Core desktop support is still being validated."
5. Summary reviewed (05-summary.png); install completed: **"All done."**
   (06-installing.png, 07-installing.png).
6. Rebooted **without the ISO**; greeter reached with session **Niri**
   (08-greeter.png); authenticated as `hornero`.
7. **The graphical session renders a black screen** (09-session.png,
   10-session-esc.png). Diagnosis from tty3 (11-tty.png … 17-diag-6.png).

## Diagnosis (tty3, same boot)

- loginctl: graphical user session on tty1 exists; processes alive:
  `niri --session` (pid 537), `niri msg --json event-stream`,
  `/usr/bin/quickshell` (pid 615). Shell IPC answers: drawers include
  `launcher` (13-diag-2.png).
- Installed profile is correct: `.edition.edition` = `desktop`,
  `.edition.compositor` = `niri`,
  `.edition.compositorMaturity` = `experimental` (13-diag-2.png).
- `niri msg --json outputs` (via the session socket
  `/run/user/1000/niri.wayland-1.537.sock`) returns **`{}` — zero
  outputs**; the single workspace has `"output": null`; the Hornero
  Welcome window exists in `niri msg windows` but cannot render
  (16-diag-5.png).
- `/sys/class/drm/` contains `card1`, `card1-Virtual-1`, `renderD128`
  (connector present), while the user journal repeats every second:
  `WARN niri::backend::tty: error doing early import:
  Error::DeviceMissing` (17-diag-6.png).
- The identical VM configuration renders the Hyprland choice correctly
  (tracked PASS runs on this same ISO).

## Scenario proofs

| # | Proof | Result |
|---|---|---|
| 1 | Niri session running | PASS — `niri --session` alive (12-diag-1.png) |
| 2 | Niri reports ≥1 output (equals `1`) | **FAIL — outputs is `{}`, count 0** (16-diag-5.png) |
| 3 | Shell IPC contains `launcher` | PASS (13-diag-2.png) |
| 4 | Profile edition/compositor = `desktop/niri` | PASS (13-diag-2.png) |
| 5 | `horneroctl system info` edition = `desktop` | NOT RUN in-session (profile check 4 covers the same metadata; session unusable graphically) |
| 6 | `hornero-installer` absent from `pacman.conf` | NOT RUN (same reason) |
| 7 | Desktop frame non-blank | **FAIL — frame is fully black** (09-session.png) |

## Verdict (operator)

FAIL. The installation, composition and session processes are correct,
but the installed Niri desktop is not usable on this hardware
configuration: niri's TTY backend cannot import the virtio-gpu device
(`Error::DeviceMissing`), so no output exists and the screen stays
black. No failure class is attributed yet — whether this is a Hornero
niri session/config defect, a missing composition package, or an
upstream niri↔virtio-gpu interaction is tracked in
HorneroOS/config#121. Physical-hardware behavior is NOT TESTED and
must not be inferred from this VM result. The same symptom was
observed on preview29 (Gaming — Niri row, recorded NOT VERIFIED then).
