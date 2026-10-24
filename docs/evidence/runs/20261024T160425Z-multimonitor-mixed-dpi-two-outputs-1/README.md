# Earlier mixed-scale run (runner heads not enabled)

- Run: `20261024T160425Z-multimonitor-mixed-dpi-two-outputs-1`.
- Scenario: `multimonitor/mixed-dpi-two-outputs` before the QA native engine
  configured each QEMU virtio-gpu output.
- Product: shell `85e35a3a9db252d20a64b02096b7f3432152c30e`, config
  `76a552f7ec56f00ed52e122150f27639a3a8d70a`, Hornero CLI SHA-256
  `8e9ffd96d578543d50caa17d9449bb52e79fdf1ae90598fe417f370a263602f5`.
- Image: `qa-display-preview29-20261024`; two outputs requested.
- Raw result: `fail` / `product`; the guest did not expose the requested second
  output, so scale, bar-placement, and screenshot assertions were not
  independent product evidence.

The original run used a QA engine configuration that set `max_outputs` but did
not configure the secondary virtio-gpu scanout. QA #31 corrects that runner
configuration. See the later [mixed-scale run](../20261024T174334Z-multimonitor-mixed-dpi-two-outputs-1/README.md)
for evidence from two enabled outputs: both screens and their bars pass, while
the requested 1.5 scale reads back as 1.6. That mismatch remains unresolved.

## Privacy curation

The original local run bundle remains unchanged. This tracked copy includes its
run metadata, scenario, action and assertion records, result, report, all
screenshot files and screenshot sidecars. The retained Hyprland, Quickshell,
and shell-status logs have home-directory paths replaced with `$HOME` and
email-shaped strings redacted; trailing whitespace was removed from the
Hyprland ASCII banner. Journals, serial console, process snapshots, and
captured `Colours.qml` were excluded because they contained guest
account/network identifiers, machine or boot identifiers, or an unrelated
user configuration dump.
