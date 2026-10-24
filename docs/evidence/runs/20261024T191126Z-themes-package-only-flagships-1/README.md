# Preview20 package-only flagship themes

- Run: `20261024T191126Z-themes-package-only-flagships-1`
- Scenario: `themes/package-only-flagships`
- Result: **PASS**, 128.734 seconds; all proof checks passed.
- Product pins: Shell `248f0c9dd020f5b83bad71503ecc488a6d0d6857`, Config
  `64557c05ecf368fb3d5ed6ced69bc5e05901edbe`, Hornero source commit
  `78ff5f4249e84ef18142ca6a6f0a3188657f3144`.
- CLI binary SHA-256: `269687cbf66666c7a33ebdaa82bafdf4b912e666405c44b7a9e42173af85f877`.
- Image: `preview20-core78ff-shell248f0c9`; Hyprland, 1280x800;
  QEMU 11.1.2, 2048 MiB guest memory, 2 vCPUs.
- Candidate metadata: manifest and release `0.2.0-preview20`.

With personal and legacy theme/wallpaper catalogues removed, the installed
system catalogues still exposed Hornero Light and Pampa. Both themes applied
through the launcher and `horneroctl`; Pampa's GTK, icon, and wallpaper state
matched the package. The final state returned to Hornero Light and the shell
remained alive. See `assertions.json`, `result.json`, and screenshot sidecars.

The first attempt showed that the pinned Config package declares
`pampa-01.jpg` and the guest reports `/usr/share/hornero/wallpapers/pampa/pampa-01.jpg`,
while the scenario expected `.png`. The scenario was updated to assert the
asset declared by the pinned Config package; this run passed.

The scenario records `logs: on-failure`; no guest logs were generated for this
passing run. The included bundle files were checked for host paths, account
names, email addresses, and machine or boot identifiers.

The source checkout built `horneroctl` with V compiler commit `ffc38ad`
(2026-10-22). Its self-reported git version is
`horneroctl-v0.2.0-preview30-4-g78ff5f4`; explicitly embedded manifest and
release fields are Preview20. This compiler is older than V master HEAD at
test time and remains a provenance limitation.

The image base includes `libcava` built from AUR commit
`39403443c8208f5d9adaaed7c8347c439efe52cf` to work around the pinned Shell
harness's incorrect `makepkg` working directory; the original base was not
modified.
