#!/usr/bin/env bash
# Read-only-to-host Helan automated trigger verification in disposable netns.
set -Eeuo pipefail
umask 077
[[ $(id -u) == 0 && $(hostname) == helan ]] || { echo "REFUSED: HELAN root only"; exit 1; }
for c in curl sha256sum python3 nft tc ip unshare nsenter; do command -v "$c" >/dev/null || exit 1; done
ROOT="$(mktemp -d /tmp/portbw-cpu-XXXXXXXX)"
REF=0d7f41534949a50bc1c64a4361d65931d803e15e
BASE=https://raw.githubusercontent.com/liucong552-art/jieshu
mkdir -p "$ROOT"/{B,tools,tests,results}
echo "AUTO_ACCEPT_ROOT=$ROOT PINNED_REF=$REF"
curl -fsSL --retry 3 "$BASE/$REF/portbw.py" -o "$ROOT/B/portbw.py"
curl -fsSL --retry 3 "$BASE/$REF/portbw.py" -o "$ROOT/portbw.py"
cmp "$ROOT/portbw.py" "$ROOT/B/portbw.py"
for f in test_portbw_auto_sustained_window.py test_portbw_cpu_candidate.py; do
  curl -fsSL --retry 3 "$BASE/$REF/tests/$f" -o "$ROOT/tests/$f"
done
for f in portbw_ab_lab_runner.py portbw_lab_semantic_runner.py portbw_lab_semantics.py portbw_lab_traffic.py portbw_lab_outbound_traffic.py verify_portbw_semantic_harness.py; do
  curl -fsSL --retry 3 "$BASE/$REF/tests/$f" -o "$ROOT/tools/$f"
done
python3 -m py_compile "$ROOT/portbw.py" "$ROOT"/tests/*.py "$ROOT"/tools/*.py
export PORTBW_LAB_B_SHA="$(sha256sum "$ROOT/B/portbw.py" | cut -d ' ' -f1)"
echo "AUTO_SOURCE_SHA256=$PORTBW_LAB_B_SHA"
echo "===== AUTO WINDOW UNIT REGRESSIONS ====="
python3 -m unittest discover -s "$ROOT/tests" -p 'test_portbw_auto_sustained_window.py' -v 2>&1 | tee "$ROOT/results/window.log"
echo "AUTO_WINDOW_UNIT_PASS=YES"
echo "===== CORE CPU+BURST UNIT REGRESSIONS ====="
python3 -m unittest discover -s "$ROOT/tests" -p 'test_portbw_cpu_candidate.py' -v 2>&1 | tee "$ROOT/results/core.log"
echo "CORE_UNIT_PASS=YES"
python3 "$ROOT/tools/verify_portbw_semantic_harness.py" "$ROOT/tools/portbw_lab_semantics.py"
export PORTBW_LAB_ACK=isolated-netns-only
for suite in aggregate outbound faults lifecycle; do
  echo "===== HELAN KERNEL AUTO FIX $suite ====="
  unshare --net -- python3 -B "$ROOT/tools/portbw_lab_semantic_runner.py" --root "$ROOT" --version B --suite "$suite" --seconds 18 2>&1 | tee "$ROOT/results/$suite.log"
done
echo "===== PASS SUMMARIES ====="
grep -h '^SEMANTIC_PASS=' "$ROOT"/results/*.log
echo "AUTO_ACCEPT_PASS=YES"
echo "RESULT_DIR=$ROOT/results"
