#!/usr/bin/env bash
# HELAN ONLY: bidirectional fixed-source kernel acceptance; disposable netns.
set -Eeuo pipefail
umask 077
[[ $(id -u) == 0 && $(hostname) == helan ]] || { echo "REFUSED: Helan root only"; exit 1; }
for c in curl sha256sum python3 ip nft tc unshare nsenter; do command -v "$c" >/dev/null || exit 1; done
BASE=https://raw.githubusercontent.com/liucong552-art/jieshu
REF=3c2e41d429ba68b41e86cc66549479c4f49f56dc
EXPECTED=a6f5232edede0fd8c2114589b4de18d7ee2c6745af9aa860682996ad16a262c9
ROOT=$(mktemp -d /tmp/portbw-cpu-XXXXXXXX)
mkdir -p "$ROOT"/{B,tools,results}
echo "BIDIRECTIONAL_TEST_ROOT=$ROOT PINNED_REF=$REF EXPECTED_SHA=$EXPECTED"
curl -fsSL --retry 3 "$BASE/$REF/portbw.py" -o "$ROOT/B/portbw.py"
printf "%s  %s\n" "$EXPECTED" "$ROOT/B/portbw.py" | sha256sum -c -
for f in portbw_ab_lab_runner.py portbw_lab_tcp_goodput.py portbw_lab_egress_tcp_goodput.py portbw_lab_traffic.py portbw_lab_semantics.py portbw_lab_semantic_runner.py portbw_lab_outbound_traffic.py verify_portbw_semantic_harness.py; do
  curl -fsSL --retry 3 "$BASE/$REF/tests/$f" -o "$ROOT/tools/$f"
done
python3 -m py_compile "$ROOT/B/portbw.py" "$ROOT"/tools/*.py
python3 -B "$ROOT/tools/verify_portbw_semantic_harness.py" "$ROOT/tools/portbw_lab_semantics.py"
export PORTBW_LAB_ACK=isolated-netns-only
echo "===== TCP UP BOTH NFT+TC 20/40 ====="
unshare --net -- python3 -B "$ROOT/tools/portbw_lab_tcp_goodput.py" bench --root "$ROOT" --version B --mode both --skip-control --seconds 20 --warmup 4 2>&1 | tee "$ROOT/results/up.log"
echo "===== TCP DOWN BOTH NFT+TC 5/20/40 ====="
unshare --net -- python3 -B "$ROOT/tools/portbw_lab_egress_tcp_goodput.py" bench --root "$ROOT" --mode original --skip-control --seconds 20 --warmup 4 2>&1 | tee "$ROOT/results/down.log"
for suite in aggregate outbound faults lifecycle; do
  echo "===== SEMANTIC $suite ====="
  unshare --net -- python3 -B "$ROOT/tools/portbw_lab_semantic_runner.py" --root "$ROOT" --version B --suite "$suite" --seconds 18 2>&1 | tee "$ROOT/results/sem_${suite}.log"
done
echo "===== FINAL ACCEPTANCE SUMMARY ====="
grep -hE "^(TCP_GOODPUT_SUMMARY|EGRESS_TCP_SUMMARY|SEMANTIC_PASS)=" "$ROOT"/results/*.log
echo "RESULT_DIR=$ROOT/results"

