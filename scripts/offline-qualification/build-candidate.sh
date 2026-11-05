#!/usr/bin/env bash
# Build ONE Preview 33 candidate ISO inside the disposable build VM.
#
# Runs on the HOST (maintainer-executed, Muse closed). It preflights
# for the build VM's 8 GiB, launches the existing build VM, clones the
# installer at current origin/main INSIDE the VM (clean checkout, as
# build-iso.sh requires), builds as root via the installer's own
# scripts/build-iso.sh, and copies the ISO + sidecar manifest out.
# Provenance (installer HEAD, product revision, hashes) is printed and
# saved next to the artifact; signing stays on the established
# maintainer workflow (scripts/sign-release.sh in installer) and is
# NOT performed here.
#
# Required environment:
#   OFFLINE_BUILD_SSH   ssh target for the build VM, e.g.
#                       "builder@127.0.0.1 -p 2224" (key-based, sudo root)
# Optional:
#   BUILD_VM_LAUNCHER   default ~/.local/share/hornero/run-build-vm.sh
#   CANDIDATE_OUT       default ~/hornero-p33-offline/candidate
set -euo pipefail

HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
LAUNCHER=${BUILD_VM_LAUNCHER:-$HOME/.local/share/hornero/run-build-vm.sh}
OUT=${CANDIDATE_OUT:-$HOME/hornero-p33-offline/candidate}

if [[ -z "${OFFLINE_BUILD_SSH:-}" ]]; then
  cat >&2 <<'EOF'
OFFLINE_BUILD_SSH is not set. Manual build path:
  1. ~/.local/share/hornero/run-build-vm.sh        # boots the 8 GiB build VM (SSH :2224)
  2. Inside the VM, as root:
       git clone https://github.com/HorneroOS/installer /root/installer
       git -C /root/installer rev-parse HEAD        # record this revision
       /root/installer/scripts/build-iso.sh --work /var/tmp/p33-work --output /var/tmp/p33-out
  3. Copy /var/tmp/p33-out/*.iso and *.iso.manifest.json to the host.
  4. Sign with the established maintainer workflow (installer/scripts/sign-release.sh).
Then re-run with OFFLINE_BUILD_SSH set, or point run.py --iso at the copied artifact.
EOF
  exit 4
fi

# Preflight for the 8 GiB build VM (exit 3 with diagnostics on failure).
python3 "$HERE/preflight.py" 8192

mkdir -p "$OUT"
echo "launching build VM via $LAUNCHER"
"$LAUNCHER"
# shellcheck disable=SC2086  # OFFLINE_BUILD_SSH is a word-split ssh target by design
printf 'waiting for build VM ssh'
for _ in $(seq 1 60); do
  if ssh -o BatchMode=yes -o ConnectTimeout=3 $OFFLINE_BUILD_SSH true 2>/dev/null; then break; fi
  printf '.'; sleep 3
done
echo " up"

# shellcheck disable=SC2086
ssh $OFFLINE_BUILD_SSH 'sudo -n true' || { echo "build VM user needs passwordless sudo for root build" >&2; exit 4; }

# shellcheck disable=SC2086
ssh $OFFLINE_BUILD_SSH 'sudo bash -s' <<'EOF'
set -euo pipefail
rm -rf /root/installer /var/tmp/p33-work /var/tmp/p33-out
git clone --quiet https://github.com/HorneroOS/installer /root/installer
echo "installer HEAD: $(git -C /root/installer rev-parse HEAD)"
/root/installer/scripts/build-iso.sh --work /var/tmp/p33-work --output /var/tmp/p33-out
ls -l /var/tmp/p33-out
EOF

# shellcheck disable=SC2086
scp $OFFLINE_BUILD_SSH:'/var/tmp/p33-out/*.iso /var/tmp/p33-out/*.iso.manifest.json' "$OUT/" || \
  scp $OFFLINE_BUILD_SSH:'/var/tmp/p33-out/*.iso' "$OUT/"

echo "candidate artifacts in $OUT:"
sha256sum "$OUT"/*.iso | tee "$OUT/candidate.sha256"
echo "Next: sign via installer/scripts/sign-release.sh (maintainer workflow),"
echo "then: python3 $HERE/run.py --iso $OUT/<candidate>.iso"
