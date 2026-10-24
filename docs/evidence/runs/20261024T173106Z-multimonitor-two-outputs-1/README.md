# Two-output per-screen bar diagnostics

- Run: `20261024T173106Z-multimonitor-two-outputs-1`.
- Scenario: `multimonitor/two-outputs` in this PR; groups visible bars by the
  `screen` field returned by `debug bars()`.
- Product: Shell `37a09b31b1cf7f10206b13a20d355e4bf5730cc4`, config
  `76a552f7ec56f00ed52e122150f27639a3a8d70a`, Hornero CLI
  `horneroctl-v0.2.0-preview29 (028a52c)` with SHA-256
  `8e9ffd96d578543d50caa17d9449bb52e79fdf1ae90598fe417f370a263602f5`.
- Image: `studio-shell-debug-preview29-20261024`; QEMU 11.1.2; Hyprland;
  two `1280x800` outputs.
- Result: PASS. The guest reports two outputs, two distinct screen names, and
  two visible `cockpit-clear` bars grouped under each screen (`[2,2]`). Both
  screenshots visibly show the Shell bar.

This run verifies the Shell debug IPC contract and the two-output layout on a
virtual display using the isolated QA image builder. It does not establish
physical hotplug or mixed-DPI support, and it does not satisfy the broader
Studio readiness gate.

## Privacy curation

The original bundle remains unchanged. This tracked copy includes run metadata,
the scenario, actions, assertions, result, screenshots, and screenshot
sidecars. Serial, journal, process, compositor, and Shell logs plus the HTML
report were omitted because they contain guest paths, machine or boot
identifiers, or unrelated configuration. Each screenshot sidecar SHA-256 was
verified against its PNG. Included text metadata and screenshots were reviewed
for personal paths, hostnames, email addresses, and machine or boot
identifiers; none were found.
