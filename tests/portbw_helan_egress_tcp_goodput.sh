#!/usr/bin/env bash
# Helan-only TCP download goodput, disposable network namespaces only.
set -Eeuo pipefail
umask 077
[[ $(id -u) == 0 && $(hostname) == helan ]] || { echo "REFUSED: HELAN root only"; exit 1; }
for c in curl python3 ip nft tc unshare nsenter sha256sum; do command -v "$c" >/dev/null; done
ROOT=$(mktemp -d /tmp/portbw-cpu-XXXXXXXX)
BASE=https://raw.githubusercontent.com/liucong552-art/jieshu
REF=2179f05b3e6755bb8634bde7751f7a026fe5525e
mkdir -p "$ROOT"/{B,tools,results}
echo "EGRESS_TEST_ROOT=$ROOT PINNED_REF=$REF"
curl -fsSL --retry 3 "$BASE/$REF/portbw.py" -o "$ROOT/B/portbw.py"
for f in portbw_ab_lab_runner.py portbw_lab_egress_tcp_goodput.py; do
  curl -fsSL --retry 3 "$BASE/$REF/tests/$f" -o "$ROOT/tools/$f"
done
printf "%s  %s\n" f0ebe551e8c0345c045a558b39a8b13523b2be8195255c67db13eec3eff5dc1a "$ROOT/B/portbw.py" | sha256sum -c -
python3 -m py_compile "$ROOT"/tools/*.py "$ROOT/B/portbw.py"
export PORTBW_LAB_ACK=isolated-netns-only
for mode in half_second one_meg; do
  echo "==== EGRESS TCP mode=$mode ===="
  unshare --net -- python3 -B "$ROOT/tools/portbw_lab_egress_tcp_goodput.py" bench --root "$ROOT" --mode "$mode" --seconds 20 --warmup 4 --skip-control 2>&1 | tee "$ROOT/results/egress_${mode}.log"
done
echo "RESULT_DIR=$ROOT/results"
