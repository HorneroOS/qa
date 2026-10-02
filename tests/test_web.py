"""Web lane: journey parsing plus failure handling without a real browser.

run_journey is exercised through a fake Playwright harness: navigation and
truth-check failures must be recorded as assertions and the bundle must
always be finished with an honest verdict/class.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from hornero_qa.state import QAState
from hornero_qa.web import Journey, load_journey, run_journey

PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
    b"\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00"
    b"\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


class _Resp:
    def __init__(self, status: int = 200) -> None:
        self.status = status


class _Page:
    def __init__(self, fail_urls: set[str]) -> None:
        self.fail_urls = fail_urls

    def on(self, _event: str, _handler: object) -> None:
        pass

    def goto(self, url: str, wait_until: str = "load") -> _Resp:
        if url in self.fail_urls:
            raise RuntimeError("boom")
        return _Resp()

    def evaluate(self, _js: str) -> bool:
        return False

    def screenshot(self, path: str, full_page: bool = False) -> None:
        Path(path).write_bytes(PNG)


class _Ctx:
    def __init__(self, page: _Page) -> None:
        self._page = page

    def new_page(self) -> _Page:
        return self._page

    def close(self) -> None:
        pass


class _Browser:
    def __init__(self, page: _Page) -> None:
        self._page = page
        self.closed = False

    def new_context(self, viewport: dict[str, int]) -> _Ctx:
        return _Ctx(self._page)

    def new_page(self) -> _Page:
        return self._page

    def close(self) -> None:
        self.closed = True


class _Pw:
    def __init__(self, page: _Page) -> None:
        self._page = page
        self.browser: _Browser | None = None

    @property
    def chromium(self) -> _Pw:
        return self

    def launch(self, **kwargs: Any) -> _Browser:
        self.browser = _Browser(self._page)
        return self.browser

    def __enter__(self) -> _Pw:
        return self

    def __exit__(self, *args: object) -> None:
        pass


def _run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, journey: Journey, fail: set[str]) -> dict[str, Any]:
    import playwright.sync_api

    monkeypatch.setattr(playwright.sync_api, "sync_playwright", lambda: _Pw(_Page(fail)))
    return run_journey(QAState(root=tmp_path / "state"), journey, "https://site.test")


def test_load_journey_validates(tmp_path: Path) -> None:
    good = tmp_path / "j.yaml"
    good.write_text("id: web/x\npurpose: Probe parsing.\npages: [/a]\n", encoding="utf-8")
    assert load_journey(good).pages == ["/a"]
    bad = tmp_path / "bad.yaml"
    bad.write_text("id: web/x\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_journey(bad)
    bad.write_text("id: web/x\npurpose: P\nbogus: 1\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_journey(bad)


def test_navigation_failure_is_recorded_and_continues(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    journey = Journey(id="web/x", purpose="P", pages=["/a", "/b"], viewports=["desktop"])
    result = _run(tmp_path, monkeypatch, journey, {"https://site.test/a"})
    assert result["verdict"] == "fail" and result["class"] == "product"
    assert "desktop /a: navigation failed" in result["reason"]
    bundle = Path(result["bundle"])
    assert (bundle / "result.json").exists() and (bundle / "assertions.json").exists()


def test_unrunnable_truth_check_is_harness_not_product(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    journey = Journey(id="web/x", purpose="P", pages=[], viewports=[], truth=["bogus"])
    result = _run(tmp_path, monkeypatch, journey, set())
    assert result["verdict"] == "fail" and result["class"] == "harness"
    assert "could not run" in result["reason"]
