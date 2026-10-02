"""hornero-qa: system-level graphical acceptance for Hornero OS."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

from hornero_qa import __version__
from hornero_qa.engines.native import read_image_info
from hornero_qa.evidence import load_bundle
from hornero_qa.scenario import ScenarioError, discover, load, resolve
from hornero_qa.state import QAState

EXIT_OK, EXIT_FAIL, EXIT_INCONCLUSIVE, EXIT_USAGE = 0, 1, 2, 64


def _doctor(state: QAState, _: argparse.Namespace) -> int:
    checks: list[tuple[str, bool, str]] = []
    for tool in ("qemu-system-x86_64", "qemu-img", "systemd-run", "ssh", "scp"):
        path = shutil.which(tool)
        checks.append((tool, path is not None, path or "not on PATH"))
    kvm = Path("/dev/kvm")
    checks.append(("/dev/kvm", kvm.exists() and os.access(kvm, os.R_OK | os.W_OK), "read/write access"))
    checks.append(("state dir", True, str(state.root)))
    checks.append(("ssh key", state.ssh_key.exists(), str(state.ssh_key)))
    img = state.current_image()
    info = read_image_info(img) if img.exists() else {}
    checks.append(("current image", img.exists(), f"{img} -> {json.dumps(info.get('product', {}))}"))
    for name, ok, detail in checks:
        print(f"{'ok ' if ok else 'ERR'}  {name:<20} {detail}")
    return EXIT_OK if all(ok for _, ok, _ in checks) else EXIT_FAIL


def _list(_: QAState, args: argparse.Namespace) -> int:
    for path in discover():
        sc = load(path)
        covers = f"  [{', '.join(sc.covers)}]" if sc.covers else ""
        print(f"{sc.id}{covers}" if not args.verbose else f"{sc.id}{covers}\n    {sc.purpose}")
    return EXIT_OK


def _validate(_: QAState, args: argparse.Namespace) -> int:
    from hornero_qa.runner import ANCHORS_DIR

    paths = [Path(p) for p in args.paths] or discover()
    errors = 0
    for path in paths:
        try:
            sc = load(path)
        except ScenarioError as exc:
            print(f"ERR {exc}")
            errors += 1
            continue
        scenario_errors = 0
        for item in sc.steps + sc.proof:
            if "anchor" in item and not (ANCHORS_DIR / f"{item['anchor']['id']}.json").exists():
                print(
                    f"ERR {path}: anchor {item['anchor']['id']!r} has no anchors/{item['anchor']['id']}.json"
                )
                scenario_errors += 1
        errors += scenario_errors
        if not scenario_errors:
            print(f"ok  {sc.id}")
    return EXIT_OK if errors == 0 else EXIT_FAIL


def _run(state: QAState, args: argparse.Namespace) -> int:
    from hornero_qa.runner import RunOptions, run

    image = Path(args.image) if args.image else state.current_image()
    if not image.exists():
        print(f"no ready image at {image}; see docs/IMAGES.md", file=sys.stderr)
        return EXIT_INCONCLUSIVE
    summaries = []
    for name in args.scenarios:
        sc = load(resolve(name))
        summary = run(state, sc, RunOptions(image=image, repeat=args.repeat, mem_mb=args.mem_mb))
        summaries.append(summary)
        for r in summary["results"]:
            cls = r["class"] or "-"
            print(f"{r['verdict'].upper():<13} {sc.id}  class={cls}  {r['wall_s']}s  {r['bundle']}")
            if r["verdict"] != "pass":
                print(f"              {r['reason']}")
        if summary["flaky"]:
            print(f"FLAKY         {sc.id}: {summary['passed']}/{summary['attempts']} passed")
    if args.json:
        print(json.dumps(summaries, indent=2))
    verdicts = {r["verdict"] for s in summaries for r in s["results"]}
    if "fail" in verdicts:
        return EXIT_FAIL
    return EXIT_INCONCLUSIVE if verdicts - {"pass"} else EXIT_OK


def _inspect(_: QAState, args: argparse.Namespace) -> int:
    b = load_bundle(Path(args.bundle))
    if b["run"] is None:
        print(f"{args.bundle}: not an evidence bundle", file=sys.stderr)
        return EXIT_USAGE
    print(json.dumps({k: b[k] for k in ("run", "result", "assertions", "screenshots")}, indent=2))
    return EXIT_OK


def _report(_: QAState, args: argparse.Namespace) -> int:
    from hornero_qa.report import write_report

    print(write_report(Path(args.bundle)))
    return EXIT_OK


def _image(state: QAState, args: argparse.Namespace) -> int:
    from hornero_qa import image

    if args.image_cmd == "info":
        path = Path(args.path) if args.path else state.current_image()
        print(json.dumps(read_image_info(path), indent=2))
        return EXIT_OK
    if args.image_cmd == "adopt":
        product = dict(kv.split("=", 1) for kv in args.product)
        key = Path(args.ssh_key) if args.ssh_key else None
        print(image.adopt(state, Path(args.path), args.name, key, product))
        return EXIT_OK
    out = image.refresh(
        state,
        base=Path(args.base),
        shell_checkout=Path(args.shell),
        config_sha=args.config_sha,
        horneroctl=Path(args.horneroctl),
        name=args.name,
    )
    print(out)
    return EXIT_OK


def _anchor(_: QAState, args: argparse.Namespace) -> int:
    from hornero_qa.runner import ANCHORS_DIR
    from hornero_qa.vision import cut_anchor

    x, y, w, h = (int(v) for v in args.rect.split(","))
    prov = {"source": str(args.frame)}
    sidecar = Path(args.frame).with_suffix(".json")
    if sidecar.exists():
        meta = json.loads(sidecar.read_text(encoding="utf-8"))
        prov |= {k: meta[k] for k in ("run_id", "scenario", "product", "environment") if k in meta}
    print(cut_anchor(args.frame, ANCHORS_DIR, args.id, (x, y, w, h), args.tag, args.mode, provenance=prov))
    return EXIT_OK


def _media(_: QAState, args: argparse.Namespace) -> int:
    from hornero_qa.media import MediaError, export

    try:
        manifest = export([Path(b) for b in args.bundles], Path(args.out))
    except MediaError as exc:
        print(f"hornero-qa: {exc}", file=sys.stderr)
        return EXIT_FAIL
    for item in manifest["items"]:
        print(f"{item['file']}  {item['sha256'][:12]}  {item['run_id']}")
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="hornero-qa", description=__doc__)
    p.add_argument("--version", action="version", version=f"hornero-qa {__version__}")
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("doctor", help="check host prerequisites and the current ready image")
    s = sub.add_parser("list", help="list scenarios")
    s.add_argument("-v", "--verbose", action="store_true")
    s = sub.add_parser("validate", help="validate scenarios against the schema and anchors")
    s.add_argument("paths", nargs="*")

    s = sub.add_parser("run", help="run scenarios on the native engine")
    s.add_argument("scenarios", nargs="+", help="scenario ids (layouts/apply-cockpit-clear) or paths")
    s.add_argument("--image", help="ready image (default: state images/current.qcow2)")
    s.add_argument("--repeat", type=int, default=1, help="independent attempts per scenario (flakiness)")
    s.add_argument("--mem-mb", type=int, default=2048)
    s.add_argument("--json", action="store_true", help="print machine-readable summaries")

    s = sub.add_parser("inspect", help="print an evidence bundle summary")
    s.add_argument("bundle")
    s = sub.add_parser("report", help="(re)generate a bundle's report.html")
    s.add_argument("bundle")

    s = sub.add_parser("image", help="ready images")
    isub = s.add_subparsers(dest="image_cmd", required=True)
    i = isub.add_parser("info", help="show image provenance")
    i.add_argument("path", nargs="?")
    i = isub.add_parser("adopt", help="register an existing image (symlink) with declared provenance")
    i.add_argument("path")
    i.add_argument("--name", required=True)
    i.add_argument("--ssh-key")
    i.add_argument("--product", action="append", default=[], metavar="KEY=VALUE")
    i = isub.add_parser("refresh", help="compose shell+config+horneroctl at exact SHAs into a new image")
    i.add_argument("--base", required=True, help="provisioned base image (never modified)")
    i.add_argument("--shell", required=True, help="clean HorneroOS/shell checkout at the SHA under test")
    i.add_argument("--config-sha", required=True)
    i.add_argument("--horneroctl", required=True, help="horneroctl binary to install")
    i.add_argument("--name", required=True)

    s = sub.add_parser("anchor", help="visual anchors")
    asub = s.add_subparsers(dest="anchor_cmd", required=True)
    a = asub.add_parser("cut", help="cut an anchor from a certified screenshot")
    a.add_argument("frame")
    a.add_argument("--id", required=True, help="anchor id, e.g. launcher/search-field")
    a.add_argument("--rect", required=True, help="x,y,w,h in pixels")
    a.add_argument("--tag", action="append", default=[])
    a.add_argument("--mode", choices=["structure", "pixel"], default="structure")

    s = sub.add_parser("media", help="product media from certified runs")
    msub = s.add_subparsers(dest="media_cmd", required=True)
    m = msub.add_parser("export", help="export `media` screenshots of passing runs with provenance")
    m.add_argument("bundles", nargs="+")
    m.add_argument("--out", required=True)
    return p


COMMANDS = {
    "doctor": _doctor,
    "list": _list,
    "validate": _validate,
    "run": _run,
    "inspect": _inspect,
    "report": _report,
    "image": _image,
    "anchor": _anchor,
    "media": _media,
}


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.cmd:
        parser.print_help()
        return EXIT_OK
    try:
        return COMMANDS[args.cmd](QAState.default(), args)
    except ScenarioError as exc:
        print(f"hornero-qa: {exc}", file=sys.stderr)
        return EXIT_USAGE
