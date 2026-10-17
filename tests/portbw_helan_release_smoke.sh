#!/usr/bin/env bash
# HELAN ONLY — modifies HOST systemd, nft and tc (unlike CPU network-namespace tests).
# On success: original main release remains installed; temp port is removed.
# Full pre-test restoration requires user's Helan VPS snapshot.
set -Eeuo pipefail
umask 077
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

MAIN_REF=41723a28129682421e13a62112111a1967f28f89
CANDIDATE_REF=1b1386b93792ed912b2703600cd3bab57be47c0b
MAIN_SHA=69058c8069e78d902c4814e1300c5aa38e2b91340f936cdb9cdc09a14936f359
CANDIDATE_SHA=52eaa233f831236973dff6b43d8f320659b29226939ee5ba132d2b9cf31eebfb
BASE=https://raw.githubusercontent.com/liucong552-art/jieshu
PORT=43099
WORK="$(mktemp -d /tmp/portbw-release-smoke-XXXXXXXX)"
mkdir -p "$WORK"/{A,B,logs}
exec > >(tee -a "$WORK/logs/steps.log") 2>&1

STAGE=preflight
report_exit() {
  local rc=$?
  trap - EXIT
  echo "EXIT_CODE=$rc STAGE=$STAGE REPORT=$WORK"
  if ((rc!=0)); then
    echo 'ERROR: Host managed installation state may have changed.'
    echo 'Review release backup/snapshot before further work.'
    echo 'No automatic flush of nft tables or root qdisc.'
  fi
}
trap report_exit EXIT
die(){ echo "REFUSED: $*" >&2; exit 1; }

[[ "$(hostname)" == helan ]] || die 'Helan-only smoke test'
[[ $(id -u) -eq 0 ]] || die 'root required'
[[ "${PORTBW_HELAN_RELEASE_ACK:-}" == "ALLOW_HOST_INSTALL_AND_ROLLBACK" ]] ||
  die 'explicit Helan host-install acknowledgment missing'
[[ -d /run/systemd/system ]] || die 'systemd host required'
for c in curl sha256sum systemctl ip nft tc ss python3 bash;do
  command -v "$c" >/dev/null || die "missing $c"
done
[[ ! -e /usr/local/lib/portbw/portbw.py && ! -L /usr/local/lib/portbw/portbw.py ]] ||
  die 'managed program exists; refusing to overwrite'
[[ ! -e /var/lib/portbw-resident-release/current.env ]] ||
  die 'managed release already exists'
[[ ! -e /var/lib/portbw/ports/$PORT.json ]] ||
  die 'test policy file already exists'
if ss -H -ltnu | grep -Eq ":$PORT([[:space:]]|$)";then
  die "host already has listener on test port $PORT"
fi

echo "RESULTS_DIR=$WORK"
curl -fsSL --retry 3 "$BASE/$MAIN_REF/portbw.py" -o "$WORK/A/portbw.py"
curl -fsSL --retry 3 "$BASE/$MAIN_REF/portbw-install.sh" -o "$WORK/A/portbw-install.sh"
curl -fsSL --retry 3 "$BASE/$CANDIDATE_REF/portbw.py" -o "$WORK/B/portbw.py"
curl -fsSL --retry 3 "$BASE/$CANDIDATE_REF/portbw-install.sh" -o "$WORK/B/portbw-install.sh"
printf '%s  %s\n' "$MAIN_SHA" "$WORK/A/portbw.py" \
                      "$CANDIDATE_SHA" "$WORK/B/portbw.py" | sha256sum -c -
bash -n "$WORK/A/portbw-install.sh"
bash -n "$WORK/B/portbw-install.sh"
grep -Fxq "EXPECTED_SHA='$MAIN_SHA'" "$WORK/A/portbw-install.sh" ||
  die 'main installer expected SHA mismatch'
grep -Fxq "EXPECTED_SHA='$CANDIDATE_SHA'" "$WORK/B/portbw-install.sh" ||
  die 'candidate installer expected SHA mismatch'

STAGE=main-clean-check
bash "$WORK/A/portbw-install.sh" check --iface eth0

STAGE=install-main
bash "$WORK/A/portbw-install.sh" install --iface eth0
STAGE=verify-main
bash "$WORK/A/portbw-install.sh" verify
test "$(sha256sum /usr/local/lib/portbw/portbw.py | awk '{print $1}')" = "$MAIN_SHA"
systemctl show portbw-watch.service -p MainPID -p CPUAccounting -p WatchdogUSec -p ActiveState |
  tee "$WORK/logs/main-systemd.txt"

STAGE=create-static-test-policy
/usr/local/sbin/portbw set "$PORT" 1 1
/usr/local/sbin/portbw audit
/usr/local/sbin/portbw show "$PORT"
python3 - "$PORT" <<'PY'
import json,sys
port=int(sys.argv[1])
with open(f'/var/lib/portbw/ports/{port}.json',encoding='utf8') as f: r=json.load(f)
assert r['up']==125000 and r['down']==125000,r
PY

STAGE=upgrade-to-candidate
bash "$WORK/B/portbw-install.sh" upgrade --iface eth0
STAGE=verify-candidate
bash "$WORK/B/portbw-install.sh" verify
test "$(sha256sum /usr/local/lib/portbw/portbw.py | awk '{print $1}')" = "$CANDIDATE_SHA"
test "$(sed -n 's/^source_sha=//p' /var/lib/portbw-resident-release/current.env)" = "$CANDIDATE_SHA"
/usr/local/sbin/portbw audit
/usr/local/sbin/portbw show "$PORT"

STAGE=restart-candidate-watchdog
systemctl restart portbw-watch.service
bash "$WORK/B/portbw-install.sh" verify
systemctl show portbw-watch.service -p MainPID -p CPUUsageNSec -p CPUAccounting \
  -p WatchdogUSec -p NRestarts -p ActiveState | tee "$WORK/logs/candidate-systemd.txt"

STAGE=rollback-to-main
bash "$WORK/B/portbw-install.sh" rollback
STAGE=verify-rollback
bash "$WORK/A/portbw-install.sh" verify
test "$(sha256sum /usr/local/lib/portbw/portbw.py | awk '{print $1}')" = "$MAIN_SHA"
test "$(sed -n 's/^source_sha=//p' /var/lib/portbw-resident-release/current.env)" = "$MAIN_SHA"
/usr/local/sbin/portbw audit
/usr/local/sbin/portbw show "$PORT"
python3 - "$PORT" <<'PY'
import json,sys
port=int(sys.argv[1])
with open(f'/var/lib/portbw/ports/{port}.json',encoding='utf8') as f:r=json.load(f)
assert r['up']==125000 and r['down']==125000,r
PY

STAGE=delete-temporary-policy
/usr/local/sbin/portbw del "$PORT"
/usr/local/sbin/portbw audit
bash "$WORK/A/portbw-install.sh" verify

STAGE=complete
echo 'PASS: main install, policy, candidate upgrade, watchdog restart, rollback, preserved policy, test policy deletion.'
echo "RESULTS_DIR=$WORK"
echo 'FINAL_HOST_STATE: original managed main release remains installed; base nft/tc and service remain.'
echo 'Use the saved Helan VPS snapshot for exact pre-test restoration; do not flush unrelated nft/tc.'
