# Three-output QA runtime evidence

- Run: `20261024T175312Z-multimonitor-three-outputs-1`.
- Scenario: `multimonitor/three-outputs` from this PR.
- Product: Shell `37a09b31b1cf7f10206b13a20d355e4bf5730cc4`, config
  `76a552f7ec56f00ed52e122150f27639a3a8d70a`, and verified
  `horneroctl-v0.2.0-preview29` (SHA-256
  `8e9ffd96d578543d50caa17d9449bb52e79fdf1ae90598fe417f370a263602f5`).
- Image: `studio-shell-debug-preview29-20261024`; QEMU 11.1.2; Hyprland;
  three `1280x800` outputs.
- QA runner: commit
  `ce62b043b63132dc79c48a0d15e9075ddda06f78` from QA #31, which adds explicit
  QEMU output definitions for each requested scanout.
- Result: PASS. Hyprland reported three monitors, and screenshots from all
  three heads were captured and verified nonblank. Each screenshot was reviewed
  and shows the desktop and its bar.

The earlier run `20261024T160629Z-multimonitor-three-outputs-1` used the QA
runner before per-head QEMU output definitions and exposed only one guest
monitor. This run confirms virtual three-output bring-up with the updated QA
engine. It does not establish physical hotplug or tablet support.

## Privacy curation

This tracked bundle contains run metadata, scenario, actions, assertions,
result, screenshots, and screenshot sidecars. The scenario retains diagnostic
logs only on failure; this passing run therefore has no required log artifacts.
The HTML report and the runner's local diagnostic logs are not included because
they contain guest paths, machine or boot identifiers, or unrelated
configuration. Screenshot sidecar hashes were verified against their PNG
files. Included text metadata and screenshots were reviewed for personal
paths, hostnames, email addresses, and machine or boot identifiers; none were
found.
