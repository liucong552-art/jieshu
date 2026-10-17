#!/usr/bin/env bash
# Standalone Helan-only bootstrap. Invoked as bash /tmp/portbw-helan-ab.sh
set -Eeuo pipefail
umask 077
BASE=https://raw.githubusercontent.com/liucong552-art/jieshu
BRANCH=opt/portbw-cpu-snapshot-index-20261016
A_SHA=69058c8069e78d902c4814e1300c5aa38e2b91340f936cdb9cdc09a14936f359
B_SHA=52eaa233f831236973dff6b43d8f320659b29226939ee5ba132d2b9cf31eebfb
[[ $(id -u) == 0 && $(hostname) == helan ]] || { echo "Only root on Helan"; exit 1; }
for c in curl python3 sha256sum unshare nsenter ip nft tc; do command -v "$c" >/dev/null || exit 1; done
ROOT=$(mktemp -d /tmp/portbw-cpu-XXXXXXXX)
mkdir -p "$ROOT"/{A,B/tests,tools,results}
echo "TEST_ROOT=$ROOT"
curl -fsSL --retry 3 "$BASE/main/portbw.py" -o "$ROOT/A/portbw.py"
curl -fsSL --retry 3 "$BASE/$BRANCH/portbw.py" -o "$ROOT/B/portbw.py"
for f in portbw_cpu_probe.py portbw_ab_lab_runner.py portbw_lab_traffic.py; do
  curl -fsSL --retry 3 "$BASE/$BRANCH/tests/$f" -o "$ROOT/tools/$f"
done
curl -fsSL --retry 3 "$BASE/$BRANCH/tests/test_portbw_cpu_candidate.py" -o "$ROOT/B/tests/test_portbw_cpu_candidate.py"
echo "$A_SHA  $ROOT/A/portbw.py" | sha256sum -c -
echo "$B_SHA  $ROOT/B/portbw.py" | sha256sum -c -
python3 -B -m py_compile "$ROOT/A/portbw.py" "$ROOT/B/portbw.py" "$ROOT"/tools/*.py
(cd "$ROOT/B" && python3 -B -m unittest discover -s tests -p "test_portbw_cpu_candidate.py" -v)
export PORTBW_LAB_ACK=isolated-netns-only
echo "===== ORIGINAL MAIN BASELINE FIRST ====="
EXTRA=()
if [[ "${TEST_AUTO:-0}" == 1 ]]; then EXTRA+=(--auto); fi
echo "Phase A1: untouched main, rule counts and real command CPU."
unshare --net -- python3 -B "$ROOT/tools/portbw_ab_lab_runner.py" --root "$ROOT" --seconds "${TEST_SECONDS:-30}" --sizes "${TEST_SIZES:-1,10}" --traffic "${TEST_TRAFFIC:-idle}" --proto "${TEST_PROTO:-udp}" --family "${TEST_FAMILY:-ipv4}" --baseline-only --profile-baseline "${EXTRA[@]}" 2>&1 | tee "$ROOT/results/baseline.log"
cp "$ROOT/results/summary.json" "$ROOT/results/baseline-summary.json"
echo "===== BASELINE CPU RESULTS ====="
cat "$ROOT/results/baseline-summary.json"
echo "Python hot paths reports: $ROOT/results/"*"_A_hotspots.pstats.txt"
if [[ "${RUN_AB_AFTER_BASELINE:-0}" == 1 ]]; then
  echo "Phase A2: same environment sequential A/B."
  unshare --net -- python3 -B "$ROOT/tools/portbw_ab_lab_runner.py" --root "$ROOT" --seconds "${TEST_SECONDS:-30}" --sizes "${TEST_SIZES:-1,10}" --traffic "${TEST_TRAFFIC:-idle}" --proto "${TEST_PROTO:-udp}" --family "${TEST_FAMILY:-ipv4}" "${EXTRA[@]}" 2>&1 | tee "$ROOT/results/ab.log"
  cp "$ROOT/results/summary.json" "$ROOT/results/ab-summary.json"
fi
echo "===== SUMMARY ====="
cat "$ROOT/results/summary.json"
echo "RESULTS=$ROOT/results"
