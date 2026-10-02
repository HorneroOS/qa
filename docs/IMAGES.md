# Ready images

A **ready image** is a provisioned Arch guest with one exact Hornero
composition baked in: shell tree + native plugin at a shell SHA, the config
pin materialized, and a `horneroctl` binary. Runs never write to it; every
attempt boots a throwaway qcow2 overlay.

## Where state lives

Everything is outside the repository and outside `/tmp`:

```text
~/.local/share/hornero/qa/          ($HORNERO_QA_STATE overrides)
  images/<name>.qcow2 + <name>.json  ready images + provenance sidecar
  images/current.qcow2 (+ .json)     symlinks to the default image
  runs/<run-id>/                     evidence bundles
  work/                              per-run overlays, sockets (cleaned up)
  ssh/id_ed25519                     guest key ($HORNERO_QA_SSH_KEY overrides)
```

Image and key files are rejected by repository governance
(`**/*.qcow2`, `**/id_ed25519*`).

## Provenance sidecar (`hornero.qa.image/1`)

```json
{
  "schema": "hornero.qa.image/1",
  "name": "p13-shell-25d2206",
  "built": "2026-10-02T01:05:00Z",
  "base": "hornero-ready.qcow2",
  "product": {
    "shell_sha": "<40-hex>",
    "config_sha": "<40-hex>",
    "horneroctl": "horneroctl horneroctl-v0.2.0-preview13-dirty (8557401)",
    "horneroctl_sha256": "<64-hex>"
  },
  "runtime_packages": ["papirus-icon-theme", "qt6ct", "dunst", "libnotify", "jq"],
  "aur_runtime_packages": ["python-materialyoucolor"]
}
```

Every evidence bundle copies this block into `run.json` and every screenshot
sidecar, so a picture always says which composition produced it.

## Refreshing an image

`image refresh` boots a provisioned base image (never modified), composes
the product by **calling the shell's own harness**
(`HorneroOS/shell tests/vm/lib/deploy-shell.sh`) from a clean shell checkout
at the SHA under test, then mints the QA session (`guest/`) and flattens the
result:

```sh
git -C ../shell worktree add --detach ~/.local/share/hornero/qa/work/shell-<sha> <sha>
uv run hornero-qa image refresh \
  --base <provisioned-base.qcow2> \
  --shell ~/.local/share/hornero/qa/work/shell-<sha> \
  --config-sha <40-hex config SHA> \
  --horneroctl <horneroctl binary, e.g. the release asset> \
  --name <name>
uv run hornero-qa image info
```

The refresh refuses a dirty shell checkout or an abbreviated config SHA. It
runs QEMU inside `systemd-run --user --scope -p MemoryMax=...`; run one heavy
job at a time.

What the mint adds on top of the composition:

- `guest/hyprland.conf`: sources the product's `environment`, `input`,
  `layout`, `window-rules` and `keybindings` fragments, so product binds are
  exercised as shipped; fixed `Virtual-1`/`Virtual-2` outputs; animations off.
- tty1 autologin into Hyprland and a serial readiness marker
  (`HORNERO-SHELL-READY`). The marker is diagnostic only; readiness is
  proven by the shell's IPC answering.
- `shell.json` idle timeouts disabled (a locking guest would poison runs).
- AUR runtime dependencies the Hornero packages declare
  (`python-materialyoucolor`, required by `hornero-config` since
  HorneroOS/config#46), installed with the base image's `yay`.
- Runtime packages a Hornero desktop needs (Papirus icons, `qt6ct`). `dunst`
  is installed **on purpose**: notification acceptance must prove the shell
  owns `org.freedesktop.Notifications` with a competitor present.
- Welcome onboarding marked as seen.

## Adopting an existing image

`image adopt <path> --name <name> [--ssh-key <key>] [--product k=v ...]`
symlinks an image built elsewhere and records declared provenance. Use it
for bootstrap or bisect images; evidence from adopted images carries
whatever provenance was declared, so prefer `refresh` for release evidence.

## Base images

A base image is the shell harness's provisioned cloud image (Arch +
Hyprland + Quickshell + build dependencies). Building one from scratch uses
the shell harness (`tests/vm/lib/boot.sh` with cloud-init); this repository
consumes it and does not duplicate that provisioning.

## Known product gaps the image works around

Each workaround is recorded in the image sidecar and removed when the
product fix lands:

| Gap | Workaround | Tracking |
|---|---|---|
| Package installs ship presets/themes where `horneroctl` does not read them | the mint seeds `~/.local/share/hornero/shell-presets` from the shell tree under test | [hornero#96](https://github.com/HorneroOS/hornero/issues/96) |
