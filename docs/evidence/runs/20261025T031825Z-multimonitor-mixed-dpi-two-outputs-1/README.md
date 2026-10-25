# Mixed-scale two-output QA evidence

- Run: `20261025T031825Z-multimonitor-mixed-dpi-two-outputs-1`.
- Scenario: `multimonitor/mixed-dpi-two-outputs` in this PR. `Virtual-1` uses
  1280x800 at scale 1; `Virtual-2` uses 1920x1080 at scale 1.5.
- Product: Shell `fa4f5741e246ad04d96874b1de1f442965c11e47`, config
  `76a552f7ec56f00ed52e122150f27639a3a8d70a`, Hornero CLI
  `horneroctl-v0.2.0-preview29 (028a52c)` with SHA-256
  `8e9ffd96d578543d50caa17d9449bb52e79fdf1ae90598fe417f370a263602f5`.
- Image: `studio-shell320`; QEMU 11.1.2; Hyprland 0.56.2; two virtual
  outputs.
- Result: PASS. Hyprland reports scales 1 and 1.5, the screen-aware Shell
  probe reports two visible bars on each output (`[2,2]`), and both captured
  outputs contain the desktop.

Hyprland 0.56.2 checks that `mode / scale` yields integer logical dimensions
and adjusts scales that would produce fractional pixels ([source](https://github.com/hyprwm/Hyprland/blob/v0.56.2/src/output/Monitor.cpp#L3721-L3728)).
At 1280x800, scale 1.5 gives fractional dimensions; the earlier run observed
Hyprland select 1.6. At 1920x1080, scale 1.5 gives 1280x720 logical pixels,
so the requested scale remains exact. This is virtual two-output evidence; it
does not establish physical hotplug or general display-hardware support.

## Evidence curation

The scenario retains screenshots on every run and logs on failure only. This
passing bundle includes run metadata, the exact scenario, action and assertion
records, result, screenshots, and screenshot sidecars. Runtime logs are omitted
under that policy. Both screenshot SHA-256 values were checked against their
sidecars. The included files and images were reviewed for host paths, account
data, hostnames, credentials, and user media; none were found.
