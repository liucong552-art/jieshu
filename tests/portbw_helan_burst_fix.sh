#!/usr/bin/env bash
# Helan-only. Disposable network namespace. No host nft/tc rule edits.
set -Eeuo pipefail
umask 077
[[ $(id -u) == 0 && $(hostname) == helan ]] || { echo "REFUSED: Helan root only"; exit 1; }
for c in curl sha256sum python3 ip nft tc unshare nsenter; do command -v "$c" >/dev/null; done
ROOT=$(mktemp -d /tmp/portbw-cpu-XXXXXXXX)
BASE=https://raw.githubusercontent.com/liucong552-art/jieshu
REF=48ac700dd734b7492d367342fb343eeaa99fc183
mkdir -p "$ROOT"/{A,B,tools,results}
echo "FIX_BURST_LAB_ROOT=$ROOT SOURCE_REF=$REF"
curl -fsSL --retry 3 "$BASE/$REF/portbw.py" -o "$ROOT/B/portbw.py"
for f in portbw_ab_lab_runner.py portbw_lab_tcp_goodput.py; do curl -fsSL --retry 3 "$BASE/$REF/tests/$f" -o "$ROOT/tools/$f"; done
export PORTBW_LAB_B_SHA
PORTBW_LAB_B_SHA=$(sha256sum "$ROOT/B/portbw.py" | awk '{print $1}')
echo "FIX_CANDIDATE_SHA256=$PORTBW_LAB_B_SHA"
python3 -m py_compile "$ROOT"/tools/*.py "$ROOT/B/portbw.py"
export PORTBW_LAB_ACK=isolated-netns-only
for mode in both nft_only; do
  echo "===== FIX CANDIDATE TCP mode=$mode ====="
  unshare --net -- python3 -B "$ROOT/tools/portbw_lab_tcp_goodput.py" bench --root "$ROOT" --version B --mode "$mode" --seconds 24 --warmup 4 2>&1 | tee "$ROOT/results/fix_${mode}.log"
done
echo "RESULT_DIR=$ROOT/results"
