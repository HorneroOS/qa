"""Web lane: browser journeys and product-truth checks for the public site.

A web journey visits real pages in Chromium (Playwright, optional `web`
dependency group) and asserts what a visitor would notice: third-party
requests, console errors, horizontal scroll, broken navigation. Truth checks
compare what the site claims with the product repositories' current state,
so a stale website is a failure, not a surprise.
"""

from __future__ import annotations

import glob
import json
import os
import re
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urljoin, urlparse

import yaml

from hornero_qa.evidence import Bundle
from hornero_qa.scenario import REPO_ROOT
from hornero_qa.state import QAState

if TYPE_CHECKING:
    from playwright.sync_api import ConsoleMessage, Error, Page, Request

JOURNEY_DIR = REPO_ROOT / "web" / "journeys"
DEFAULT_BASE = "https://website-zcra.vercel.app"
VIEWPORTS = {"phone": (390, 844), "desktop": (1366, 860)}
GITHUB = "https://api.github.com"


@dataclass
class Journey:
    id: str
    purpose: str
    pages: list[str] | str = "sitemap"
    viewports: list[str] = field(default_factory=lambda: ["phone", "desktop"])
    checks: list[str] = field(default_factory=lambda: ["status", "third_party", "console", "overflow"])
    steps: list[dict[str, Any]] = field(default_factory=list)
    truth: list[str] = field(default_factory=list)
    text: str = ""


def load_journey(path: Path) -> Journey:
    text = path.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    if not isinstance(data, dict) or "id" not in data or "purpose" not in data:
        raise ValueError(f"{path}: a journey needs id and purpose")
    known = {"id", "purpose", "pages", "viewports", "checks", "steps", "truth"}
    if set(data) - known:
        raise ValueError(f"{path}: unknown keys {sorted(set(data) - known)}")
    return Journey(**data, text=text)


def discover_journeys() -> list[Path]:
    return sorted(JOURNEY_DIR.glob("*.yaml"))


def chromium_path() -> str | None:
    env = os.environ.get("HORNERO_QA_CHROMIUM")
    if env:
        return env
    found = sorted(glob.glob(os.path.expanduser("~/.cache/ms-playwright/chromium-*/chrome-linux*/chrome")))
    return found[-1] if found else None


def _get(url: str) -> Any:
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read())


def _sitemap_pages(base: str) -> list[str]:
    def locs(url: str) -> list[str]:
        with urllib.request.urlopen(url, timeout=20) as resp:
            body = resp.read().decode("utf-8")
        return re.findall(r"<loc>([^<]+)</loc>", body)

    pages: list[str] = []
    for loc in locs(urljoin(base, "/sitemap-index.xml")):
        pages += [urlparse(u).path for u in locs(loc)]
    return sorted(set(pages))


@dataclass
class _Watch:
    """Collects what a visitor's browser did on one page."""

    host: str | None
    external: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def reset(self) -> None:
        self.external.clear()
        self.errors.clear()

    def on_request(self, req: Request) -> None:
        if urlparse(req.url).hostname not in (self.host, None):
            self.external.append(req.url)

    def on_console(self, msg: ConsoleMessage) -> None:
        if msg.type == "error":
            self.errors.append(msg.text)

    def on_pageerror(self, err: Error) -> None:
        self.errors.append(str(err))


# ------------------------------------------------------------ truth checks --
def _truth(name: str, page: Page, base: str) -> tuple[bool, str]:
    if name == "layouts_match_shell_main":
        presets = [f["name"] for f in _get(f"{GITHUB}/repos/HorneroOS/shell/contents/presets?ref=main")]
        want = {p.removesuffix(".json") for p in presets if p.endswith(".json")}
        page.goto(urljoin(base, "/layouts"), wait_until="load")
        got = set(page.eval_on_selector_all("li.layout[id]", "els => els.map(e => e.id)"))
        return got == want, f"site {len(got)} layouts, shell main {len(want)}; missing {sorted(want - got)}"
    if name == "themes_match_config_main":
        items = _get(f"{GITHUB}/repos/HorneroOS/config/contents/profiles/themes?ref=main")
        want = {i["name"] for i in items if i["type"] == "dir"}
        page.goto(urljoin(base, "/themes"), wait_until="load")
        got = set(page.eval_on_selector_all("li.theme[id]", "els => els.map(e => e.id)"))
        return got == want, f"site {len(got)} themes, config main {len(want)}; missing {sorted(want - got)}"
    if name == "latest_tag_matches_hornero":
        tags = [t["name"] for t in _get(f"{GITHUB}/repos/HorneroOS/hornero/tags?per_page=100")]
        previews = sorted(
            (int(m.group(1)) for t in tags if (m := re.fullmatch(r"v\d+\.\d+\.\d+-preview(\d+)", t))),
            reverse=True,
        )
        page.goto(urljoin(base, "/releases"), wait_until="load")
        latest = page.locator("text=Latest tagged").locator("xpath=..").inner_text()
        expected = f"Development Preview {previews[0]}" if previews else "?"
        return expected in latest, f"site says {latest.splitlines()[-1]!r}, hornero tags say {expected!r}"
    if name == "no_download_claims":
        page.goto(urljoin(base, "/install"), wait_until="load")
        hrefs = page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
        bad = [h for h in hrefs if re.search(r"\.(iso|img|qcow2)(\?|$)", h)]
        return not bad, f"download links: {bad}" if bad else "no image download links"
    raise ValueError(f"unknown truth check {name!r}")


def run_journey(state: QAState, journey: Journey, base: str) -> dict[str, Any]:
    from playwright.sync_api import sync_playwright

    exe = chromium_path()
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    run_id = f"{stamp}-{journey.id.replace('/', '-')}"
    state.ensure()
    meta = {
        "scenario": journey.id,
        "instruction": journey.purpose,
        "environment": {"lane": "web", "base": base},
    }
    bundle = Bundle.create(state.runs_dir, run_id, meta, journey.text)
    host = urlparse(base).hostname
    failures: list[str] = []
    pages = _sitemap_pages(base) if journey.pages == "sitemap" else list(journey.pages)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=exe, args=["--disable-quic"])
        try:
            for vp in journey.viewports:
                w, h = VIEWPORTS[vp]
                ctx = browser.new_context(viewport={"width": w, "height": h})
                page = ctx.new_page()
                watch = _Watch(host)
                page.on("request", watch.on_request)
                page.on("console", watch.on_console)
                page.on("pageerror", watch.on_pageerror)
                for path in pages:
                    watch.reset()
                    resp = page.goto(urljoin(base, path), wait_until="networkidle")
                    problems: list[str] = []
                    if "status" in journey.checks and (resp is None or resp.status >= 400):
                        problems.append(f"HTTP {resp.status if resp else 'no response'}")
                    if "third_party" in journey.checks and watch.external:
                        problems.append(f"third-party requests: {sorted(set(watch.external))[:5]}")
                    if "console" in journey.checks and watch.errors:
                        problems.append(f"console errors: {watch.errors[:3]}")
                    if "overflow" in journey.checks and page.evaluate(
                        "document.documentElement.scrollWidth > window.innerWidth"
                    ):
                        problems.append("horizontal overflow")
                    rec = {
                        "kind": "web",
                        "where": f"{vp} {path}",
                        "ok": not problems,
                        "detail": problems or "ok",
                    }
                    bundle.assertion(rec)
                    if problems:
                        failures.append(f"{vp} {path}: {'; '.join(problems)}")
                        shot = bundle.root / "screenshots" / "tmp.png"
                        page.screenshot(path=str(shot), full_page=True)
                        bundle.screenshot(shot, f"{vp}-{path.strip('/').replace('/', '-') or 'home'}")
                        shot.unlink()
                for i, step in enumerate(journey.steps):
                    ok, why = _step(page, base, step)
                    bundle.assertion({"kind": "step", "where": f"{vp} step {i}", "ok": ok, "detail": why})
                    if not ok:
                        failures.append(f"{vp} step {i}: {why}")
                        break
                ctx.close()
            if journey.truth:
                page = browser.new_page()
                for name in journey.truth:
                    try:
                        ok, why = _truth(name, page, base)
                    except Exception as exc:  # network or API problem: not a site failure
                        ok, why = False, f"truth check could not run: {type(exc).__name__}: {exc}"
                    bundle.assertion({"kind": "truth", "where": name, "ok": ok, "detail": why})
                    if not ok:
                        failures.append(f"{name}: {why}")
        finally:
            browser.close()
    verdict = "pass" if not failures else "fail"
    result = bundle.finish(
        {
            "verdict": verdict,
            "class": None if verdict == "pass" else "product",
            "reason": "; ".join(failures)[:2000] or "all checks passed",
            "pages": len(pages),
        }
    )
    return result | {"bundle": str(bundle.root)}


def _step(page: Page, base: str, step: dict[str, Any]) -> tuple[bool, str]:
    ((kind, val),) = step.items()
    try:
        if kind == "visit":
            page.goto(urljoin(base, val), wait_until="networkidle")
        elif kind == "click":
            page.get_by_role(
                val.get("role", "link"), name=val["name"], exact=val.get("exact", False)
            ).first.click()
            page.wait_for_load_state("networkidle")
        elif kind == "expect_url":
            if not urlparse(page.url).path.rstrip("/").endswith(val.rstrip("/")):
                return False, f"at {page.url}, expected {val}"
        elif kind == "expect_text":
            if page.get_by_text(val).count() == 0:
                return False, f"text {val!r} not on {page.url}"
        else:
            return False, f"unknown step {kind!r}"
    except Exception as exc:
        return False, f"{kind} failed: {type(exc).__name__}: {str(exc).splitlines()[0]}"
    return True, f"{kind} ok"
