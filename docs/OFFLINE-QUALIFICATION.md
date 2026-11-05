# Offline qualification runbook (Preview 33)

Runs the remaining Preview 33 installation acceptance **without
Muse running**. Muse consumes ~5 GiB RSS; on a 15 GiB host
that leaves too little RAM for the 4 GiB install VMs Calamares
requires. This procedure separates preparation (already done: this
repository) from execution (a normal terminal, Muse closed).

## Safety contract (enforced, not advisory)

`scripts/offline-qualification/preflight.py` runs before **every** VM
launch and refuses (exit 3, nothing started) unless:

- `MemAvailable` ≥ VM RAM + 4 GiB host floor (install VMs: ≥ 8 GiB;
  build VM: ≥ 12 GiB),
- no swap in/out activity in the last vmstat sample,
- no other QEMU/build process is running (one heavy job at a time),
- ≥ 10 GiB disk free.

Guest RAM is fixed at 4096 MiB — Calamares refuses to install below
4 GiB ("At least 4 GiB is required"), so the runner never lowers it.
Only disposable qcow2 disks are used; host/physical disks are never
touched. Cells run **sequentially**; each completed cell is a
checkpoint in `manifest.json` and `--resume` skips it.

## Step 1 — Prepare (Muse may still be open)

```bash
cd <qa clone>            # HorneroOS/qa, main, this tooling merged
uv sync --group web      # one-time environment
```

## Autonomous supervised execution (preferred)

`worker.py` is the independent process intended for `systemd --user`.
It holds an exclusive lock, writes atomic JSON status, waits until no
Muse executable remains running, then waits until the existing
`preflight.py` passes before invoking `run.py` once. It polls at a
bounded interval, has a finite wait deadline, and records `blocked`,
`failed`, `interrupted`, or `completed` distinctly. `completed` only
means `run.py` exited 0 and its cells reached `executed`; it is not a
QA PASS verdict.

The checked-in unit
`scripts/offline-qualification/hornero-offline-qualification.service`
is preconfigured for the persistent `~/hornero-qa` checkout and the
Preview 32 single-cell smoke. The arming agent writes the exact
execution-owned Muse PID to `smoke-preview32.muse.pid`; the worker
waits only for that PID, never for unrelated Muse sessions. Once an
agent has installed and started that unit, the maintainer normally
only needs to close that Muse session. The worker survives the
exit because systemd owns its process and control group.

A separate `coordinator.py` service waits for the worker's terminal
state and starts one new headless `muse exec` review using a
persisted prompt. Muse `resume` is interactive, so this is a new
bounded review run, not a claim that the original session resumed
itself. It cannot start during the qualification VM.

Status can be inspected later with:

```bash
~/hornero-qa/.venv/bin/python \
  ~/hornero-qa/scripts/offline-qualification/worker.py status \
  --status-file ~/hornero-p33-offline/smoke-preview32.worker.json
```

## Step 2 — Build one candidate (optional; skip to test the signed Preview 32)

Cells unrelated to installer#94 can run against the signed Preview 32
ISO as-is. The **cancel-contract** cell needs a candidate containing
installer#94 (`disable-cancel-during-exec`):

```bash
# after closing Muse (the build VM needs 8 GiB + 4 GiB floor):
export OFFLINE_BUILD_HOST="builder@127.0.0.1"   # build-VM key user w/ sudo
export OFFLINE_BUILD_PORT=2224                  # default; ssh -p / scp -P handled
scripts/offline-qualification/build-candidate.sh
# -> prints installer HEAD + artifact SHA-256; sign via the established
#    maintainer workflow (installer/scripts/sign-release.sh)
```

Without `OFFLINE_BUILD_HOST` the script prints the exact manual
in-VM build commands and exits 4. Keep the sidecar
`*.iso.manifest.json` next to the artifact — `run.py` pins it into
its manifest, and the cancel-contract gate reads its
`installerRevision` from there (never from the filename).

## Step 3 — Close Muse, then run a SINGLE-CELL SMOKE first

Do not start with the full matrix. Prove the pipeline end-to-end
with one cell against the signed Preview 32 ISO:

```bash
# close Muse completely (this alone frees ~5 GiB), then:
free -h                  # sanity: MemAvailable should be ≥ 8 GiB
cd <qa clone>
python3 scripts/offline-qualification/run.py \
  --iso ~/.local/share/hornero/iso/preview32/horneroos-2026.10-preview32-x86_64.iso \
  --cells desktop-uefi \
  --state-dir ~/hornero-p33-offline/smoke-preview32
echo "exit=$?"           # 0 only if the cell reached `executed`
```

Inspect `~/hornero-p33-offline/smoke-preview32/evidence/desktop-uefi/attempt-1/`
(screenshots + `RESULT.draft.md`). **`executed` is not PASS** — it
means the drive ran and evidence was captured; verdicts are recorded
later from the frames via `hornero-qa import` (Step 4). Only after a
clean smoke, run the remaining cells (fresh state dir per ISO):

```bash
python3 scripts/offline-qualification/run.py \
  --iso /path/to/candidate-or-preview32.iso \
  --state-dir ~/hornero-p33-offline/<run-name>
```

Default cells: `desktop-uefi`, `studio-uefi`, `gaming-uefi`,
`desktop-bios-luks`, `studio-uefi-luks`, `cancel-contract`.
**cancel-contract is gated on artifact provenance**: it runs only
when the sidecar `installerRevision` is the installer#94 mitigation
commit (`cf72bbc…`) or a descendant (ancestry verified with
`--installer-repo <installer checkout>`). Against Preview 32 it is
recorded `not-applicable` and the run exits nonzero — exclude it
explicitly for Preview 32 runs. Opt-in: `--cells failure-cleanup`
(NIC cut mid-transaction; best effort, no tracked scenario yet).
The Niri graphical scenario is **not** part of this runner — it
requires a 3D-accelerated, observable GPU (qa#71 gate).

A full default run takes roughly 3–4 hours (install waits are
deliberately generous; the machine stays usable throughout because
only one 4 GiB VM runs at a time under the 4 GiB floor). If you stop
it, re-run with `--resume` and the same `--state-dir`: the pinned
ISO SHA-256 and execution config must match (a different ISO is
refused, never mixed), completed cells are skipped, and every retry
gets a **fresh disk** under a new `attempt-<n>` evidence directory
(previous attempts are preserved). The runner exits nonzero if any
selected cell fails, is preflight-blocked, or is gated out —
manifest, summary and evidence are still written.

Output: `~/hornero-p33-offline/<run-id>/` with `manifest.json`
(machine-readable checkpoints, ISO hash, per-cell status/timestamps),
`SUMMARY.md`, and `evidence/<cell>/` (screenshots in drive order +
`RESULT.draft.md`).

## Step 4 — Reopen Muse and hand over the run directory

Statuses in the manifest are **execution states, never verdicts**.
An operator/agent reviews each `evidence/<cell>/` (probe screenshots
carry `PROBE<n>:` markers from the scenario's own proof probes),
finalizes `RESULT.md`, and records explicit verdicts:

```bash
uv run hornero-qa import install/desktop-uefi-unencrypted \
  --source ~/hornero-p33-offline/<run>/evidence/desktop-uefi/attempt-1 \
  --verdict PASS --reason "<evidence-based reason>" \
  --product iso=<iso name> --product iso_sha256=<sha256>
git add -A && uv run hornero-qa matrix && uv run hornero-qa matrix --check
```

Then the normal PR flow updates the matrix, triage, and issues
(installer#93 closes only with the cancel-contract behavior proof
from this run on an installer#94 candidate).

## Troubleshooting

| Symptom | Meaning | Action |
|---|---|---|
| exit 3, `MemAvailable … < required` | host too busy | close browsers/IDEs; retry |
| exit 3, `swap activity` | host swapping | wait for settle (`vmstat 1 5`) |
| exit 3, `another heavy job` | a VM/build is running | let it finish or stop it |
| cell `failed` in manifest | drive or QEMU error | inspect `evidence/<cell>/` screenshots (last frames) and `~/.local/share/hornero/install-test/*-qemu.log` |
| cell executed but probes show errors | real product failure | keep the evidence; verdict FAIL on import with `--failure-class` |
| install screenshots still mid-progress at the end | install slower than the wait budget | re-run that cell alone (`--cells <name> --resume`); the retry uses a fresh disk and a new `attempt-<n>` evidence dir |
| `refusing --resume: state dir pins ISO sha256 …` | different ISO against an existing run | use a fresh `--state-dir` (one run = one immutable ISO) |
| `cancel-contract NOT applicable` | artifact lacks installer#94 provenance (e.g. Preview 32) | expected on Preview 32; for candidates keep the sidecar next to the ISO and pass `--installer-repo` |
