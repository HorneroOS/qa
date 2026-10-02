# Agentic QA contracts

Status: **contract**. The deterministic runner is the acceptance authority;
agentic adapters are optional and land behind this contract. Nothing here
requires a specific model or vendor: an adapter is any executable that reads
one JSON document on stdin and writes one JSON document on stdout.

## Roles

| Role | Sees | Can do | Cannot do |
|---|---|---|---|
| Driver | instruction, current screenshot, short history, budgets | return one input action | SSH, IPC, source access, probes, deciding the verdict |
| Reviewer | scenario, proof criteria, assertions, action trace, final and per-step frames | type and explain a verdict | act on the guest, override a deterministic failure |

## Driver: `hornero.qa.driver/1`

Input (one turn):

```json
{
  "schema": "hornero.qa.driver.in/1",
  "run_id": "20261002T011048Z-drawers-dashboard-keyboard-1",
  "turn": 3,
  "instruction": "Press Super+D to open the dashboard, look at it, then press Escape.",
  "frame": {"path": "/abs/run/frames/0003.png", "w": 1280, "h": 800, "sha256": "…"},
  "pointer": {"x": 0.42, "y": 0.10},
  "refusal": null,
  "history": [{"turn": 2, "action": {"type": "key", "chord": "super+d"}, "outcome": "ok"}],
  "budget": {"actions_left": 57, "seconds_left": 140, "malformed_left": 3}
}
```

- `pointer` is `null` before the first move; `history` keeps the last 20
  entries; `refusal` explains why the previous reply was refused.

Output, exactly one of:

```json
{"action": {"type": "key", "chord": "escape"}, "reason": "dashboard is open; close it"}
{"end": "done", "reason": "dashboard opened and closed"}
{"end": "give_up", "reason": "no dashboard after two attempts"}
```

Actions (coordinates normalized to the frame, `0..1`): `key{chord}`,
`type{text}`, `move{x,y}`, `click{button}` at the tracked pointer,
`scroll{ticks}` (`-10..10`), `wait{ms}` (at most 3000).

Rules:

- Unknown fields, unknown action types and clicks before any move are
  refused. Each refusal is a malformed output; `max_malformed` in a row
  (default 3) ends the run with class `driver`.
- `done` is a claim, never a verdict. Proof is always checked through the
  observation lane, exactly as for deterministic runs.
- `give_up` or an exhausted budget is a `driver` failure unless the
  reviewer finds a product cause backed by evidence.

## Reviewer: `hornero.qa.review/1`

Input: the scenario (`instruction`, `proof`), `assertions.json`,
`actions.jsonl`, the final frame and per-step frames, the driver's end
state, and infra signals (QEMU exit, capture errors).

Output:

```json
{
  "verdict": "FAIL",
  "class": "product",
  "reasons": [{"proof": "proof 0", "evidence": "003-dashboard.png + proof 0", "text": "…"}],
  "confidence": "high",
  "disagrees_with_driver": true
}
```

`verdict` is `PASS`, `FAIL` or `INCONCLUSIVE`; `class` comes from the closed
taxonomy in `src/hornero_qa/taxonomy.py`.

## Precedence (enforced by the harness, not the model)

1. Any infra signal (QEMU exited, the guest never booted, capture
   failed, the adapter crashed) → `INCONCLUSIVE` with class
   `harness`/`boot`; the run is repeated, not counted. Shell or compositor
   death inside a healthy guest is a product failure (`product_crash`).
2. A failed deterministic proof check → `FAIL`. The reviewer may only
   explain it; it can never upgrade it.
3. No deterministic failure but the driver ended `give_up` or ran out of
   budget → `FAIL` class `driver`.
4. Every proof check passing deterministically → `PASS`; reviewer output is
   sampled for audit.

Driver `done` + reviewer `FAIL` is a `FAIL` that needs human inspection.
`--repeat N` reports counts per class, so a model miss is never reported as a
Hornero regression.
