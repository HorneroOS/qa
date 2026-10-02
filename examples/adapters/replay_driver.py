#!/usr/bin/env python3
"""Reference driver adapter (hornero.qa.driver/1): replays a fixed action list.

Usage: hornero-qa run <scenario> --driver "python3 examples/adapters/replay_driver.py actions.json"

actions.json is a JSON list of driver actions, e.g.
  [{"type": "key", "chord": "super+d"}, {"type": "wait", "ms": 800},
   {"type": "key", "chord": "escape"}]
It exercises the agentic loop end to end without any model: the contract,
the sandbox, refusals and budgets. A model-backed adapter replaces it with
the same stdin/stdout contract.
"""

import json
import sys


def main() -> int:
    with open(sys.argv[1], encoding="utf-8") as fh:
        actions = json.load(fh)
    turn_in = json.load(sys.stdin)
    done = len(turn_in.get("history", []))
    if done < len(actions):
        reply = {"action": actions[done], "reason": f"replaying action {done + 1} of {len(actions)}"}
    else:
        reply = {"end": "done", "reason": "all actions replayed"}
    json.dump(reply, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
