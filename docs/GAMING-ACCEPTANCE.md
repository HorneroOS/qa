# Gaming acceptance evidence gate

`gaming-acceptance.yaml` is QA's evidence index for Gaming promotion
decisions (HorneroOS/hornero#328, HorneroOS/qa#37). It mirrors the Studio
gate: QA reports evidence and never changes product maturity or publishes
a Preview claim. Gaming stays `planned` until every required item is
accepted and the maintainer approves promotion.

Run the local gate with:

```sh
uv run hornero-qa gaming-gate
uv run hornero-qa gaming-gate --json
```

The command exits non-zero while any required item is pending. Physical
hardware items (Steam/Proton gameplay, handheld session, graphics
topologies) stay BLOCKED until owner-approved fixtures exist; VM evidence
is never hardware evidence. Anti-cheat honesty is review evidence only:
kernel-level anti-cheat is unsupported, and EAC/BattlEye depend on
publisher Proton enablement — it is never a satisfiable install gate.
