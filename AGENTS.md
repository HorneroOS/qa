# AGENTS.md — HorneroOS/qa contributor rules

Read `docs/ARCHITECTURE.md` first. These rules are the contract.

## Boundary

- Only system/product acceptance belongs here. Do not move unit, lint or
  component tests out of shell/config/hornero/greeter/website.
- Compose guests by calling the shell's `tests/vm/lib` at a pinned SHA. Do not
  fork or copy that harness.
- `HorneroOS/hornero` owns releases. QA produces evidence; it never edits
  manifests or tags.

## Scenarios

- Acceptance criteria (`proof`) are written by humans and reviewed. A runner,
  driver or reviewer must never invent or relax them at runtime.
- UX scenarios act only through the action lane (QMP keyboard/pointer).
  SSH/IPC are observation-only (probes) unless the scenario explicitly tests
  those interfaces.
- No arbitrary sleeps: synchronize with `wait: {changed, stable}` or a probe.

## Host safety (hard rules)

- Never archive, copy or mount the operator's real HOME. Guests get fixtures.
- Every VM runs in a memory-capped `systemd-run --user --scope` (`MemoryMax`).
  One graphical VM at a time on a workstation.
- Keep large files out of `/tmp` (often tmpfs/RAM). Run state goes under the
  configured state dir (default `~/.local/share/hornero/qa`).
- Never touch the operator's live compositor, shell or display manager.
- No telemetry or automatic bug-report submission from any tool
  (`V_C_ERROR_BUG_REPORT_DISABLED=1` etc.). No test contacts external
  services beyond package mirrors needed to build an image.

## Evidence

- Every run writes a bundle (`docs/EVIDENCE.md`). Results use the taxonomy in
  `docs/ARCHITECTURE.md#7-failure-taxonomy`. Driver PASS + reviewer FAIL is FAIL.
- Never commit personal data, accounts, emails, hostnames or SSH keys in
  fixtures, anchors or screenshots.

## Gates

`uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`,
`uv run pytest`, `uv run hornero-qa validate`.
