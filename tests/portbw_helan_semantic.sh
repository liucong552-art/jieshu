#!/usr/bin/env bash
# Helan-only real-kernel multi-protocol and fault isolation A/B.
set -Eeuo pipefail
umask 077
[[ $(id -u) == 0 && $(hostname) == helan ]] || { echo "Only root on Helan"; exit 1; }
for c in curl python3 sha256sum unshare nsenter ip nft tc; do command -v "$c" >/dev/null || exit 1; done
BASE=https://raw.githubusercontent.com/liucong552-art/jieshu
BRANCH=opt/portbw-cpu-snapshot-index-20261016
# Immutable commit containing the corrected TCP backpressure checks.
HARNESS_REF=484df0a2ae43667c5e818047eb7d2e3c01faa834
HARNESS_VERSION=20261017-shared-police-pressure-v4
ROOT=$(mktemp -d /tmp/portbw-cpu-XXXXXXXX)
mkdir -p "$ROOT"/{A,B,tools,results}
echo "TEST_ROOT=$ROOT"
echo "HARNESS_VERSION=$HARNESS_VERSION"
echo "HARNESS_REF=$HARNESS_REF"
curl -fsSL --retry 3 "$BASE/main/portbw.py" -o "$ROOT/A/portbw.py"
curl -fsSL --retry 3 "$BASE/$HARNESS_REF/portbw.py" -o "$ROOT/B/portbw.py"
for f in portbw_ab_lab_runner.py portbw_lab_traffic.py portbw_lab_semantics.py portbw_lab_semantic_runner.py verify_portbw_semantic_harness.py; do
  curl -fsSL --retry 3 "$BASE/$HARNESS_REF/tests/$f" -o "$ROOT/tools/$f"
done
printf "%s  %s\n" "69058c8069e78d902c4814e1300c5aa38e2b91340f936cdb9cdc09a14936f359" "$ROOT/A/portbw.py" "52eaa233f831236973dff6b43d8f320659b29226939ee5ba132d2b9cf31eebfb" "$ROOT/B/portbw.py" | sha256sum -c -
# Fail before touching netns if a stale harness was downloaded from a
# cache, or if the wrong TCP overload condition is accidentally restored.
python3 -B "$ROOT/tools/verify_portbw_semantic_harness.py" "$ROOT/tools/portbw_lab_semantics.py"
python3 -m py_compile "$ROOT"/tools/*.py "$ROOT/A/portbw.py" "$ROOT/B/portbw.py"
export PORTBW_LAB_ACK=isolated-netns-only
case "${SEMANTIC_SUITES:-all}" in
  all) SUITES=(aggregate faults lifecycle) ;;
  aggregate) SUITES=(aggregate) ;;
  faults) SUITES=(faults) ;;
  lifecycle) SUITES=(lifecycle) ;;
  *) echo 'Invalid SEMANTIC_SUITES (all|aggregate|faults|lifecycle)' >&2; exit 1 ;;
esac
for suite in "${SUITES[@]}"; do
  for version in A B; do
    echo "===== SEMANTIC SUITE=$suite VERSION=$version ====="
    unshare --net -- python3 -B "$ROOT/tools/portbw_lab_semantic_runner.py" --root "$ROOT" --version "$version" --suite "$suite" --seconds "${SEMANTIC_SECONDS:-18}" 2>&1 | tee "$ROOT/results/${suite}_${version}.log"
  done
done
echo "===== RESULTS ====="
cat "$ROOT"/results/semantics_*.json
echo "RESULTS_DIR=$ROOT/results"
