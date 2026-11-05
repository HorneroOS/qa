"""Offline qualification runner contracts (no VMs are launched).

Covers the resource preflight gates, manifest checkpoints, cell map
integrity, and the failure behavior that must never silently bypass the
RAM/disk/serialization rules.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts" / "offline-qualification"


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


preflight = _load("preflight")
drive = _load("drive")
run = _load("run")
worker = _load("worker")
coordinator = _load("coordinator")

MEMINFO_OK = "MemTotal:       16000000 kB\nMemAvailable:   11000000 kB\n"
MEMINFO_LOW = "MemTotal:       16000000 kB\nMemAvailable:    6000000 kB\n"
VMSTAT_QUIET = (
    "procs ---swap---\n r b si so bi bo\n 1 0 0 0 5 5 0 0 0 0 0 0 0 0 0 0\n 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0\n"
)
# vmstat columns: r b swpd free buff cache si so ...
VMSTAT_QUIET = " 1 0 100 200 300 400 0 0 1 2 3 4 5 6 7 8\n 0 0 100 200 300 400 0 0 0 0 0 0 0 0 0 0\n"
VMSTAT_SWAPPING = " 1 0 100 200 300 400 0 0 1 2 3 4 5 6 7 8\n 0 0 100 200 300 400 12 3 0 0 0 0 0 0 0 0\n"
PS_CLEAN = "python3 run.py\nbash\n"
PS_QEMU = "qemu-system-x86_64 -m 4096 -name hornero-install-x\n"


def test_preflight_passes_with_headroom() -> None:
    result = preflight.check_resources(
        vm_mib=4096, meminfo_text=MEMINFO_OK, vmstat_text=VMSTAT_QUIET, ps_text=PS_CLEAN, disk_free_gib=100.0
    )
    assert result.ok, result.messages


def test_preflight_refuses_below_required_ram() -> None:
    result = preflight.check_resources(
        vm_mib=4096, meminfo_text=MEMINFO_LOW, vmstat_text=VMSTAT_QUIET, ps_text=PS_CLEAN, disk_free_gib=100.0
    )
    assert not result.ok
    assert any("MemAvailable" in m for m in result.messages)


def test_preflight_scales_requirement_with_vm_size() -> None:
    # 11 GiB available passes a 4 GiB VM (needs 8) but not an 8 GiB VM (needs 12).
    small = preflight.check_resources(
        vm_mib=4096, meminfo_text=MEMINFO_OK, vmstat_text=VMSTAT_QUIET, ps_text=PS_CLEAN, disk_free_gib=100.0
    )
    large = preflight.check_resources(
        vm_mib=8192, meminfo_text=MEMINFO_OK, vmstat_text=VMSTAT_QUIET, ps_text=PS_CLEAN, disk_free_gib=100.0
    )
    assert small.ok and not large.ok


def test_preflight_refuses_swap_activity_and_competing_vm_and_low_disk() -> None:
    result = preflight.check_resources(
        vm_mib=4096, meminfo_text=MEMINFO_OK, vmstat_text=VMSTAT_SWAPPING, ps_text=PS_QEMU, disk_free_gib=5.0
    )
    assert not result.ok
    joined = " | ".join(result.messages)
    assert "swap activity" in joined
    assert "another heavy job" in joined
    assert "disk free" in joined


def test_competing_process_scan_ignores_grep_lines() -> None:
    assert preflight.find_competing_processes("grep qemu-system\n") == []


def test_cells_map_to_registered_scenarios_and_rows() -> None:
    from hornero_qa.scenario import load, resolve

    for cell in drive.CELLS.values():
        scenario = load(resolve(cell.scenario))
        assert scenario.proof, f"{cell.name}: scenario has no probes to type"
        assert cell.edition_row in drive.EDITION_ROWS
        assert cell.firmware in {"uefi", "bios"}


class _RecordingDriver:
    """Fake Driver for drive_install: records actions, never touches QMP."""

    def __init__(self) -> None:
        self.clicks: list[tuple[float, float]] = []
        self.typed: list[str] = []
        self.events: list[tuple] = []

    def shot(self, name: str) -> None:
        pass

    def click(self, x: float, y: float, wait_s: float = 2.0) -> None:
        self.clicks.append((x, y))
        self.events.append(("click", x, y))

    def type(self, text: str, wait_s: float = 0.5) -> None:
        self.typed.append(text)
        self.events.append(("type", text))

    def key(self, chord: str, wait_s: float = 1.0) -> None:
        pass

    def run_typed(self, command: str, wait_s: float = 3.0) -> None:
        self.events.append(("type", command))


def test_unencrypted_drive_clicks_encrypt_checkbox_center(monkeypatch: pytest.MonkeyPatch) -> None:
    # Preview 32 attempt-1 frames (02-partitions.png, 1280x800) place the
    # "Encrypt system" checkbox centre at ~(271, 572) px = (0.212, 0.715).
    # The old click (0.215, 0.686) landed ~23 px above it, leaving encryption
    # checked with empty/mismatched passphrases and Next disabled.
    monkeypatch.setattr(drive.time, "sleep", lambda *_a, **_k: None)
    fake = _RecordingDriver()
    drive.drive_install(fake, drive.CELLS["desktop-uefi"], install_timeout_s=0)
    assert (0.212, 0.715) in fake.clicks
    assert (0.215, 0.686) not in fake.clicks
    erase = fake.clicks.index((0.298, 0.108))
    partitions_next = fake.clicks.index((0.864, 0.941), erase)
    assert fake.clicks.index((0.212, 0.715)) < partitions_next
    # Only the Users-page fields are typed; no passphrase pair precedes them.
    assert fake.typed == ["Hornero Test", "hornero", "hornero-test", drive.TEST_PASSWORD, drive.TEST_PASSWORD]
    # No offline flow may keep the proven-missing coordinate.
    for script in ("drive.py", "run.py"):
        assert "0.215, 0.686" not in (SCRIPTS / script).read_text(encoding="utf-8")


def test_encrypted_drive_types_luks_passphrase_twice(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(drive.time, "sleep", lambda *_a, **_k: None)
    fake = _RecordingDriver()
    drive.drive_install(fake, drive.CELLS["desktop-bios-luks"], install_timeout_s=0)
    # LUKS and user passwords share the fixture string; the first two typed
    # values are the passphrase + confirmation on the Partitions page.
    assert fake.typed[:2] == [drive.LUKS_PASSPHRASE, drive.LUKS_PASSPHRASE]
    assert (0.212, 0.715) not in fake.clicks


class _FakeQMPConnection:
    def quit(self) -> None:
        pass

    def cmd(self, *_a: object, **_k: object) -> None:
        pass


class _FakeQMP:
    @staticmethod
    def wait(_sock: object, deadline_s: int = 30) -> _FakeQMPConnection:
        return _FakeQMPConnection()


@pytest.mark.parametrize("flow", ["run_cancel_contract", "run_failure_cleanup"])
def test_run_flows_uncheck_encrypt_before_users_input(
    flow: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _RecordingDriver()
    monkeypatch.setattr(run.time, "sleep", lambda *_a, **_k: None)
    monkeypatch.setattr(run, "preflight_or_exit", lambda *_a, **_k: None)
    monkeypatch.setattr(run, "launch_vm", lambda *_a, **_k: None)
    monkeypatch.setattr(run, "QMP", _FakeQMP)
    monkeypatch.setattr(run, "Driver", lambda _q, _ev: fake)
    iso = tmp_path / "x.iso"
    iso.write_bytes(b"x")
    getattr(run, flow)(run.Manifest(tmp_path / "state"), iso, "sha")
    checkbox = ("click", *drive.ENCRYPT_SYSTEM_CHECKBOX)
    assert checkbox in fake.events
    first_type = next(i for i, event in enumerate(fake.events) if event[0] == "type")
    assert fake.events.index(checkbox) < first_type


def test_manifest_checkpoint_roundtrip(tmp_path: Path) -> None:
    manifest = run.Manifest(tmp_path)
    manifest.cell("desktop-uefi").update(status="executed")
    manifest.save()
    reloaded = run.Manifest(tmp_path)
    assert reloaded.data["cells"]["desktop-uefi"]["status"] == "executed"
    on_disk = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert on_disk["run_id"] == tmp_path.name


def test_runner_refuses_dirty_state_without_resume(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    iso = tmp_path / "fake.iso"
    iso.write_bytes(b"x")
    manifest = run.Manifest(tmp_path / "state")
    manifest.cell("desktop-uefi").update(status="executed")
    manifest.save()
    code = run.main(["--iso", str(iso), "--state-dir", str(tmp_path / "state")])
    assert code == 2
    assert "--resume" in capsys.readouterr().out


def test_runner_refuses_unknown_cells(tmp_path: Path) -> None:
    iso = tmp_path / "fake.iso"
    iso.write_bytes(b"x")
    assert run.main(["--iso", str(iso), "--state-dir", str(tmp_path / "s"), "--cells", "nope"]) == 2


def test_result_draft_never_claims_pass(tmp_path: Path) -> None:
    cell = drive.CELLS["desktop-uefi"]
    run.write_result_draft(cell, tmp_path, "x.iso", "abc", ["echo hi"])
    text = (tmp_path / "RESULT.draft.md").read_text(encoding="utf-8")
    assert "PENDING OPERATOR REVIEW" in text
    assert "PASS" not in text.replace("never infer PASS", "")


# --- Hardening regressions (post-#72 review) ---------------------------------

import os  # noqa: E402
import subprocess  # noqa: E402


def _dry_run(env_extra: dict[str, str]) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "OFFLINE_BUILD_DRY_RUN": "1", **env_extra}
    env.pop("OFFLINE_BUILD_HOST", None) if "OFFLINE_BUILD_HOST" not in env_extra else None
    return subprocess.run(
        ["bash", str(SCRIPTS / "build-candidate.sh")],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )


def test_build_candidate_ssh_scp_use_structured_port() -> None:
    out = _dry_run({"OFFLINE_BUILD_HOST": "builder@127.0.0.1"})
    assert out.returncode == 0, out.stderr
    assert "ssh -p 2224 builder@127.0.0.1" in out.stdout
    assert "scp -P 2224 builder@127.0.0.1:" in out.stdout
    custom = _dry_run(
        {"OFFLINE_BUILD_HOST": "u@h", "OFFLINE_BUILD_PORT": "2200", "OFFLINE_BUILD_IDENTITY": "/tmp/k"}
    )
    assert "ssh -p 2200 -i /tmp/k u@h" in custom.stdout
    assert "scp -P 2200 -i /tmp/k u@h:" in custom.stdout


def test_build_candidate_without_host_exits_4() -> None:
    out = _dry_run({})
    assert out.returncode == 4
    assert "Manual build path" in out.stderr


def _pin_manifest(state: Path, iso: Path) -> None:
    manifest = run.Manifest(state)
    manifest.data["iso"] = {"path": str(iso), "name": iso.name, "sha256": run.sha256_of(iso)}
    manifest.data["config"] = run.run_config()
    manifest.save()


def test_resume_rejects_different_iso(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    iso_a = tmp_path / "a.iso"
    iso_a.write_bytes(b"A")
    iso_b = tmp_path / "b.iso"
    iso_b.write_bytes(b"B")
    state = tmp_path / "state"
    _pin_manifest(state, iso_a)
    code = run.main(["--iso", str(iso_b), "--state-dir", str(state), "--resume", "--cells", "desktop-uefi"])
    assert code == 2
    assert "refusing --resume" in capsys.readouterr().out


def test_resume_rejects_config_change(tmp_path: Path) -> None:
    iso = tmp_path / "a.iso"
    iso.write_bytes(b"A")
    state = tmp_path / "state"
    _pin_manifest(state, iso)
    manifest = run.Manifest(state)
    manifest.data["config"] = {"vm_mib": 8192, "vm_cpus": 4, "disk_gib": 60}
    manifest.save()
    assert run.main(["--iso", str(iso), "--state-dir", str(state), "--resume", "--cells", "x"]) == 2


def test_resume_accepts_same_iso_and_skips_executed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    iso = tmp_path / "a.iso"
    iso.write_bytes(b"A")
    state = tmp_path / "state"
    _pin_manifest(state, iso)
    manifest = run.Manifest(state)
    manifest.cell("desktop-uefi").update(status="executed")
    manifest.save()
    calls: list[str] = []
    monkeypatch.setattr(run, "launch_vm", lambda *a, **k: calls.append("launch"))
    code = run.main(["--iso", str(iso), "--state-dir", str(state), "--resume", "--cells", "desktop-uefi"])
    assert code == 0
    assert calls == []  # executed checkpoint respected; nothing relaunched


def test_failed_attempt_gets_fresh_attempt_and_preserves_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = run.Manifest(tmp_path / "state")
    cell = drive.CELLS["desktop-uefi"]
    monkeypatch.setattr(run, "preflight_or_exit", lambda *a: (_ for _ in ()).throw(RuntimeError("boom")))
    run.run_cell(manifest, cell, tmp_path / "x.iso", "sha")
    run.run_cell(manifest, cell, tmp_path / "x.iso", "sha")
    record = manifest.data["cells"]["desktop-uefi"]
    assert record["status"] == "failed" and record["attempts"] == 2
    assert len(record["history"]) == 2
    assert record["history"][0]["disk"] != record["history"][1]["disk"]
    base = tmp_path / "state" / "evidence" / "desktop-uefi"
    assert (base / "attempt-1" / "RESULT.draft.md").is_file()
    assert (base / "attempt-2" / "RESULT.draft.md").is_file()


def test_final_exit_code_and_nonzero_main(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = run.Manifest(tmp_path / "s1")
    manifest.cell("desktop-uefi").update(status="executed")
    manifest.cell("studio-uefi").update(status="failed")
    assert run.final_exit_code(manifest, ["desktop-uefi"]) == 0
    assert run.final_exit_code(manifest, ["desktop-uefi", "studio-uefi"]) == 1
    assert run.final_exit_code(manifest, ["gaming-uefi"]) == 1

    iso = tmp_path / "a.iso"
    iso.write_bytes(b"A")
    state = tmp_path / "s2"

    def fake_run_cell(m: object, cell: object, iso_path: Path, sha: str) -> None:
        m.cell(cell.name).update(status="failed")  # type: ignore[attr-defined]

    monkeypatch.setattr(run, "run_cell", fake_run_cell)
    assert run.main(["--iso", str(iso), "--state-dir", str(state), "--cells", "desktop-uefi"]) == 1
    assert (state / "SUMMARY.md").is_file()
    assert (state / "manifest.json").is_file()


def _iso_with_sidecar(tmp_path: Path, revision: str | None) -> Path:
    iso = tmp_path / "cand.iso"
    iso.write_bytes(b"X")
    if revision is not None:
        iso.with_name(iso.name + ".manifest.json").write_text(
            json.dumps({"installerRevision": revision}), encoding="utf-8"
        )
    return iso


def test_cancel_gate_requires_artifact_provenance(tmp_path: Path) -> None:
    proven, _ = run.cancel_mitigation_proven(_iso_with_sidecar(tmp_path, None), None)
    assert not proven  # no sidecar -> never inferred from filename
    preview32_rev = "329e66831ad5a31e48c466771f015ef05568e571"
    proven, reason = run.cancel_mitigation_proven(_iso_with_sidecar(tmp_path, preview32_rev), None)
    assert not proven and "mitigation" in reason  # Preview 32 is not applicable
    proven, _ = run.cancel_mitigation_proven(_iso_with_sidecar(tmp_path, run.MITIGATION_REVISION), None)
    assert proven


def test_cancel_gate_descendant_via_installer_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "installer"
    repo.mkdir()
    git = ["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t"]
    subprocess.run([*git, "init", "-q"], check=True)
    (repo / "f").write_text("1")
    subprocess.run([*git, "add", "."], check=True)
    subprocess.run([*git, "commit", "-qm", "mitigation"], check=True)
    mitigation = subprocess.run([*git, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    (repo / "f").write_text("2")
    subprocess.run([*git, "commit", "-qam", "later"], check=True)
    descendant = subprocess.run([*git, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    monkeypatch.setattr(run, "MITIGATION_REVISION", mitigation)
    proven, _ = run.cancel_mitigation_proven(_iso_with_sidecar(tmp_path, descendant), repo)
    assert proven
    proven, _ = run.cancel_mitigation_proven(_iso_with_sidecar(tmp_path, descendant), None)
    assert not proven  # no repo -> ancestry unprovable -> refused


def test_cancel_gate_main_records_not_applicable(tmp_path: Path) -> None:
    iso = _iso_with_sidecar(tmp_path, "329e66831ad5a31e48c466771f015ef05568e571")
    state = tmp_path / "state"
    code = run.main(["--iso", str(iso), "--state-dir", str(state), "--cells", "cancel-contract"])
    assert code == 1
    data = json.loads((state / "manifest.json").read_text(encoding="utf-8"))
    assert data["cells"]["cancel-contract"]["status"] == "not-applicable"
    assert (state / "SUMMARY.md").is_file()


def test_runbook_recommends_single_cell_smoke() -> None:
    doc = (ROOT / "docs" / "OFFLINE-QUALIFICATION.md").read_text(encoding="utf-8")
    assert "SINGLE-CELL SMOKE" in doc
    assert "--cells desktop-uefi" in doc
    assert "executed` is not PASS" in doc
    assert "OFFLINE_BUILD_SSH" not in doc


# --- Autonomous supervised worker -------------------------------------------


def test_worker_detects_only_muse_executables() -> None:
    ps_text = """\
101 /home/u/.local/bin/muse-bin-1.4.14 --yolo resume abc
102 /usr/bin/python3 /tmp/muse-helper.py
103 /bin/sh -c pgrep -f muse-bin
104 muse --help
"""
    found = worker.find_muse_processes(ps_text)
    assert [item["pid"] for item in found] == [101, 104]


def test_worker_lock_refuses_duplicate(tmp_path: Path) -> None:
    lock = tmp_path / "worker.lock"
    with worker.exclusive_lock(lock) as first:
        assert first
        with worker.exclusive_lock(lock) as second:
            assert not second


def test_worker_waits_for_muse_then_resources(tmp_path: Path) -> None:
    status = worker.StatusWriter(
        tmp_path / "status.json", state_dir=tmp_path, iso_path=tmp_path / "x.iso", cells="desktop-uefi"
    )
    processes = iter([[{"pid": 1, "executable": "muse"}], [], []])
    preflights = iter([(False, "low RAM"), (True, "ok")])
    sleeps: list[float] = []

    def record_sleep(seconds: float) -> bool:
        sleeps.append(seconds)
        return True

    ticks = iter([0.0, 0.0, 10.0, 20.0, 30.0, 40.0, 50.0, 60.0])
    outcome = worker.wait_until_ready(
        status,
        wait_for_muse=True,
        vm_mib=4096,
        state_dir=tmp_path,
        poll_seconds=60,
        max_wait_seconds=3600,
        process_provider=lambda: next(processes),
        preflight_runner=lambda _mib, _path: next(preflights),
        sleeper=record_sleep,
        clock=lambda: next(ticks),
    )
    assert outcome == "ready"
    assert sleeps == [60, 60]
    data = json.loads((tmp_path / "status.json").read_text(encoding="utf-8"))
    assert data["status"] == "resources-ready"


def test_worker_wait_deadline_is_blocked_not_infinite(tmp_path: Path) -> None:
    status = worker.StatusWriter(
        tmp_path / "status.json", state_dir=tmp_path, iso_path=tmp_path / "x.iso", cells="desktop-uefi"
    )
    ticks = iter([0.0, 0.0, 100.0])
    outcome = worker.wait_until_ready(
        status,
        wait_for_muse=False,
        vm_mib=4096,
        state_dir=tmp_path,
        poll_seconds=60,
        max_wait_seconds=50,
        preflight_runner=lambda _mib, _path: (False, "low RAM"),
        sleeper=lambda _seconds: True,
        clock=lambda: next(ticks),
    )
    assert outcome == "blocked"


def _worker_args(tmp_path: Path, iso: Path) -> object:
    return worker.parse_args(
        [
            "--iso",
            str(iso),
            "--cells",
            "desktop-uefi",
            "--state-dir",
            str(tmp_path / "state"),
            "--status-file",
            str(tmp_path / "status.json"),
            "--lock-file",
            str(tmp_path / "worker.lock"),
            "--log-file",
            str(tmp_path / "runner.log"),
        ]
    )


def test_worker_command_resumes_only_existing_manifest(tmp_path: Path) -> None:
    iso = tmp_path / "x.iso"
    iso.write_bytes(b"x")
    args = _worker_args(tmp_path, iso)
    assert "--resume" not in worker.build_runner_command(args)
    state = tmp_path / "state"
    state.mkdir()
    (state / "manifest.json").write_text("{}", encoding="utf-8")
    assert "--resume" in worker.build_runner_command(args)


def test_worker_execute_records_completion_without_claiming_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    iso = tmp_path / "x.iso"
    iso.write_bytes(b"x")
    args = _worker_args(tmp_path, iso)
    monkeypatch.setattr(worker, "install_signal_handlers", lambda: None)
    monkeypatch.setattr(worker, "wait_until_ready", lambda *_a, **_k: "ready")
    monkeypatch.setattr(worker, "run_runner", lambda *_a, **_k: 0)
    assert worker.execute(args) == 0
    data = json.loads((tmp_path / "status.json").read_text(encoding="utf-8"))
    assert data["status"] == "completed"
    assert "PASS" not in json.dumps(data)


def test_worker_execute_rejects_iso_hash_mismatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    iso = tmp_path / "x.iso"
    iso.write_bytes(b"x")
    args = _worker_args(tmp_path, iso)
    args.expected_sha256 = "0" * 64  # type: ignore[attr-defined]
    monkeypatch.setattr(worker, "install_signal_handlers", lambda: None)
    assert worker.execute(args) == 3
    data = json.loads((tmp_path / "status.json").read_text(encoding="utf-8"))
    assert data["status"] == "blocked"
    assert data["reason"] == "ISO SHA-256 mismatch"


def test_worker_targets_only_execution_owned_muse_pid(tmp_path: Path) -> None:
    ps_text = """\
364422 /home/u/.local/bin/muse-bin-1.4.14 --yolo resume this-session
2489940 /home/u/.local/bin/muse-bin-1.4.14 --yolo
3000001 /usr/bin/python3 unrelated
"""
    monkeypatch_ps = ps_text
    assert worker.find_muse_processes(monkeypatch_ps)
    targeted = [item for item in worker.find_muse_processes(monkeypatch_ps) if int(item["pid"]) in {364422}]
    assert [item["pid"] for item in targeted] == [364422]
    pid_file = tmp_path / "muse.pid"
    pid_file.write_text("364422, 2489940\n", encoding="utf-8")
    assert worker.read_pid_file(pid_file) == {364422, 2489940}
    args = worker.parse_args(
        [
            "--iso",
            str(tmp_path / "x.iso"),
            "--cells",
            "desktop-uefi",
            "--state-dir",
            str(tmp_path / "state"),
            "--status-file",
            str(tmp_path / "status.json"),
            "--lock-file",
            str(tmp_path / "lock"),
            "--log-file",
            str(tmp_path / "log"),
        ]
    )
    assert not hasattr(args, "vm_mib")


def test_coordinator_waits_for_terminal_and_builds_review(tmp_path: Path) -> None:
    status_path = tmp_path / "coordinator.json"
    states = iter(["waiting-for-muse-exit", "running", "completed"])
    ticks = iter([0.0, 0.0, 10.0, 20.0, 30.0, 40.0])
    outcome = coordinator.wait_for_terminal(
        tmp_path / "worker.json",
        status_path,
        poll_seconds=10,
        max_wait_seconds=3600,
        status_reader=lambda _path: next(states),
        sleeper=lambda _seconds: True,
        clock=lambda: next(ticks),
    )
    assert outcome == "completed"
    args = coordinator.parse_args(
        [
            "--worker-status-file",
            str(tmp_path / "worker.json"),
            "--status-file",
            str(status_path),
            "--lock-file",
            str(tmp_path / "lock"),
            "--log-file",
            str(tmp_path / "log"),
            "--prompt-file",
            str(tmp_path / "prompt.md"),
            "--workspace",
            str(tmp_path),
            "--muse-bin",
            "muse-test",
        ]
    )
    assert coordinator.build_review_command(args) == [
        "muse-test",
        "exec",
        "--yolo",
        "--workspace",
        str(tmp_path),
        "--prompt-file",
        str(tmp_path / "prompt.md"),
    ]
    unit = (SCRIPTS / "hornero-offline-coordinator.service").read_text(encoding="utf-8")
    assert "coordinator.py" in unit and "KillMode=control-group" in unit


def test_worker_systemd_unit_contract() -> None:
    unit = (SCRIPTS / "hornero-offline-qualification.service").read_text(encoding="utf-8")
    assert "worker.py" in unit
    assert "--cells desktop-uefi" in unit
    assert "b8cd0f8604bc69f7d2112fb8bccd97115d32d197e9c92c62e02faf5de6345aec" in unit
    assert "KillMode=control-group" in unit
    assert "Restart=no" in unit
    assert "--wait-for-pid-file" in unit
    assert "After=default.target" not in unit
    doc = (ROOT / "docs" / "OFFLINE-QUALIFICATION.md").read_text(encoding="utf-8")
    assert "Autonomous supervised execution" in doc


def test_worker_ps_failure_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    class Result:
        returncode = 1
        stdout = ""
        stderr = "ps unavailable"

    monkeypatch.setattr(worker.subprocess, "run", lambda *_a, **_k: Result())
    with pytest.raises(RuntimeError, match="ps exited 1"):
        worker.list_muse_processes()


def test_worker_qemu_cleanup_stops_only_new_runner_vms() -> None:
    ps_text = """\
201 /usr/bin/qemu-system-x86_64 -name hornero-install-p33off-desktop-uefi-a1 -pidfile /tmp/a1.pid
202 /usr/bin/qemu-system-x86_64 -name other -pidfile /tmp/other.pid
203 /usr/bin/qemu-system-x86_64 -name hornero-install-p33off-desktop-uefi-a2 -pidfile /tmp/a2.pid
"""
    found = worker.find_runner_qemu_processes(ps_text)
    assert [item["pid"] for item in found] == [201, 203]
    calls: list[tuple[int, int]] = []
    listings = iter([found, []])
    stopped = worker.stop_new_runner_qemu_processes(
        {201},
        process_provider=lambda: next(listings),
        signaler=lambda pid, sig: calls.append((pid, sig)),
        sleeper=lambda _seconds: None,
    )
    assert stopped == [203]
    assert calls == [(203, worker.signal.SIGTERM)]


def test_runner_rejects_expected_sha256_mismatch(tmp_path: Path) -> None:
    iso = tmp_path / "x.iso"
    iso.write_bytes(b"x")
    state = tmp_path / "state"
    code = run.main(
        [
            "--iso",
            str(iso),
            "--state-dir",
            str(state),
            "--cells",
            "desktop-uefi",
            "--expected-sha256",
            "0" * 64,
        ]
    )
    assert code == 2
    data = json.loads((state / "manifest.json").read_text(encoding="utf-8"))
    assert data["iso"] is None


def test_worker_forwards_expected_sha256_and_resolved_installer_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    iso = tmp_path / "x.iso"
    iso.write_bytes(b"x")
    args = _worker_args(tmp_path, iso)
    args.expected_sha256 = "a" * 64  # type: ignore[attr-defined]
    args.installer_repo = Path("relative-installer")  # type: ignore[attr-defined]
    args.log_file = tmp_path / "new-log-dir" / "runner.log"  # type: ignore[attr-defined]
    monkeypatch.setattr(worker, "install_signal_handlers", lambda: None)
    monkeypatch.setattr(worker, "verify_expected_iso", lambda *_a, **_k: True)
    monkeypatch.setattr(worker, "wait_until_ready", lambda *_a, **_k: "ready")
    captured: dict[str, list[str]] = {}

    def fake_run_runner(command: list[str], _log: Path) -> int:
        captured["command"] = command
        return 0

    monkeypatch.setattr(worker, "run_runner", fake_run_runner)
    assert worker.execute(args) == 0
    assert "--expected-sha256" in captured["command"]
    assert args.installer_repo.is_absolute()  # type: ignore[attr-defined]
    assert (tmp_path / "new-log-dir" / "runner.log").is_file()
    assert not hasattr(args, "vm_mib")
