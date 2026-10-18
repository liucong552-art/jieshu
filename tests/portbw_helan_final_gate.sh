#!/usr/bin/env bash
# Final Helan release gate. Read-only inspection of installed service + disposable netns tests.
# Does not change VLESS/WG services or live portbw policies.
set -Eeuo pipefail
umask 077
[[ $(id -u) -eq 0 && $(hostname) == helan ]] || { echo 'STOP: Helan root only' >&2; exit 1; }
for c in curl sha256sum python3 ip nft tc unshare nsenter systemctl; do command -v "$c" >/dev/null || exit 1; done
EXPECTED=66a79fd8ff9f4b00c43a62ef3530251cd6934301bfc5412d497b47d94a3f70d1
BASE=https://raw.githubusercontent.com/liucong552-art/jieshu
REF=e6ce9b8bfac0bedb0dc433e550156f23ff3fc16e
ROOT=$(mktemp -d /tmp/portbw-final-XXXXXXXX)
mkdir -p "$ROOT"/{B,tools,tests,results}
echo "FINAL_ROOT=$ROOT REF=$REF TARGET_SHA=$EXPECTED"
curl -fsSL --retry 3 "$BASE/$REF/portbw.py" -o "$ROOT/B/portbw.py"
printf '%s  %s\n' "$EXPECTED" "$ROOT/B/portbw.py" | sha256sum -c -
INSTALLED=$(sha256sum /usr/local/lib/portbw/portbw.py | awk '{print $1}')
[[ "$INSTALLED" == "$EXPECTED" ]] || { echo "STOP: installed SHA mismatch: $INSTALLED";exit 1; }
[[ "$(systemctl is-active portbw-watch.service)" == active ]] || { echo 'STOP: Watchdog not active';exit 1; }
[[ "$(systemctl show portbw-watch.service -p Type --value)" == notify ]] || { echo 'STOP: not resident mode';exit 1; }
[[ "$(systemctl is-active portbw-watch.timer 2>/dev/null || true)" != active ]] || { echo 'STOP: legacy timer active';exit 1; }
/usr/local/sbin/portbw audit > "$ROOT/results/host-audit.log"
echo HOST_INSTALL_AUDIT_PASS=YES
for f in portbw_lab_tcp_goodput.py portbw_lab_egress_tcp_goodput.py portbw_lab_traffic.py portbw_lab_semantics.py portbw_lab_semantic_runner.py portbw_lab_outbound_traffic.py portbw_ab_lab_runner.py verify_portbw_semantic_harness.py;do
  curl -fsSL --retry 3 "$BASE/$REF/tests/$f" -o "$ROOT/tools/$f"
done
for f in test_portbw_auto_sustained_window.py test_portbw_cpu_candidate.py;do
  curl -fsSL --retry 3 "$BASE/$REF/tests/$f" -o "$ROOT/tests/$f"
done
python3 -B - "$ROOT/B/portbw.py" <<'PY'
import ast,sys
ast.parse(open(sys.argv[1]).read())
PY
python3 -B "$ROOT/tools/verify_portbw_semantic_harness.py" "$ROOT/tools/portbw_lab_semantics.py"
export PORTBW_LAB_ACK=isolated-netns-only
export PORTBW_LAB_B_SHA="$EXPECTED"
PYTHONPATH="$ROOT/B:$ROOT/tests" python3 -B -m unittest discover -s "$ROOT/tests" -p 'test_portbw_auto_sustained_window.py' -v > "$ROOT/results/auto-unit.log" 2>&1
PYTHONPATH="$ROOT/B:$ROOT/tests" python3 -B -m unittest discover -s "$ROOT/tests" -p 'test_portbw_cpu_candidate.py' -v > "$ROOT/results/core-unit.log" 2>&1
echo AUTO_UNIT_PASS=YES
echo CORE_UNIT_PASS=YES
unshare --net -- python3 -B "$ROOT/tools/portbw_lab_tcp_goodput.py" bench --root "$ROOT" --version B --mode both --skip-control --seconds 20 --warmup 4 > "$ROOT/results/tcp-up.log" 2>&1
unshare --net -- python3 -B "$ROOT/tools/portbw_lab_egress_tcp_goodput.py" bench --root "$ROOT" --mode original --skip-control --seconds 20 --warmup 4 > "$ROOT/results/tcp-down.log" 2>&1
grep '^TCP_GOODPUT_SUMMARY=' "$ROOT/results/tcp-up.log"
grep '^EGRESS_TCP_SUMMARY=' "$ROOT/results/tcp-down.log"
for suite in aggregate outbound faults lifecycle;do
  unshare --net -- python3 -B "$ROOT/tools/portbw_lab_semantic_runner.py" --root "$ROOT" --version B --suite "$suite" --seconds 18 > "$ROOT/results/sem-${suite}.log" 2>&1
  grep '^SEMANTIC_PASS=' "$ROOT/results/sem-${suite}.log"
done
/usr/local/sbin/portbw audit > "$ROOT/results/host-audit-after.log"
cmp "$ROOT/results/host-audit.log" "$ROOT/results/host-audit-after.log" || { echo 'STOP: host audit changed during isolated test';exit 1; }
echo 'HELAN_FINAL_GATE_PASS=YES'
echo "RESULT_DIR=$ROOT/results"
