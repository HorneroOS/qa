# Mixed-scale two-output QA evidence

- Run: `20261024T174334Z-multimonitor-mixed-dpi-two-outputs-1`.
- Scenario: `multimonitor/mixed-dpi-two-outputs` in this PR. It requests
  `Virtual-1` at scale 1 and `Virtual-2` at scale 1.5, and groups visible bars
  by the Shell IPC `screen` field.
- Product: Shell `37a09b31b1cf7f10206b13a20d355e4bf5730cc4`, config
  `76a552f7ec56f00ed52e122150f27639a3a8d70a`, Hornero CLI
  `horneroctl-v0.2.0-preview29 (028a52c)` with SHA-256
  `8e9ffd96d578543d50caa17d9449bb52e79fdf1ae90598fe417f370a263602f5`.
- Image: `studio-shell-debug-preview29-20261024`; QEMU 11.1.2; Hyprland
  0.56.2; two `1280x800` outputs.
- Result: FAIL on the requested scale. The guest reports
  `[Virtual-1: 1, Virtual-2: 1.6]` after the scenario applies scale 1.5.
  The two-output assertion and screenshot captures pass, and visible bars group
  as `[2,2]` across the two screens.

This run confirms that the fixed `1280x800` mode adjusts the requested scale.
Hyprland requires integer logical dimensions: at 1280x800, scale 1.5 produces
fractional pixels, so the compositor selects the nearest valid scale, 1.6.
The follow-up run
[`20261025T031825Z`](../20261025T031825Z-multimonitor-mixed-dpi-two-outputs-1/README.md)
uses 1920x1080 at scale 1.5 (1280x720 logical) and passes. This virtual result
does not establish physical hotplug or general mixed-DPI support.

## Privacy curation

The original run bundle remains unchanged. This tracked copy includes run
metadata, scenario, actions, assertions, result, screenshots, and screenshot
sidecars. Serial, journal, process, compositor, and Shell logs plus the HTML
report were omitted because they contain guest paths, machine or boot
identifiers, or unrelated configuration. Each screenshot sidecar SHA-256 was
verified against its PNG. Included text metadata and screenshots were reviewed
for personal paths, hostnames, email addresses, and machine or boot
identifiers; none were found.
