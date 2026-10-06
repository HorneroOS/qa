# Writing scenarios

A scenario is reviewed product data: what a user does (**instruction**),
the deterministic actions that do it (**steps**), and how we know it worked
(**proof**). The schema is `src/hornero_qa/schemas/scenario.schema.json`;
`uv run hornero-qa validate` checks every file.

## Rules

- `id` equals the path under `scenarios/` without `.yaml`.
- Proof uses the observation lane only: probes, anchors, screenshots. A step
  may never be the only evidence for an outcome.
- Probes are read-only. Mutations belong in `setup`.
- Prefer `wait` (screen synchronisation) and `probe` with `retry_s` over
  `pause`; `pause` is capped at 3 seconds.
- `covers` lists the issues/PRs a scenario guards (`shell#94`). A scenario
  that guards a fix must fail on the commit before the fix.

## Setup

| Key | Effect |
|---|---|
| `layout` | `horneroctl shell preset apply <name> --yes` |
| `theme` | `horneroctl appearance theme set <name> --yes` |
| `compositor` requirement | Requires an image sidecar with the same compositor; the runner refuses mismatched images |
| `commands` | extra guest commands, run in order; any non-zero exit is a `harness` failure |

`layout` and `theme` go through the product CLI, so their failure is a
`product` failure (the product could not do it); a failing `commands` entry
is a `harness` failure (the scenario's own preparation broke).

## Steps (exactly one action each, optional `note`)

| Step | Meaning |
|---|---|
| `key: super+shift+b` | key chord through the virtual keyboard (US layout) |
| `type: text` | type text, one chord per character |
| `pointer: {x, y, click?, glide?}` | absolute pointer in normalized output coordinates (0..1); `glide` approaches from above in N moves so hover enters like a real pointer |
| `scroll: N` | wheel steps (negative = up) |
| `wait: {changed?, stable?, timeout?, ignore?}` | `changed`: until the screen differs from the frame before the last action (PSNR < 45 dB); `stable`: until the screen is still for N seconds (PSNR >= 50 dB). Timeouts are recorded, not asserted |
| `probe: {...}` | a gate: read-only guest command that must hold (same matchers as proof) |
| `anchor: {id, expect?, timeout?}` | a gate: visual anchor present/absent |
| `screenshot: name` | keep a frame in the bundle |
| `pause: s` | last resort, at most 3 s |

## Proof checks

| Check | Passes when |
|---|---|
| `probe: {run, equals/contains/matches/not_contains/json, retry_s?, save?}` | the matcher holds (no matcher: exit status 0). `json: a.0.b` digs into JSON stdout and compares with `equals`; `save: name` keeps the full stdout as `logs/<name>` |
| `anchor: {id, expect, timeout?}` | the anchor (`anchors/<id>.json` + `.png`) matches within its search margin, including colour probes against the shell's design tokens |
| `screenshot: name` | a non-blank frame was captured on every output |

## Verdicts

`pass` when every proof check passes. A failed check or step gate is a
`product` failure; a dead shell process is `product_crash`; everything the
product cannot be blamed for (`harness`, `boot`, `provisioning`, `timeout`,
`driver`) is `inconclusive`. Exit codes: 0 pass, 1 any fail, 2 inconclusive
only, 64 usage error.

## Anchors

Cut anchors only from certified frames of a passing run, leaving a margin of
background around the widget (the outermost two pixels of a crop are
excluded from structure matching):

```sh
uv run hornero-qa anchor cut runs/<run>/screenshots/003-launcher.png \
  --id launcher/search-field --rect 400,180,480,60 --tag launcher
```

The anchor records the source run, product SHAs and capture SHA-256. Add
`color_probes` by hand, naming tokens from the shell's `Colours.qml`, so a
recolour is caught even when the structure still matches.
