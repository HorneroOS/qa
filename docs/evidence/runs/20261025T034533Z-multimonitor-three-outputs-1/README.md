# Three-output QA runtime evidence

- Run: `20261025T034533Z-multimonitor-three-outputs-1`.
- Scenario: `multimonitor/three-outputs`, covering QA #25. It requires
  Hyprland, verifies one each of `Virtual-1`, `Virtual-2`, and `Virtual-3`,
  then checks monitor count, visible Shell bars per screen, and captures all
  three output heads.
- Product: Shell `fa4f5741e246ad04d96874b1de1f442965c11e47`, config
  `76a552f7ec56f00ed52e122150f27639a3a8d70a`, and
  `horneroctl-v0.2.0-preview29 (028a52c)` with SHA-256
  `8e9ffd96d578543d50caa17d9449bb52e79fdf1ae90598fe417f370a263602f5`.
- Image: `studio-shell320`, built 2026-10-25; QEMU 11.1.2; Hyprland 0.56.2;
  three virtual 1280x800 outputs.
- Result: PASS in 73.197 seconds. The setup found all three named outputs,
  Hyprland reported three monitors, the screen-aware Shell probe returned
  `[2,2,2]`, and all three output captures were nonblank.

This run uses the current QA runner with per-head QEMU scanout definitions. It
verifies virtual three-output desktop bring-up; it does not establish physical
hotplug or tablet support.

## Evidence curation

The scenario retains screenshots on every run and logs on failure only. This
passing bundle includes run metadata, the exact scenario, action and assertion
records, result, the three proof screenshots, and screenshot sidecars. Runtime
logs are omitted under that policy. Screenshot SHA-256 values were checked
against their sidecars, and all three screenshots were reviewed for personal
paths, hostnames, account data, credentials, and user media; none were found.
