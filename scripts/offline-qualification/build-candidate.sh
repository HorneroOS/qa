#!/usr/bin/env bash
# Build ONE Preview 33 candidate ISO inside the disposable build VM.
#
# Runs on the HOST (maintainer-executed, Muse closed). It preflights
# for the build VM's 8 GiB, launches the existing build VM, clones the
# installer at current origin/main INSIDE the VM (clean checkout, as
# build-iso.sh requires), builds as root via the installer's own
# scripts/build-iso.sh, and copies the ISO + sidecar manifest out.
# Provenance (installer HEAD, hashes) is printed and saved next to the
# artifact; signing stays on the established maintainer workflow
# (scripts/sign-release.sh in installer) and is NOT performed here.
#
# Connection configuration (structured — never a word-split string):
#   OFFLINE_BUILD_HOST      ssh destination, e.g. builder@127.0.0.1 (required)
#   OFFLINE_BUILD_PORT      ssh/scp port (default 2224)
#   OFFLINE_BUILD_IDENTITY  optional ssh identity file
# Optional:
#   BUILD_VM_LAUNCHER   default ~/.local/share/hornero/run-build-vm.sh
#   CANDIDATE_OUT       default ~/hornero-p33-offline/candidate
#   OFFLINE_BUILD_DRY_RUN=1  print the ssh/scp command lines and exit 0
set -euo pipefail

HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
LAUNCHER=${BUILD_VM_LAUNCHER:-$HOME/.local/share/hornero/run-build-vm.sh}
OUT=${CANDIDATE_OUT:-$HOME/hornero-p33-offline/candidate}
PORT=${OFFLINE_BUILD_PORT:-2224}

if [[ -z "${OFFLINE_BUILD_HOST:-}" ]]; then
  cat >&2 <<'EOF'
OFFLINE_BUILD_HOST is not set. Manual build path:
  1. ~/.local/share/hornero/run-build-vm.sh        # boots the 8 GiB build VM (SSH :2224)
  2. Inside the VM, as root:
       git clone https://github.com/HorneroOS/installer /root/installer
       git -C /root/installer rev-parse HEAD        # record this revision
       /root/installer/scripts/build-iso.sh --work /var/tmp/p33-work --output /var/tmp/p33-out
  3. Copy /var/tmp/p33-out/*.iso and *.iso.manifest.json to the host.
  4. Sign with the established maintainer workflow (installer/scripts/sign-release.sh).
Then re-run with OFFLINE_BUILD_HOST set, or point run.py --iso at the copied artifact.
EOF
  exit 4
fi
[[ "$PORT" =~ ^[0-9]+$ ]] || { echo "OFFLINE_BUILD_PORT must be numeric: $PORT" >&2; exit 2; }

SSH_ARGS=(-p "$PORT")
SCP_ARGS=(-P "$PORT")
if [[ -n "${OFFLINE_BUILD_IDENTITY:-}" ]]; then
  SSH_ARGS+=(-i "$OFFLINE_BUILD_IDENTITY")
  SCP_ARGS+=(-i "$OFFLINE_BUILD_IDENTITY")
fi
remote() { ssh "${SSH_ARGS[@]}" "$OFFLINE_BUILD_HOST" "$@"; }

if [[ "${OFFLINE_BUILD_DRY_RUN:-}" == "1" ]]; then
  echo "ssh ${SSH_ARGS[*]} $OFFLINE_BUILD_HOST <remote command>"
  echo "scp ${SCP_ARGS[*]} $OFFLINE_BUILD_HOST:<remote files> $OUT/"
  exit 0
fi

# Preflight for the 8 GiB build VM (exit 3 with diagnostics on failure).
python3 "$HERE/preflight.py" 8192

mkdir -p "$OUT"
echo "launching build VM via $LAUNCHER"
"$LAUNCHER"
printf 'waiting for build VM ssh'
up=0
for _ in $(seq 1 60); do
  if ssh "${SSH_ARGS[@]}" -o BatchMode=yes -o ConnectTimeout=3 "$OFFLINE_BUILD_HOST" true 2>/dev/null; then
    up=1; break
  fi
  printf '.'; sleep 3
done
[[ "$up" == "1" ]] || { echo " build VM ssh never came up" >&2; exit 4; }
echo " up"

remote 'sudo -n true' || { echo "build VM user needs passwordless sudo for root build" >&2; exit 4; }

remote 'sudo bash -s' <<'EOF'
set -euo pipefail
rm -rf /root/installer /var/tmp/p33-work /var/tmp/p33-out
git clone --quiet https://github.com/HorneroOS/installer /root/installer
echo "installer HEAD: $(git -C /root/installer rev-parse HEAD)"
/root/installer/scripts/build-iso.sh --work /var/tmp/p33-work --output /var/tmp/p33-out
ls -l /var/tmp/p33-out
EOF

scp "${SCP_ARGS[@]}" "$OFFLINE_BUILD_HOST:/var/tmp/p33-out/*.iso" "$OUT/"
scp "${SCP_ARGS[@]}" "$OFFLINE_BUILD_HOST:/var/tmp/p33-out/*.iso.manifest.json" "$OUT/" || true

echo "candidate artifacts in $OUT:"
sha256sum "$OUT"/*.iso | tee "$OUT/candidate.sha256"
echo "Next: sign via installer/scripts/sign-release.sh (maintainer workflow),"
echo "then: python3 $HERE/run.py --iso $OUT/<candidate>.iso --installer-repo <installer checkout>"
