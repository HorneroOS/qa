# Hornero QA

System-level graphical, end-to-end, visual and agentic acceptance for
[Hornero OS](https://github.com/HorneroOS).

Hornero QA boots a real Hornero composition (shell + config + horneroctl at
exact SHAs) in QEMU/KVM, drives it through the keyboard and pointer like a
user, proves outcomes with screenshots, visual anchors and read-only guest
probes, and writes an evidence bundle for every run.

> The website says "this is Hornero OS". Hornero QA answers "this exact state
> existed, ran and was tested".

## Status

Native engine, scenario/evidence model, compositor-specific ready-image
builder for Hyprland and Niri, and the first product journeys (smoke, layouts,
Layout Picker, drawers, notifications, lock, themes, regressions, perf) run
today, deterministically or with model-agnostic agentic adapters
([docs/AGENTIC.md](docs/AGENTIC.md)). See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md),
[docs/SCENARIOS.md](docs/SCENARIOS.md), [docs/IMAGES.md](docs/IMAGES.md) and
[docs/MEDIA.md](docs/MEDIA.md).

The tracked scenario execution ledger is [docs/SCENARIO-MATRIX.md](docs/SCENARIO-MATRIX.md).
Regenerate it with `uv run hornero-qa matrix`; CI checks it without starting a VM.
Record a keep/fix/retire decision for every scenario in
[docs/scenario-triage.yaml](docs/scenario-triage.yaml). Only complete run bundles
can produce PASS/FAIL results; screenshot provenance alone is reported as
unverified evidence.

The Studio evidence gate is separate from the scenario execution ledger. It
fails closed until every required Studio outcome has owner-approved fixtures,
complete pinned evidence bundles, and human review. It can recommend owner
review; it never changes Hornero's edition maturity. See
[docs/STUDIO-ACCEPTANCE.md](docs/STUDIO-ACCEPTANCE.md).

## Quick start

Requirements: Linux host with `/dev/kvm`, QEMU, `uv`, and a Hornero QA ready
image (see [docs/IMAGES.md](docs/IMAGES.md)).

```sh
uv run hornero-qa doctor            # host checks (KVM, QEMU, image, memory)
uv run hornero-qa list              # scenarios
uv run hornero-qa run smoke/desktop-ready
uv run hornero-qa inspect ~/.local/share/hornero/qa/runs/<run-id>
uv run hornero-qa studio-gate
```

## What lives here (and what does not)

Product and system acceptance lives here. Unit, component and repo-local
tests stay in their owning repositories (shell, config, hornero, greeter,
website). See the boundary table in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#1-boundary).

## License

MIT. Hornero QA integrates GPL tools such as os-autoinst only as external
processes; no GPL code is copied into this repository.
