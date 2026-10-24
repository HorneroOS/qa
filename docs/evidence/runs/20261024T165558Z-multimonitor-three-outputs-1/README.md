# Three-output QA runtime evidence

- Run: `20261024T165558Z-multimonitor-three-outputs-1`
- Scenario: `multimonitor/three-outputs` from QA PR #29, head
  `851bbfeaeb4082a480bae63d9f6f4bdf82f6b1ad`
- Product: shell `85e35a3a9db252d20a64b02096b7f3432152c30e`, config
  `76a552f7ec56f00ed52e122150f27639a3a8d70a`, horneroctl SHA256
  `8e9ffd96d578543d50caa17d9449bb52e79fdf1ae90598fe417f370a263602f5`
- Image: `qa-display-preview29-20261024`; QEMU 11.1.2; three requested outputs.
- Result: PASS. Hyprland reported three outputs and the runner captured nonblank
  screenshots for heads 0, 1, and 2. See `assertions.json`, `result.json`, and
  `report.html`.

This run exercises the native engine's per-output QEMU configuration. The
scenario file was copied unchanged from PR #29 into the isolated verification
worktree for this run. The run demonstrates that all three virtual heads reach
the guest and can be captured; it does not establish physical display hotplug,
tablet behavior, or bar placement on each output.

## Privacy curation

The original run bundle remains unchanged. This tracked copy includes the run
metadata, exact scenario, action/assertion records, result, report, screenshots,
and screenshot sidecars. It omits serial, journal, process, and application logs,
which contain guest account paths, machine or boot identifiers, or unrelated
configuration. The included files were checked for host paths, email addresses,
and machine/boot identifiers; none were found.
