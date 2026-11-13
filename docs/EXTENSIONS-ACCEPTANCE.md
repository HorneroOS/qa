# Extension Premium Acceptance Matrix (qa#81)

Status: **all scenarios PENDING — none has been executed yet.** This file is
the one acceptance matrix for Extensions 2.0 work across `HorneroOS/shell`
(#369–#380, #222, #366) and `HorneroOS/plugins`. Source tests in those repos
cannot satisfy the runtime gaps acknowledged in shell#222 and shell#366, so
every row below needs guest evidence: a complete run bundle
(`docs/ARCHITECTURE.md` §6) whose `result.json` verdict is the only thing
that may turn a row PASS in `docs/SCENARIO-MATRIX.md`. A scenario that has
not run stays **PENDING / Never executed**, never silently PASS.

Run the repo checks with:

```sh
uv run hornero-qa validate
uv run hornero-qa matrix --check
uv run pytest tests/test_extensions_scenarios.py
```

## Fixture requirement (ready image)

The scenarios assume a ready image (shell + config at pinned SHAs, a
`horneroctl` build that accepts manifest `schemaVersion` 2) whose guest
user has these fixture extensions **installed, trusted and enabled** through
the normal `horneroctl plugin` lifecycle before the run. All five are
the shell repo's reference packages (`examples/plugins/` in
`HorneroOS/shell`); the fifth, `example-broken`, landed on shell `main`
in shell PR #395 (merge `07d8d1d`):

| Fixture id | Shape | Used for |
|---|---|---|
| `example-clock` | v1, `bar`, boolean setting `twentyFourHour`, marketplace metadata, ES catalog | discovery, settings, marketplace, lifecycle, edges |
| `example-multi-surface` | v2, `bar` primary + `dashboard` surface, string setting | multi-surface, restart persistence |
| `example-dashboard-note` | `dashboard` card | dashboard stress, restart persistence |
| `example-desktop-note` | `desktop` widget (disposable) | desktop slots, uninstall cleanup |
| `example-broken` | exists on shell `main` @ `07d8d1d` (shell PR #395, `examples/plugins/example-broken`): validator-clean manifest, entrypoint deterministically fails to load (`tests/test_plugin_broken_fixture.py`) | load-failure isolation |

Until a ready image carries the fixture, `extensions/load-failure-isolation`
cannot run at all, and every other scenario's fixture precondition probe
fails honestly rather than passing vacuously (e.g. "no failed extensions"
is always paired with "at least one loaded"). Fixture installation is image
composition work (shell `tests/vm/lib` at a pinned SHA, per `AGENTS.md`);
this repo does not fork that harness.

## Waves

**Foundation wave** — probe-assertable through the observation lane
(`qs ipc call plugins status`, `horneroctl plugin list --json`,
`shell.json`). Run these first in the next approved KVM window; per qa#81
they must be executed with recorded bundle evidence before this matrix can
claim anything. They are listed here in run order:

1. `extensions/discovery-status`
2. `extensions/multi-surface-loads`
3. `extensions/settings-persistence`
4. `extensions/malformed-settings-resilience`
5. `extensions/safe-mode-recovery`
6. `extensions/load-failure-isolation` (needs the `example-broken` fixture, now on shell `main` @ `07d8d1d`; still needs a ready image carrying it)
7. `extensions/lifecycle-disable-enable`
8. `extensions/uninstall-cleanup`
9. `extensions/restart-persistence`
10. `extensions/marketplace-metadata`
11. `extensions/offline-unavailable-services`

**Visual / interaction wave** — probes assert liveness, layout edges,
display geometry and persisted state, but the premium claim (tooltip
opens inward, focus is visible, light-theme tokens, compact/HiDPI
rendering) is **screenshot-review evidence**: a reviewer compares the
bundle frames against the requirement in the evidence column. For the four
`bar-edge-*` scenarios the tooltip/popover hover itself is a manual
reviewer journey (the `MANUAL` note steps) because no probe exposes
tooltip geometry today; a deterministic bundle alone must never be
recorded as the visual PASS.

## Matrix

| Scenario | Wave | Covers (qa#81 dimension) | Evidence required for PASS | Status |
|---|---|---|---|---|
| `extensions/discovery-status` | foundation | extension load errors (healthy baseline), PluginKit runtime (shell#222) | Bundle: IPC/CLI id agreement, `plugins-status.json` saved probe, desktop screenshot | PENDING |
| `extensions/multi-surface-loads` | foundation | multi-surface plugins (shell#373) | Bundle: v1+v2 both `loaded`, dashboard screenshot showing the v2 card | PENDING |
| `extensions/settings-persistence` | foundation | settings UI (shell#374), restart persistence | Bundle: stored `twentyFourHour=false` after restart; screenshot-review that the generated Extensions settings field shows the same value | PENDING |
| `extensions/malformed-settings-resilience` | foundation | load errors from stored state (shell#222/#374/#378) | Bundle: shell alive, fixture `loaded`, 0 config errors over malformed `shell.json` | PENDING |
| `extensions/safe-mode-recovery` | foundation | safe mode / diagnostics (shell#380) | Bundle: `safeMode=true`, `loaded=0`, core IPC alive, reload refused, lifecycle untouched | PENDING |
| `extensions/load-failure-isolation` | foundation | extension load errors (shell#380) | Bundle with the broken fixture: `failed` isolated, bounded redacted diagnostics, neighbour `loaded` | PENDING |
| `extensions/lifecycle-disable-enable` | foundation | disable cleanup | Bundle: disable → `disabled` → enable → `loaded` probe sequence | PENDING |
| `extensions/uninstall-cleanup` | foundation | uninstall cleanup | Bundle: removed id absent from CLI list and IPC status, neighbours healthy | PENDING |
| `extensions/restart-persistence` | foundation | restart persistence, dashboard layout (shell#378), desktop slots (shell#222) | Bundle: `dashboardLayout` + `desktopWidgetSlots` verbatim after restart, dashboard screenshot | PENDING |
| `extensions/marketplace-metadata` | foundation | marketplace metadata (shell#366/#379), offline registry | Bundle: normalized preview/compatibility/changelog in status; community list refused while no product key ships | PENDING |
| `extensions/dashboard-all-enabled-stress` | visual | all-dashboard-extensions-enabled stress (shell#378) | Bundle: every enabled fixture `loaded`, no churn flags; screenshot-review of grouping/scroll with all cards | PENDING |
| `extensions/keyboard-only` | visual | keyboard-only use (shell#370/#376/#378) | Bundle: keyboard pin persisted (exactly 1 pinned), Escape closed drawer; screenshot-review of visible focus ring | PENDING |
| `extensions/themes-reduced-motion` | visual | themes, reduced motion (shell#369/#376) | Bundle: `hornero-light` active, anim scale 0; screenshot-review of bar + dashboard token colours under light | PENDING |
| `extensions/bar-edge-left` | visual | four bar edges + tooltip placement (shell#370/#371/#372) | Bundle + MANUAL reviewer frames: tooltip/popover open inward from the left rail, unclipped | PENDING |
| `extensions/bar-edge-right` | visual | four bar edges + tooltip placement | Bundle + MANUAL reviewer frames: tooltip/popover open inward from the right rail, unclipped | PENDING |
| `extensions/bar-edge-top` | visual | four bar edges + tooltip placement | Bundle + MANUAL reviewer frames: tooltip/popover open below the top bar, unclipped | PENDING |
| `extensions/bar-edge-bottom` | visual | four bar edges + tooltip placement | Bundle + MANUAL reviewer frames: tooltip/popover open above the bottom dock, unclipped | PENDING |
| `extensions/narrow-display` | visual | narrow displays (shell#372) | Bundle at 800x600@1; screenshot-review of compact bar/dashboard (no clipped labels) | PENDING |
| `extensions/hidpi-wide-display` | visual | wide displays, HiDPI (shell#372) | Bundle at 1920x1080@1.5; screenshot-review of logical-size rendering | PENDING |
| `extensions/multimonitor-virtual` | visual | multi-monitor (**virtual outputs only**) | Bundle on Virtual-1/2 at scales 1/1.5, bars on both outputs; screenshot per head | PENDING |
| `extensions/offline-unavailable-services` | foundation | offline/unavailable services (shell#377) | Bundle: weather unconfigured, discovery error empty, provider fixtures `loaded` | PENDING |

## NOT TESTED — never claim from the rows above

- **Physical multi-monitor, hotplug, disconnect fallback, physical
  HiDPI panels.** The multi-output and HiDPI rows use QEMU virtual outputs
  only. Physical claims need an owner-approved hardware fixture that does
  not exist in this repo today.
- **Live compositor focus grabs and screen-reader (AT-SPI) announcements**
  for tooltips and popovers. The QML-level keyboard probe lives in the
  shell repo; the live audit remains shell#221. The keyboard row here proves
  key-driven navigation and persistence, not announcements.
- **Tooltip/popover geometry** as a deterministic assertion. No IPC exposes
  it today; placement on all four edges is manual screenshot-review
  evidence until a probe or certified anchor exists (anchors may only be
  cut from certified frames of a passing run, `docs/SCENARIOS.md`).
- **Community catalogue install/update/rollback from the pane** while no
  registry product key ships (shell `docs/PLUGINS.md`): discovery must fail
  closed, and the marketplace row asserts exactly that.
- **`launcher` / custom `settings` surfaces.** Manifest v2 validates these
  declarations but no host loads them yet; nothing here claims they run.

## Recording results

After an approved KVM window, update `docs/scenario-triage.yaml` first
(decision, rationale, what actually ran), regenerate the matrix
(`uv run hornero-qa matrix --output docs/SCENARIO-MATRIX.md`), and set the
Status column above to match the bundle verdict. A row whose bundle is
missing, incomplete or only a screenshot sidecar stays PENDING — screenshot
sidecars without a complete run result are never PASS.
