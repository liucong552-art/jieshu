#!/usr/bin/env bash
# Standalone Helan-only bootstrap. Invoked as bash /tmp/portbw-helan-ab.sh
set -Eeuo pipefail
umask 077
BASE=https://raw.githubusercontent.com/liucong552-art/jieshu
BRANCH=opt/portbw-cpu-snapshot-index-20261016
A_SHA=69058c8069e78d902c4814e1300c5aa38e2b91340f936cdb9cdc09a14936f359
B_SHA=601423e191fd809cda1bd7cbbab285096178b938a131ce4d9fe99fb83b08495f
[[ $(id -u) == 0 && $(hostname) == helan ]] || { echo "Only root on Helan"; exit 1; }
for c in curl python3 sha256sum unshare nsenter ip nft tc; do command -v "$c" >/dev/null || exit 1; done
ROOT=$(mktemp -d /tmp/portbw-cpu-XXXXXXXX)
mkdir -p "$ROOT"/{A,B,tools,results}
echo "TEST_ROOT=$ROOT"
curl -fsSL --retry 3 "$BASE/main/portbw.py" -o "$ROOT/A/portbw.py"
curl -fsSL --retry 3 "$BASE/$BRANCH/portbw.py" -o "$ROOT/B/portbw.py"
for f in portbw_cpu_probe.py portbw_ab_lab_runner.py portbw_lab_traffic.py; do
  curl -fsSL --retry 3 "$BASE/$BRANCH/tests/$f" -o "$ROOT/tools/$f"
done
curl -fsSL --retry 3 "$BASE/$BRANCH/tests/test_portbw_cpu_candidate.py" -o "$ROOT/B/test_portbw_cpu_candidate.py"
echo "$A_SHA  $ROOT/A/portbw.py" | sha256sum -c -
echo "$B_SHA  $ROOT/B/portbw.py" | sha256sum -c -
python3 -B -m py_compile "$ROOT/A/portbw.py" "$ROOT/B/portbw.py" "$ROOT"/tools/*.py
(cd "$ROOT/B" && python3 -B -m unittest -v test_portbw_cpu_candidate)
export PORTBW_LAB_ACK=isolated-netns-only
echo "===== A/B namespace lab ====="
EXTRA=()
if [[ "${TEST_AUTO:-0}" == 1 ]]; then EXTRA+=(--auto); fi
unshare --net -- python3 -B "$ROOT/tools/portbw_ab_lab_runner.py" --root "$ROOT" --seconds "${TEST_SECONDS:-30}" --sizes "${TEST_SIZES:-1,10}" --traffic "${TEST_TRAFFIC:-idle}" "${EXTRA[@]}" 2>&1 | tee "$ROOT/results/lab.log"
echo "===== SUMMARY ====="
cat "$ROOT/results/summary.json"
echo "RESULTS=$ROOT/results"
