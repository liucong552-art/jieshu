#!/usr/bin/env bash
# Helan-only. All policy/traffic changes are inside disposable network namespaces.
set -Eeuo pipefail
umask 077
[[ $(id -u) -eq 0 && $(hostname) == helan ]] || { echo "REFUSED: Helan root only"; exit 1; }
for c in curl sha256sum python3 ip nft tc unshare nsenter; do command -v "$c" >/dev/null || exit 1; done
ROOT=$(mktemp -d /tmp/portbw-cpu-XXXXXXXX)
BASE=https://raw.githubusercontent.com/liucong552-art/jieshu
REF=59e440a45d8eceae017016e58cc4625b42040638
mkdir -p "$ROOT"/{A,B,tools,results}
echo "TCP_GOODPUT_ROOT=$ROOT PINNED_REF=$REF"
curl -fsSL --retry 3 "$BASE/main/portbw.py" -o "$ROOT/A/portbw.py"
curl -fsSL --retry 3 "$BASE/$REF/portbw.py" -o "$ROOT/B/portbw.py"
for f in portbw_ab_lab_runner.py portbw_lab_tcp_goodput.py; do
  curl -fsSL --retry 3 "$BASE/$REF/tests/$f" -o "$ROOT/tools/$f"
done
printf '%s  %s\n' \
  69058c8069e78d902c4814e1300c5aa38e2b91340f936cdb9cdc09a14936f359 "$ROOT/A/portbw.py" \
  52eaa233f831236973dff6b43d8f320659b29226939ee5ba132d2b9cf31eebfb "$ROOT/B/portbw.py" | sha256sum -c -
python3 -m py_compile "$ROOT"/tools/*.py
export PORTBW_LAB_ACK=isolated-netns-only
for version in A B; do
  echo "==== TCP GOODPUT version=$version 0ms ===="
  unshare --net -- python3 -B "$ROOT/tools/portbw_lab_tcp_goodput.py" bench --root "$ROOT" --version "$version" --seconds 24 --warmup 4 --delay-ms 0 2>&1 | tee "$ROOT/results/goodput_${version}_0ms.log"
  if [[ "${TCP_DELAY_MS:-0}" != 0 ]]; then
    echo "==== TCP GOODPUT version=$version delay=${TCP_DELAY_MS}ms ===="
    unshare --net -- python3 -B "$ROOT/tools/portbw_lab_tcp_goodput.py" bench --root "$ROOT" --version "$version" --seconds 24 --warmup 4 --delay-ms "$TCP_DELAY_MS" 2>&1 | tee "$ROOT/results/goodput_${version}_delay.log"
  fi
done
echo "RESULT_DIR=$ROOT/results"
