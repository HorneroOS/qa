#!/usr/bin/env python3
"""Reference reviewer adapter (hornero.qa.review/1): judges by the evidence.

It reads the deterministic assertions and the bundle's frames and returns
PASS only when every assertion passed and a final frame exists; it never
acts on the guest. A model-backed reviewer would look at the frames
themselves and explain more, under the same contract.
"""

import json
import sys
from pathlib import Path


def main() -> int:
    data = json.load(sys.stdin)
    assertions = data.get("assertions", [])
    final = data.get("frames", {}).get("final")
    failed = [a for a in assertions if not a.get("ok")]
    reasons = [
        {"proof": a.get("where", "?"), "evidence": final or "", "text": str(a.get("detail", ""))}
        for a in failed
    ]
    if final is None or not Path(final).exists():
        verdict, cls = "INCONCLUSIVE", "inconclusive"
        reasons.append({"proof": "-", "evidence": "", "text": "no final frame to review"})
    elif failed:
        verdict, cls = "FAIL", "product"
    else:
        verdict, cls = "PASS", None
    json.dump(
        {
            "verdict": verdict,
            "class": cls,
            "reasons": reasons,
            "confidence": "high",
            "disagrees_with_driver": verdict == "FAIL" and data.get("driver", {}).get("end") == "done",
        },
        sys.stdout,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
