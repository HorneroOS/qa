# Virtual output disable and reconnect run

- Run: `20261025T053713Z-multimonitor-virtual-output-disable-reconnect-1`
- Result: PASS in 53.479 seconds.
- Image: `studio-shell320` (`studio-shell320.qcow2`), built from `arch-provisioned-yay-20261024.qcow2`.
- Shell: `fa4f5741e246ad04d96874b1de1f442965c11e47`.
- Config: `76a552f7ec56f00ed52e122150f27639a3a8d70a`.
- Hornero CLI: `horneroctl horneroctl-v0.2.0-preview29 (028a52c)`, SHA-256 `8e9ffd96d578543d50caa17d9449bb52e79fdf1ae90598fe417f370a263602f5`.
- Compositor: Hyprland 0.56.2, commit `efb50993780079460b0cbed1363e2166a2de1d9f`.
- Synthetic window client: Kitty 0.49.2. Host kernel: `7.2.9-arch1-1`; QEMU: `11.1.2`.
- Scenario: `multimonitor/virtual-output-disable-reconnect`; exact scenario text is archived here.

The run disabled `Virtual-2` through Hyprland and verified that the Kitty window remained mapped to workspace 2 on the remaining `Virtual-1`. Workspace 1 stayed active, so the scenario used the user action `Super+2` to make the preserved window visible; probes confirmed it was mapped, not hidden, and on the active workspace. After `Virtual-2` was re-enabled, workspace 2 returned to that output, the critical window remained visible, and both heads were captured. The archived state probes show monitor, active workspace, and client identity at each transition.

This is a compositor-level simulation on two virtual QEMU heads. It does not verify QEMU display-device removal, physical display hotplug, mixed DPI, or tablet behavior. Screenshot SHA-256 values are recorded in their sidecars.
