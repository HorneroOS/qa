# Two-output Studio desktop run

- Run: `20261025T035600Z-multimonitor-two-outputs-1`
- Result: PASS in 72.916 seconds; two configured heads and two visible shell bars per screen.
- Image: `studio-shell320` (`studio-shell320.qcow2`), built from `arch-provisioned-yay-20261024.qcow2`.
- Shell: `fa4f5741e246ad04d96874b1de1f442965c11e47`.
- Config: `76a552f7ec56f00ed52e122150f27639a3a8d70a`.
- Hornero CLI: `horneroctl horneroctl-v0.2.0-preview29 (028a52c)`, SHA-256 `8e9ffd96d578543d50caa17d9449bb52e79fdf1ae90598fe417f370a263602f5`.
- Host kernel: `7.2.9-arch1-1`; QEMU: `11.1.2`; compositor: Hyprland.
- Scenario: `multimonitor/two-outputs`; exact scenario text is archived in this directory.

The setup precondition found exactly one `Virtual-1` and one `Virtual-2`. Hyprland reported two monitors; the Shell probe reported `[2,2]` visible bars grouped by owning screen; captures for both heads were produced and visually reviewed. PNG SHA-256 values are recorded in each screenshot sidecar.

This validates two virtual QEMU heads on the pinned image. It does not verify physical display hotplug, mixed DPI, or tablet behavior. Logs were retained by the local run but are omitted from this passing evidence bundle; the scenario requests logs on failure.
