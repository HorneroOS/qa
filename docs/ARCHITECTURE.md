# Hornero QA architecture

Hornero QA is the system-level acceptance and evidence layer for Hornero OS.
It answers one question for a given composition (shell SHA + config SHA +
horneroctl): **did this exact product state run, and did it do what the
scenario says it must?** Every answer comes with an inspectable evidence
bundle.

## 1. Boundary

| Lives here (HorneroOS/qa) | Stays in the owning repo |
|---|---|
| Cross-repository end-to-end scenarios | shell: QML lint, unit/contract tests, `tests/vm` harness, perf harness |
| Graphical OS acceptance in QEMU/KVM | config: validators, materialization, schema tests |
| Visual assertions (anchors) and their references | hornero: CLI tests, composition, manifests, release checklists, `tests/vm/smoke.sh` |
| Evidence bundles, schemas, static run reports | greeter: greeter-local tests and media pipeline |
| Engine adapters (native QEMU/QMP, os-autoinst) | website: build, type-check, lint, page tests |
| Agentic driver + independent reviewer contracts | |
| Release-level graphical acceptance (evidence for hornero checklists) | |
| Cross-product truth checks (website claims vs product data) | |

Hornero QA **calls** the shell's VM harness (`tests/vm/lib`) to compose a
guest; it does not fork it. `HorneroOS/hornero` stays the release authority:
QA produces evidence, the release checklist consumes it.

## 2. Language and dependencies

Python 3.12+ (typed, `mypy --strict`, `ruff`), managed with `uv`.

- The work is QMP sockets, framebuffer images and JSON/YAML data. NumPy and
  Pillow give exact, testable image maths (ZNCC, Oklab, frame diffs) that V
  has no libraries for, and a Node runtime would add nothing a host tool needs.
- The organization already runs Python in CI (`hornero/scripts/check-*.py`,
  shell `pytest`), so contributors and runners need no new toolchain.
- Shell scripts are limited to guest-side session glue (`guest/`).

Runtime dependencies are deliberately few: `numpy`, `pillow`, `pyyaml`,
`jsonschema`. No database, no service, no daemon.

## 3. Pipeline

```text
scenario (YAML, reviewed)            image (ready qcow2 @ shell+config SHAs)
        │                                         │
        ▼                                         ▼
     runner ──── budgets, repeats ────►  engine adapter
        │                                ├─ native   (QEMU + QMP: HID input, screendump)
        │                                └─ os-autoinst (container, process boundary) [evaluated, not default]
        ▼
  steps: input │ wait (screen change / stable) │ assert (anchor, probe) │ capture
        │
        ▼
  evidence bundle ──► result (taxonomy) ──► static HTML report
        │
        └─► optional: agentic driver (black box) + independent reviewer
```

### Two lanes, never mixed

- **Action lane**: what a user can do. QMP HID key/pointer events into the
  emulated keyboard and tablet. Scenarios that test UX may only act here.
- **Observation lane**: what the harness may read to *prove* a result.
  Framebuffer screenshots (QMP `screendump`) and read-only guest probes over
  SSH (`qs ipc call ...`, `busctl`, files). Probes never perform the
  scenario's action.

This is the "instruction vs proof" split: the instruction is executed through
the action lane; the proof is checked through the observation lane.

## 4. Engines

| Engine | Status | Strengths | Limits |
|---|---|---|---|
| `native` | **default** | Real HID input via QMP, colour-aware anchors (Oklab probes), sharp failure taxonomy, no container | Single host, no needle editor |
| `os-autoinst` | evaluated, adapter planned | Mature QEMU automation, needles, video, openQA interop | 1.34 GB container, grayscale matching (blind to colour-only regressions), slower |

Evidence (bake-off 2026-10-01, 20 interleaved runs, same ready image and
launcher journey): native detected 3/3 injected fault classes, isotovideo
2/3 (it passed a colour-only regression). Wall time per run: native median
~21 s, isotovideo ~36 s. Raw data: `docs/evidence/bakeoff-2026-10-01.tsv`.

**Full openQA is not deployed.** Adopt it only when several of these become
real at once: more than 4 worker slots, multi-host workers, a hardware lab,
multi-machine tests, large ISO × hardware matrices, a public historical
dashboard, distributed interactive debugging.

## 5. Scenario model

Scenarios are product data (`scenarios/**/*.yaml`, validated against
`schemas/scenario.schema.json`). Acceptance criteria are written by humans
and reviewed in PRs; the runner never invents them.

```yaml
id: layouts/apply-cockpit-clear
purpose: Switch to Cockpit Clear from the Layout Picker using only the keyboard.
requires: {engine: native, outputs: 1}
setup:
  layout: hornero-left
instruction: Open the Layout Picker and apply Cockpit Clear.
steps:
  - key: super+shift+b
  - wait: {changed: true, stable: 0.5, timeout: 5}
  ...
proof:
  - probe: {run: "horneroctl shell preset current", equals: cockpit-clear}
  - screenshot: final
budget: {wall_s: 120}
artifacts: {screenshots: always, logs: on-failure}
```

## 6. Evidence bundle

One directory per run:

```text
runs/<run-id>/
  run.json          provenance: scenario, QA SHA, shell/config/hornero SHAs,
                    image digest, engine, resolution, layout, theme, host
  scenario.yaml     exact scenario text that ran
  actions.jsonl     every action + observation with timestamps (intent log)
  assertions.json   every proof check with verdict and measurements
  result.json       verdict + taxonomy class + timings
  screenshots/      NNN-<name>.png (+ <name>.json sidecar provenance)
  logs/             serial, hyprland, quickshell, journal (policy-driven)
  report.html       static human report (no JS required)
```

Screenshots carry sidecar provenance so the website can promote certified
media without guessing what a picture shows (`docs/MEDIA.md`).

## 7. Failure taxonomy

| Class | Meaning |
|---|---|
| `pass` | every proof check passed |
| `product` | the product misbehaved (proof failed, guest healthy) |
| `product_crash` | compositor or shell process died |
| `driver` | the agentic driver/model failed (malformed output, gave up, budget) |
| `harness` | Hornero QA itself failed (exception, capture error) |
| `provisioning` | image/composition could not be prepared |
| `boot` | guest did not reach a desktop |
| `timeout` | wall-time budget exceeded without a verdict |
| `inconclusive` | evidence insufficient (e.g. reviewer cannot decide) |

Repeat runs (`--repeat N`) report counts per class, so a model miss is never
reported as a Hornero regression.

## 8. Agentic QA

Optional, model-agnostic. A **driver adapter** (any executable speaking the
JSON contract in `docs/AGENTIC.md`) receives the instruction and the current
screenshot and returns one action at a time; it has no SSH, no IPC and no
source access. A separate **reviewer adapter** receives the scenario, proof
criteria, screenshots, action trace and deterministic assertions and returns
PASS / FAIL / INCONCLUSIVE. Driver PASS + reviewer FAIL is a FAIL that needs
inspection; it is never upgraded.

## 9. CI lanes

| Lane | When | What |
|---|---|---|
| fast | every PR | ruff, mypy, pytest (schemas, parsers, vision maths, taxonomy, report), scenario validation |
| graphical | manual dispatch / pre-release, on a KVM host | real scenarios against a ready image; bundles uploaded as artifacts |

GitHub-hosted runners have no KVM: graphical runs happen on a KVM host and
their bundles are attached to the release evidence.
