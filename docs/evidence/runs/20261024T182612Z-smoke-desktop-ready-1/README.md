# Preview20 desktop readiness

- Run: `20261024T182612Z-smoke-desktop-ready-1`
- Scenario: `smoke/desktop-ready`
- Result: **PASS**, 52.77 seconds; all five proof checks passed.
- Product pins: Shell `248f0c9dd020f5b83bad71503ecc488a6d0d6857`, Config
  `64557c05ecf368fb3d5ed6ced69bc5e05901edbe`, Hornero source commit
  `78ff5f4249e84ef18142ca6a6f0a3188657f3144`.
- CLI binary SHA-256: `269687cbf66666c7a33ebdaa82bafdf4b912e666405c44b7a9e42173af85f877`.
- Image: `preview20-core78ff-shell248f0c9`; Hyprland, one 1280x800 output;
  QEMU 11.1.2, 2048 MiB guest memory, 2 vCPUs.
- Candidate metadata: manifest and release `0.2.0-preview20`.

The guest proved Hyprland was running, the shell IPC exposed the launcher,
exactly one output was configured, a bar was visible, and the captured desktop
frame was nonblank. See `assertions.json`, `result.json`, and the screenshot
sidecars.

## Build and privacy notes

The source checkout built `horneroctl` with V compiler commit `ffc38ad`
(2026-10-22). The Core CLI's self-reported git version is
`horneroctl-v0.2.0-preview30-4-g78ff5f4`; the explicitly embedded manifest and
release fields are Preview20. This toolchain is older than V master HEAD at
test time and is recorded here as a provenance limitation.

The ready image was refreshed from the exact Shell and Config pins. Its
disposable base was derived from the QA provisioned Arch image with
`libcava` built from AUR commit
`39403443c8208f5d9adaaed7c8347c439efe52cf`, because the Shell harness runs
`makepkg` from the wrong directory when that dependency is absent. The
original base image was not modified.

The tracked bundle keeps run metadata, the exact scenario, action/assertion
records, result, report, screenshots, and screenshot sidecars. It omits guest
logs, which contain account paths and machine identifiers. The included files
were checked for host paths, account names, email addresses, and machine or
boot identifiers.
