"""Static, self-contained HTML report for one evidence bundle (no scripts, no network)."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from hornero_qa.evidence import load_bundle

CSS = """
:root{--bg:#f6f1ec;--fg:#2a211c;--muted:#6f625a;--card:#fff;--line:#e3d8cf;
--pass:#2f7d4f;--fail:#b3412c;--inc:#9a6b12}
@media (prefers-color-scheme:dark){:root{--bg:#1b1613;--fg:#f1e8e1;--muted:#b3a59b;
--card:#25201c;--line:#3a312b}}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif}
main{max-width:1100px;margin:0 auto;padding:24px 16px}
h1{font-size:1.4rem;margin:0 0 4px}h2{font-size:1.1rem;margin:28px 0 8px}
.v{display:inline-block;padding:2px 10px;border-radius:999px;color:#fff;font-weight:600}
.pass{background:var(--pass)}.fail{background:var(--fail)}.inconclusive{background:var(--inc)}
table{border-collapse:collapse;width:100%;background:var(--card)}
td,th{border:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}
code,pre{font:13px/1.4 ui-monospace,monospace;white-space:pre-wrap;word-break:break-word}
.muted{color:var(--muted)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:12px}
figure{margin:0;background:var(--card);border:1px solid var(--line);padding:8px}
figure img{width:100%;height:auto;display:block}
"""


def _e(v: Any) -> str:
    return html.escape(v if isinstance(v, str) else json.dumps(v))


def _row(cells: list[str], tag: str = "td") -> str:
    return "<tr>" + "".join(f"<{tag}>{c}</{tag}>" for c in cells) + "</tr>"


def _figure(name: str) -> str:
    src = f"screenshots/{_e(name)}"
    img = f'<img loading="lazy" src="{src}" alt="{_e(name)}">'
    return f'<figure><a href="{src}">{img}</a><figcaption class=muted>{_e(name)}</figcaption></figure>'


def render(bundle: dict[str, Any]) -> str:
    run = bundle["run"] or {}
    res = bundle["result"] or {}
    verdict = res.get("verdict", "inconclusive")
    scenario = _e(run.get("scenario", "?"))
    facts = (run.get("product") or {}) | (run.get("environment") or {})
    rows = "".join(
        _row(
            [
                "✅" if a.get("ok") else "❌",
                _e(a.get("where", "")),
                _e(a.get("kind", "")),
                _e(a.get("note") or ""),
                f"<code>{_e(a.get('detail', ''))}</code>",
            ]
        )
        for a in bundle["assertions"] or []
    )
    kv = "".join(f"<tr><th>{_e(k)}</th><td><code>{_e(v)}</code></td></tr>" for k, v in facts.items())
    shots = "".join(_figure(s) for s in bundle["screenshots"])
    actions = "\n".join(json.dumps(a) for a in bundle["actions"])
    meta = " · ".join(
        [
            _e(run.get("run_id", "")),
            f"attempt {_e(run.get('attempt', 1))}",
            f"{_e(res.get('wall_s', '?'))} s",
            f"class <code>{_e(res.get('class') or '-')}</code>",
        ]
    )
    head = _row(["", "where", "kind", "note", "detail"], "th")
    files = "run.json, result.json, assertions.json, actions.jsonl"
    return f"""<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>{scenario} · Hornero QA</title><style>{CSS}</style></head><body><main>
<h1>{scenario} <span class="v {_e(verdict)}">{_e(verdict.upper())}</span></h1>
<p class=muted>{meta}</p>
<p><strong>Reason:</strong> {_e(res.get("reason", ""))}</p>
<h2>Instruction</h2><p>{_e(run.get("instruction", ""))}</p>
<h2>Proof</h2><table>{head}{rows}</table>
<h2>Product and environment</h2><table>{kv}</table>
<h2>Screenshots</h2><div class=grid>{shots}</div>
<h2>Actions</h2><pre>{_e(actions)}</pre>
<p class=muted>Logs: <a href="logs/">logs/</a> · machine-readable: {files}</p>
</main></body></html>
"""


def write_report(root: Path) -> Path:
    out = root / "report.html"
    out.write_text(render(load_bundle(root)), encoding="utf-8")
    return out
