# Control Center panel matrix QA evidence

- Run: `20261025T060015Z-personalization-controlcenter-panel-matrix-1`.
- Scenario: `personalization/controlcenter-panel-matrix`. It opens Settings,
  then uses Find a setting to visit every destination and pauses on each page
  so its first view can be reviewed as a consistent visual set.
- Product: Shell `fa4f5741e246ad04d96874b1de1f442965c11e47`, config
  `76a552f7ec56f00ed52e122150f27639a3a8d70a`, Hornero CLI
  `horneroctl-v0.2.0-preview29 (028a52c)` with SHA-256
  `8e9ffd96d578543d50caa17d9449bb52e79fdf1ae90598fe417f370a263602f5`.
- Image: `studio-shell320`; compositor Hyprland.
- Result: PASS in 151.543 seconds; 54 actions, 21 of 21 proof assertions
  passed. The active-window probes confirmed each destination title:
  Network, Bluetooth, VPN, Appearance, Bars, Layout, Launcher, Dashboard,
  Javi, Audio, Notifications, On-screen display, System, Updates, Terminal,
  and Power.

An earlier attempt the same morning
(`20261025T055544Z-personalization-controlcenter-panel-matrix-1`) was
inconclusive for provisioning only: the guest reached the shell-ready marker
but the observation SSH channel never became reachable, so the scenario ran
zero actions. It is not product evidence and is not archived here.

## Evidence curation

This passing bundle includes run metadata, the exact scenario, action and
assertion records, result, screenshots, and screenshot sidecars. Runtime logs
are omitted under the passing-run curation policy. The screenshots were
reviewed for host paths, account data, hostnames, credentials, and user
media; none were found. This is QEMU virtual evidence for visual review of
the Control Center; it does not establish physical-hardware behavior.
