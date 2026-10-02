"""Host-side state locations. Never under the repo, never under /tmp.

Default root: $HORNERO_QA_STATE or ~/.local/share/hornero/qa
    images/   ready images (*.qcow2 + *.json provenance)
    runs/     evidence bundles
    work/     per-run overlays and sockets (deleted after each run)
    ssh/      guest SSH key (never committed; $HORNERO_QA_SSH_KEY overrides)
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class QAState:
    root: Path
    guest_user: str = "hornero"

    @classmethod
    def default(cls) -> QAState:
        env = os.environ.get("HORNERO_QA_STATE")
        root = Path(env) if env else Path.home() / ".local/share/hornero/qa"
        return cls(root=root.expanduser())

    @property
    def images_dir(self) -> Path:
        return self.root / "images"

    @property
    def runs_dir(self) -> Path:
        return self.root / "runs"

    @property
    def work_dir(self) -> Path:
        return self.root / "work"

    @property
    def ssh_key(self) -> Path:
        env = os.environ.get("HORNERO_QA_SSH_KEY")
        return Path(env).expanduser() if env else self.root / "ssh" / "id_ed25519"

    def ensure(self) -> None:
        for d in (self.images_dir, self.runs_dir, self.work_dir, self.ssh_key.parent):
            d.mkdir(parents=True, exist_ok=True)

    def current_image(self) -> Path:
        """The image `current.qcow2` points at (a symlink maintained by `image build`)."""
        return self.images_dir / "current.qcow2"
