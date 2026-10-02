"""Ready images: a provisioned guest + a composition at exact SHAs.

`refresh` takes an already provisioned base image (Arch + Hyprland +
quickshell + build deps), boots it with network, and composes the product
under test into it by CALLING HorneroOS/shell `tests/vm/lib/deploy-shell.sh`
from a shell checkout at the pinned SHA (shell tree + native plugin + config
pin materialized + horneroctl validation + factory defaults). It then mints
the QA session (guest/), installs the runtime packages a Hornero desktop
expects, and flattens the result into a standalone qcow2 with a provenance
sidecar. The base image is never modified.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import time
from pathlib import Path

from hornero_qa.engines.native import _free_port, write_image_info
from hornero_qa.scenario import REPO_ROOT
from hornero_qa.state import QAState

GUEST_DIR = REPO_ROOT / "guest"
CONFIG_REPO = "https://github.com/HorneroOS/config"
# Packages a Hornero desktop needs at runtime that the base provisioning does
# not guarantee. dunst is installed on purpose: notification-ownership
# acceptance must prove the shell wins the bus name with a competitor present.
# hyprlock is a horneroctl dependency (Control Center can launch it), needed
# for the cross-locker regression (HorneroOS/shell#24). gtk3 is on every
# desktop that runs a GTK app (hornero-config optdepends it) and pulls in
# gsettings-desktop-schemas, which the shell's native GTK theming writes to.
RUNTIME_PACKAGES = [
    "papirus-icon-theme",
    "qt6ct",
    "dunst",
    "libnotify",
    "jq",
    "hyprlock",
    "gtk3",
]
# AUR runtime dependencies the Hornero packages declare: M3 generation
# requires python-materialyoucolor; recipe themes require python-pywal16's
# `wal` command. Install with the base image's yay like package installs.
AUR_RUNTIME_PACKAGES = ["python-materialyoucolor", "python-pywal16"]


def _ssh(state: QAState, port: int, command: str, timeout: float = 1800) -> None:
    subprocess.run(
        [
            "ssh",
            "-4",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
            "-o",
            "LogLevel=ERROR",
            "-o",
            "BatchMode=yes",
            "-i",
            str(state.ssh_key),
            "-p",
            str(port),
            f"{state.guest_user}@127.0.0.1",
            command,
        ],
        check=True,
        timeout=timeout,
    )


def _scp(state: QAState, port: int, src: Path, dst: str) -> None:
    subprocess.run(
        [
            "scp",
            "-4",
            "-O",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
            "-o",
            "LogLevel=ERROR",
            "-i",
            str(state.ssh_key),
            "-P",
            str(port),
            str(src),
            f"{state.guest_user}@127.0.0.1:{dst}",
        ],
        check=True,
    )


def refresh(
    state: QAState,
    base: Path,
    shell_checkout: Path,
    config_sha: str,
    horneroctl: Path,
    name: str,
    mem_mb: int = 4096,
) -> Path:
    if not re.fullmatch(r"[0-9a-f]{40}", config_sha):
        raise SystemExit(f"--config-sha must be a full 40-hex SHA, got {config_sha!r}")
    shell_sha = subprocess.run(
        ["git", "-C", str(shell_checkout), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "-C", str(shell_checkout), "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    if dirty:
        raise SystemExit(f"shell checkout {shell_checkout} is dirty: images must be built from a clean SHA")
    state.ensure()
    build = state.work_dir / f"build-{name}"
    shutil.rmtree(build, ignore_errors=True)
    build.mkdir(parents=True)
    overlay = build / "overlay.qcow2"
    subprocess.run(
        ["qemu-img", "create", "-q", "-f", "qcow2", "-F", "qcow2", "-b", str(base.resolve()), str(overlay)],
        check=True,
    )
    port = _free_port()
    log = (build / "qemu.log").open("wb")
    proc = subprocess.Popen(
        [
            "systemd-run",
            "--user",
            "--scope",
            "--quiet",
            f"--unit=hornero-qa-build-{name}",
            "-p",
            f"MemoryMax={mem_mb + 1200}M",
            "--",
            "qemu-system-x86_64",
            "-enable-kvm",
            "-cpu",
            "host",
            "-machine",
            "q35",
            "-smp",
            "4",
            "-m",
            str(mem_mb),
            "-device",
            "virtio-vga",
            "-drive",
            f"file={overlay},format=qcow2,if=virtio",
            "-netdev",
            f"user,id=net0,dns=9.9.9.9,hostfwd=tcp:127.0.0.1:{port}-:22",
            "-device",
            "virtio-net-pci,netdev=net0",
            "-display",
            "none",
            "-serial",
            f"file:{build / 'serial.log'}",
        ],
        stdout=subprocess.DEVNULL,
        stderr=log,
    )
    try:
        for _ in range(180):
            try:
                _ssh(state, port, "true", timeout=10)
                break
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                time.sleep(2)
        else:
            raise SystemExit("builder VM never answered SSH")

        env = os.environ | {
            "VM_SSH_PORT": str(port),
            "VM_SSH_KEY": str(state.ssh_key),
            "VM_SSH_USER": state.guest_user,
            "VM_CACHE_DIR": str(build / "cache"),
            "VM_ARTIFACTS_DIR": str(build / "artifacts"),
            "HX_CONFIG_PIN": f"{CONFIG_REPO} {config_sha}",
            "HX_HOREROCTL_BIN": str(horneroctl),
            "V_C_ERROR_BUG_REPORT_DISABLED": "1",
        }
        subprocess.run(["bash", str(shell_checkout / "tests/vm/lib/deploy-shell.sh")], env=env, check=True)
        _mint(state, port, horneroctl)
        # The connection drops while the guest powers off, so ssh may exit
        # 255 even on success: QEMU exiting is the real signal.
        with contextlib.suppress(subprocess.CalledProcessError, subprocess.TimeoutExpired):
            _ssh(state, port, "sudo systemctl poweroff --no-block", timeout=60)
        proc.wait(timeout=180)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
    out = state.images_dir / f"{name}.qcow2"
    tmp = out.with_suffix(".qcow2.tmp")
    subprocess.run(["qemu-img", "convert", "-O", "qcow2", "-c", str(overlay), str(tmp)], check=True)
    tmp.replace(out)
    ctl_version = subprocess.run([str(horneroctl), "version"], capture_output=True, text=True).stdout.strip()
    write_image_info(
        out,
        {
            "schema": "hornero.qa.image/1",
            "name": name,
            "built": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "base": str(base.name),
            "product": {
                "shell_sha": shell_sha,
                "config_sha": config_sha,
                "horneroctl": ctl_version.splitlines()[0] if ctl_version else "unknown",
                "horneroctl_sha256": hashlib.sha256(horneroctl.read_bytes()).hexdigest(),
            },
            "runtime_packages": RUNTIME_PACKAGES,
            "aur_runtime_packages": AUR_RUNTIME_PACKAGES,
            "catalogues": {
                "shell_presets": "user catalogue seeded from shell presets/",
                "themes": "hornero-config system package; user copies removed",
                "wallpapers": "hornero-config system package; user copies removed",
            },
        },
    )
    shutil.rmtree(build, ignore_errors=True)
    set_current(state, out)
    return out


def _mint(state: QAState, port: int, horneroctl: Path) -> None:
    """Install the QA session and runtime packages into the builder guest."""
    with tempfile.TemporaryDirectory(dir=state.work_dir) as tmp:
        bundle = Path(tmp) / "guest.tar"
        with tarfile.open(bundle, "w") as tar:
            tar.add(GUEST_DIR, arcname="guest")
        _scp(state, port, bundle, "/tmp/qa-guest.tar")
    _scp(state, port, horneroctl, "/tmp/horneroctl")
    pkgs = " ".join(RUNTIME_PACKAGES)
    aur = " ".join(AUR_RUNTIME_PACKAGES)
    _ssh(
        state,
        port,
        f"""set -e
# Stop the builder's own desktop session first: a running Hyprland that sees
# its config missing (even for an instant) writes its autogenerated default
# into the same path, interleaving with ours.
sudo systemctl stop getty@tty1.service || true
pkill -x Hyprland || true
for _ in $(seq 1 20); do pgrep -x Hyprland > /dev/null || break; sleep 0.5; done
# Atomic writes: never leave the destination missing or half-written.
put() {{ install -D -m "$1" "$2" "$3.qa-tmp" && mv -f "$3.qa-tmp" "$3"; }}
sudo install -m 0755 /tmp/horneroctl /usr/local/bin/horneroctl && rm -f /tmp/horneroctl
rm -rf /tmp/qa && mkdir -p /tmp/qa && tar xf /tmp/qa-guest.tar -C /tmp/qa && G=/tmp/qa/guest
put 0644 $G/hyprland.conf ~/.config/hypr/hyprland.conf
cmp -s $G/hyprland.conf ~/.config/hypr/hyprland.conf
put 0755 $G/qa-session.sh ~/.local/bin/qa-session.sh
put 0755 $G/qa-shell.sh ~/.local/bin/qa-shell.sh
put 0644 $G/bash_profile ~/.bash_profile
sudo install -Dm0644 $G/autologin.conf /etc/systemd/system/getty@tty1.service.d/autologin.conf
python3 - <<'PY'
import json, pathlib
p = pathlib.Path.home() / ".config/hornero/shell.json"
cur = json.loads(p.read_text()) if p.exists() and p.read_text().strip() else {{}}
over = json.loads(pathlib.Path("/tmp/qa/guest/shell.json").read_text())
cur.setdefault("general", {{}}).update(over["general"])
p.parent.mkdir(parents=True, exist_ok=True)
p.write_text(json.dumps(cur, indent=2))
PY
# User preset catalogue (PATH_CONTRACT row 2) seeded from the shell tree under
# test, as the dotfiles migration does on existing hosts. Package installs do
# not populate it yet (see docs/IMAGES.md "Known product gaps").
install -d ~/.local/share/hornero/shell-presets
install -m0644 ~/.config/quickshell/presets/*.json ~/.local/share/hornero/shell-presets/
sudo pacman -Sy --noconfirm --needed {pkgs}
yay -S --noconfirm --needed --removemake \
  --answerclean None --answerdiff None --answeredit None --answerupgrade None {aur}
# Build/install the exact config pin as its system package. The shell deploy
# step also materializes defaults into a staging HOME for validation; that
# user tree must not be the only source of product catalogues in a ready image.
test -d "$HOME/hx-config/packaging"
(cd "$HOME/hx-config/packaging" && makepkg --syncdeps --install --noconfirm --cleanbuild)
sudo test -d /usr/share/hornero/themes
sudo test -d /usr/share/hornero/wallpapers
# Keep factory user preferences, but remove recipe/media copies so theme QA
# proves the installed package path rather than the deploy helper's HOME copy.
rm -rf "$HOME/.local/share/hornero/themes" "$HOME/.local/share/dots/themes"
rm -rf "$HOME/.local/share/hornero/wallpapers" "$HOME/.local/share/dots/wallpapers"
sudo gpasswd -a "$USER" uucp > /dev/null
sudo touch /etc/cloud/cloud-init.disabled
/usr/local/bin/horneroctl welcome set-show-on-login false --yes || true
/usr/local/bin/horneroctl welcome mark-seen --yes || true
rm -rf /tmp/qa /tmp/qa-guest.tar ~/.cache/yay ~/.cache/hornero-shell-build
sudo pacman -Scc --noconfirm > /dev/null 2>&1 || true
sync""",
    )


def adopt(state: QAState, image: Path, name: str, ssh_key: Path | None, product: dict[str, str]) -> Path:
    """Register an image built elsewhere (symlinked, never copied) with declared provenance."""
    state.ensure()
    out = state.images_dir / f"{name}.qcow2"
    out.unlink(missing_ok=True)
    out.symlink_to(image.resolve())
    if ssh_key is not None and not state.ssh_key.exists():
        shutil.copyfile(ssh_key, state.ssh_key)
        state.ssh_key.chmod(0o600)
    write_image_info(
        out,
        {
            "schema": "hornero.qa.image/1",
            "name": name,
            "adopted": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "source": str(image.resolve()),
            "product": product,
        },
    )
    set_current(state, out)
    return out


def set_current(state: QAState, image: Path) -> None:
    current = state.current_image()
    for link, target in (
        (current, image.name),
        (current.with_suffix(".json"), image.with_suffix(".json").name),
    ):
        link.unlink(missing_ok=True)
        link.symlink_to(target)
