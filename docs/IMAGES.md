# Ready images

A **ready image** is a provisioned Arch guest with one exact Hornero
composition baked in: shell tree + native plugin at a shell SHA, the config
pin built and installed as `hornero-config`, and a `horneroctl` binary. Runs
never write to it; every attempt boots a throwaway qcow2 overlay.

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
  "runtime_packages": ["papirus-icon-theme", "qt6ct", "dunst", "libnotify", "jq", "hyprlock", "gtk3", "ttf-ibm-plex"],
  "aur_runtime_packages": []
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

Use `--compositor niri` to build a separate Niri image. The builder installs
Niri, XWayland Satellite, the GNOME screencast portal and GTK portal fallback,
then records the compositor in the image sidecar. `grim` captures screenshots
from inside the guest's Wayland session, and `rtkit` satisfies the PipeWire
realtime service used by the GNOME portal. The QA TTY profile exports the
source-built Quickshell plugin path into Niri's service environment. The base Arch image and the
default Hyprland composition remain untouched. Scenarios can require a
specific compositor; the runner refuses an image with different provenance
instead of silently testing another session. The first Niri journey is
`compositors/niri-desktop-baseline`.

The builder defaults to 4 GiB/4 vCPUs. `--mem-mb` (1–8 GiB) and `--cpus`
(1–8) set explicit guest budgets; QEMU remains inside a user systemd scope
whose memory cap adds 1.2 GiB for emulator overhead. On a constrained host,
use `--mem-mb 2048 --cpus 2` and run no other graphical VM at the same time.

The refresh refuses a dirty shell checkout or an abbreviated config SHA. It
runs QEMU inside `systemd-run --user --scope -p MemoryMax=...`; run one heavy
job at a time.

What the mint adds on top of the composition:

- Hyprland images use `guest/hyprland.lua` (Hyprland 0.57+ prefers the Lua
  entrypoint and HorneroOS/config ships only Lua), which `dofile`s the
  product's `environment`, `input`, `layout`, `helpers`, `keybindings`,
  `window-rules`, `smart-colors` and `static` fragments from
  `~/.config/hypr/hyprland.lua.d/`, so product binds, rules and Signal border
  colours are exercised as shipped. The mint verifies every fragment exists,
  removes any stale `hyprland.conf`, fixes `Virtual-1`/`Virtual-2` outputs and
  disables animations. Runtime changes inside the guest go through
  `hyprctl eval '<lua>'`; `hyprctl keyword` answers "unknown request" with
  exit status 0 on a Lua config.
- tty1 autologin into the selected compositor and a serial readiness marker
  (`HORNERO-SHELL-READY`). The marker is diagnostic only; readiness is
  proven by the shell's IPC answering.
- `shell.json` idle timeouts disabled (a locking guest would poison runs).
- No AUR runtime packages. Hornero Signal themes are schema-v2 role tables
  rendered by hornero-config's stdlib Python, so the retired M3 generator
  (`python-materialyoucolor`) and recipe pipeline (`python-pywal16`) are gone.
  `ttf-ibm-plex` (the Signal type families, RFC 0001 §3.3) is named explicitly
  so the image stays honest if a package drops the dependency.
- The selected-wallpaper pointer is set to the factory theme's packaged
  artwork (`hornero-signal-night`, RFC 0001 §9) so the desktop never renders
  a black fallback after the deploy copies are removed.
- Runtime packages a Hornero desktop needs (Papirus icons, `qt6ct`). `dunst`
  is installed **on purpose**: notification acceptance must prove the shell
  owns `org.freedesktop.Notifications` with a competitor present.
- The exact config pin is built and installed as a system package. The
  materialized user theme and wallpaper copies are removed afterward, so
  appearance acceptance resolves those assets from `/usr/share`.
- Welcome onboarding marked as seen.

For a Niri image, the disposable guest starts `niri --session` from tty1.
This follows Niri's documented direct TTY session mode and avoids nesting a
second login shell inside the QA autologin profile. The package-owned
`/etc/niri/config.kdl` fallback starts Hornero Shell. Niri evidence is captured
inside the guest with `grim`, because QEMU's GL display has no pixman surface.
The image builder records its selected compositor and adds Niri, XWayland
Satellite, the GNOME screencast portal, and the GTK fallback/file chooser. The
base Arch image is unchanged. The current Niri scenario covers one output,
Niri-native workspace/window state, theme selection, Launcher, Kitty, and
Layout Picker; it does not certify the remaining compositor support matrix.

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

## Validating Hornero Signal in the QA VM

This is the runbook other workstreams (shell surfaces, layouts, experience
modes, plugins) use to validate Signal visually. The guest is disposable;
the host session is never touched.

Rules of the road:

- **One graphical VM at a time, machine-wide.** Wrap every run in `flock` on
  the shared mission lock so parallel agents serialise instead of colliding:

  ```sh
  flock ~/.local/share/hornero-signal-mission/vm.lock \
    uv run hornero-qa run smoke/desktop-ready
  ```

- **Budgets:** guest ≤ 3 GiB RAM and ≤ 3 vCPUs. `run` defaults to 2048 MiB
  (`--mem-mb`); for `image refresh` pass `--mem-mb 3072 --cpus 3` (the builder
  defaults are 4 GiB/4 vCPUs). QEMU always runs inside a memory-capped
  `systemd-run --user --scope`.
- **Never** drive the host's compositor, shell or display manager, and never
  screenshot host outputs. Anything that could write config/state outside the
  VM runs with `XDG_CONFIG_HOME`/`XDG_STATE_HOME`/`XDG_DATA_HOME`/
  `XDG_CACHE_HOME` pointed at a scratch dir; compare
  `sha256sum ~/.config/hornero/shell.json` before/after and stop if it moved.
- State (images, runs, overlays) lives under `~/.local/share/hornero/qa/`
  (`$HORNERO_QA_STATE` overrides). Nothing large goes to `/tmp`.

Current ready images in `~/.local/share/hornero/qa/images/` (2026-11-16;
`current.qcow2`/`current.json` symlink to the default):

| Image | Composition |
|---|---|
| `signal-s6e880f2-c64b0c46-hdaa03b0.qcow2` (current) | shell `6e880f2`, config `64b0c46`, horneroctl `daa03b0` — Signal mains |
| `signal-s5651dd2-cc5f96a7-h421a593.qcow2` | earlier Signal composition (bisect) |
| `arch-provisioned-yay-20261116.qcow2` | provisioned base for `image refresh` |

Image names encode the first 7 hex of shell/config/horneroctl SHAs; the
`.json` sidecar is the provenance of record. A shell change is only in the VM
once a new image is minted from its merged SHA:

```sh
git -C ../shell worktree add --detach ~/.local/share/hornero/qa/work/shell-<sha> <sha>
flock ~/.local/share/hornero-signal-mission/vm.lock uv run hornero-qa image refresh \
  --base ~/.local/share/hornero/qa/images/arch-provisioned-yay-20261116.qcow2 \
  --shell ~/.local/share/hornero/qa/work/shell-<sha> \
  --config-sha <40-hex config SHA> \
  --horneroctl <horneroctl binary> \
  --name signal-s<shell7>-c<config7>-h<ctl7> --mem-mb 3072 --cpus 3
```

Run loop:

```sh
uv run hornero-qa doctor                 # KVM, QEMU, current image, memory
uv run hornero-qa list                   # scenario ids
uv run hornero-qa validate               # schema + anchors (no VM)
flock ~/.local/share/hornero-signal-mission/vm.lock \
  uv run hornero-qa run smoke/desktop-ready [more scenarios...] [--repeat 3] [--json]
uv run hornero-qa inspect ~/.local/share/hornero/qa/runs/<run-id>
```

Reading results: every run writes an evidence bundle under `runs/<run-id>/`
(screenshots, `actions.jsonl`, logs incl. `signal-scheme.json` when a live
scheme was applied, and the image provenance). Exit codes: 0 pass, 1 any
fail, 2 inconclusive only, 64 usage. **Open every screenshot** — a PASS with
an ugly frame is a finding, not a success. Compare against
`signal-visual-language.md` (Signal Bezel) and the concept specimens; Signal
(immersive) mode must look visibly richer than everyday, and Cockpit Clear
means a zero-opacity bar background with adaptive per-region ink.

Signal-specific gotchas inside the guest:

- Themes are schema-v2 role tables. Built-ins: `hornero-signal-night`
  (factory), `hornero-signal-day`, `hornero-signal-contrast`. Retired M3 ids
  (`hornero-dark`, `hornero-light`, …) no longer exist; scenarios still naming
  them need a human-reviewed update, not a runtime workaround.
- Apply with `horneroctl appearance theme apply <id> --yes` (or the scenario
  `setup.theme`, which uses `theme set`); verify with
  `qs ipc call signal theme` and `horneroctl appearance theme get`.
- The live scheme is `~/.local/state/hornero/signal/scheme.json`
  (`{"schemaVersion": 2, "id", "mode", "palette", "terminal"}`). Wallpaper
  changes never recolour the UI.
- Hyprland is Lua-only in the guest: use `hyprctl eval '<lua>'` for runtime
  changes; `hyprctl keyword` silently no-ops ("unknown request", exit 0).

## Known product gaps the image works around

Each workaround is recorded in the image sidecar and removed when the
product fix lands:

| Gap | Workaround | Tracking |
|---|---|---|
| This QA image still seeds curated shell presets for layout journeys | the mint seeds `~/.local/share/hornero/shell-presets` from the shell tree under test; appearance packs and media come from the exact `hornero-config` package | shell#95 package integration |
