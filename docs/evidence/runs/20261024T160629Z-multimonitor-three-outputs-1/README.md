# Studio display run evidence

- Run: `20261024T160629Z-multimonitor-three-outputs-1`
- Scenario: `multimonitor/three-outputs`
- Started: `2026-10-24T16:06:29Z`; finished: `2026-10-24T16:07:51Z` (81.1s)
- Product pins: shell `85e35a3a9db252d20a64b02096b7f3432152c30e`, config
  `76a552f7ec56f00ed52e122150f27639a3a8d70a`, horneroctl
  `8e9ffd96d578543d50caa17d9449bb52e79fdf1ae90598fe417f370a263602f5`
- Image: `qa-display-preview29-20261024`; configured outputs: 3; guest result: guest exposed one
  active output.
- Result: `fail` / `product`. See `result.json`, `assertions.json`, screenshots, and `report.html`
  for the recorded proof.

This is a failed acceptance run, not a support claim. It records the exact Preview 29 composition
and configured virtual-output count. The observed one-output guest behavior prevents this run from
establishing Studio multi-output support or a product regression independently of the
runner/environment.

## Privacy curation

The original local run bundle remains unchanged. This tracked copy includes its run metadata,
scenario, action and assertion records, result, report, all screenshot files and screenshot
sidecars. The retained Hyprland, Quickshell, and shell-status logs have home-directory paths
replaced with `$HOME` and email-shaped strings redacted; trailing whitespace was removed from the
Hyprland ASCII banner. Journals, serial console, process snapshots, and captured `Colours.qml` were
excluded because they contained guest account/network identifiers, machine or boot identifiers, or
an unrelated user configuration dump.
