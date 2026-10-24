# Two-output QA runtime evidence

- Run: `20261024T165406Z-multimonitor-two-outputs-1`
- Scenario: `multimonitor/two-outputs` from QA main at `c84961ed71ab84c4fe535459d6bca1348d062a73`.
- Product: shell `85e35a3a9db252d20a64b02096b7f3432152c30e`, config
  `76a552f7ec56f00ed52e122150f27639a3a8d70a`, horneroctl SHA256
  `8e9ffd96d578543d50caa17d9449bb52e79fdf1ae90598fe417f370a263602f5`.
- Image: `qa-display-preview29-20261024`; QEMU 11.1.2; two requested outputs.
- Result: the raw runner marked this FAIL (product) after its bar probe reported
  only the first screen's two bars. The second screenshot visibly contains its
  bar as well, so that classification is a false negative from screen-scoped
  debug instrumentation, not evidence of a Shell layout failure. See the proof
  records and screenshots.

This verifies that the native engine enables the two requested QEMU scanouts.
`debug bars` is registered inside each per-screen drawer scope and serializes
only that scope's `BarSet`; `qs ipc call debug bars` therefore does not provide
an aggregate across outputs. The Shell diagnostics contract needs a per-screen
aggregate before the acceptance scenario can make a deterministic bar-placement
assertion.

## Privacy curation

The original run bundle remains unchanged. This tracked copy includes run
metadata, scenario, actions, assertions, result, report, screenshots, and
screenshot sidecars. It omits serial, journal, process, and application logs,
which contain guest paths, machine or boot identifiers, or unrelated
configuration. Included files were checked for host paths, email addresses,
and machine/boot identifiers; none were found.
