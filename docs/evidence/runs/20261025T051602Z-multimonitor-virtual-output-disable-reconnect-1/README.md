# Virtual output disable and reconnect run

- Run: `20261025T051602Z-multimonitor-virtual-output-disable-reconnect-1`
- Result: PASS in 54.122 seconds.
- Image: `studio-shell320` (`studio-shell320.qcow2`), built from `arch-provisioned-yay-20261024.qcow2`.
- Shell: `fa4f5741e246ad04d96874b1de1f442965c11e47`.
- Config: `76a552f7ec56f00ed52e122150f27639a3a8d70a`.
- Hornero CLI: `horneroctl horneroctl-v0.2.0-preview29 (028a52c)`, SHA-256 `8e9ffd96d578543d50caa17d9449bb52e79fdf1ae90598fe417f370a263602f5`.
- Host kernel: `7.2.9-arch1-1`; QEMU: `11.1.2`; compositor: Hyprland.
- Scenario: `multimonitor/virtual-output-disable-reconnect`; exact scenario text is archived here.

The scenario disabled the `Virtual-2` output through Hyprland, observed one active monitor, and verified the synthetic Kitty window remained mapped to that active output. It then re-enabled `Virtual-2`, verified both named outputs, rechecked the window mapping, and captured both heads. PNG SHA-256 values are recorded in each screenshot sidecar.

This is a compositor-level simulation using two virtual QEMU heads. It does not verify QEMU device removal, physical display hotplug, mixed DPI, or tablet behavior. Curated command outputs used by the assertions are retained under `logs/`; broader VM logs remain in the local QA run bundle.
