# Mixed-DPI QA runtime evidence

- Run: `20261024T165723Z-multimonitor-mixed-dpi-two-outputs-1`
- Scenario: `multimonitor/mixed-dpi-two-outputs` from QA PR #30, head
  `127f8f8daae9ed1bfd2f212d3d5a2ed1bd379ee8`.
- Product: shell `85e35a3a9db252d20a64b02096b7f3432152c30e`, config
  `76a552f7ec56f00ed52e122150f27639a3a8d70a`, horneroctl SHA256
  `8e9ffd96d578543d50caa17d9449bb52e79fdf1ae90598fe417f370a263602f5`.
- Image: `qa-display-preview29-20261024`; QEMU 11.1.2; two requested outputs.
- Result: FAIL (product). The guest reports both outputs, but Hyprland reports
  scale 1.6 for the configured 1.5 output. Both visible bars also remain on the
  first output. See the proof records and screenshots.

This run verifies that both requested QEMU scanouts reach the guest and that
the mixed-scale workflow now reaches its product assertions. It does not
establish mixed-DPI support; the scale and bar-placement failures remain open.

## Privacy curation

The original run bundle remains unchanged. This tracked copy includes run
metadata, scenario, actions, assertions, result, report, screenshots, and
screenshot sidecars. It omits serial, journal, process, and application logs,
which contain guest paths, machine or boot identifiers, or unrelated
configuration. Included files were checked for host paths, email addresses,
and machine/boot identifiers; none were found.
