#!/usr/bin/env bash
# Helan-only: fixed-source semantic acceptance in disposable netns.
set -Eeuo pipefail
umask 077
[[ $(id -u) == 0 && $(hostname) == helan ]] || { echo "REFUSED: Helan root only"; exit 1; }
for c in curl python3 sha256sum unshare nsenter ip nft tc; do command -v "$c" >/dev/null || exit 1; done
BASE=https://raw.githubusercontent.com/liucong552-art/jieshu
REF=cb7d8ad7b88e3367af9faedc9587ad07f08e1ec8
ROOT=$(mktemp -d /tmp/portbw-cpu-XXXXXXXX)
mkdir -p "$ROOT"/{A,B,tools,results}
echo "SEMANTIC_FIX_ROOT=$ROOT SOURCE_REF=$REF"
curl -fsSL --retry 3 "$BASE/$REF/portbw.py" -o "$ROOT/B/portbw.py"
for f in portbw_ab_lab_runner.py portbw_lab_traffic.py portbw_lab_semantics.py portbw_lab_semantic_runner.py portbw_lab_outbound_traffic.py verify_portbw_semantic_harness.py; do
  curl -fsSL --retry 3 "$BASE/$REF/tests/$f" -o "$ROOT/tools/$f"
done
printf "%s  %s\n" f0ebe551e8c0345c045a558b39a8b13523b2be8195255c67db13eec3eff5dc1a "$ROOT/B/portbw.py" | sha256sum -c -
python3 -B "$ROOT/tools/verify_portbw_semantic_harness.py" "$ROOT/tools/portbw_lab_semantics.py"
python3 -m py_compile "$ROOT"/tools/*.py "$ROOT/B/portbw.py"
export PORTBW_LAB_ACK=isolated-netns-only
for suite in aggregate outbound faults lifecycle; do
  echo "==== BURST FIX SUITE=$suite VERSION=B ===="
  unshare --net -- python3 -B "$ROOT/tools/portbw_lab_semantic_runner.py" --root "$ROOT" --version B --suite "$suite" --seconds 18 2>&1 | tee "$ROOT/results/fix_${suite}.log"
done
echo "==== SEMANTIC RESULTS ===="
cat "$ROOT"/results/semantics_*.json
echo "RESULT_DIR=$ROOT/results"
