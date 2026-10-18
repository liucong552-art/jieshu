#!/usr/bin/env bash
# Generic candidate deployment interface. Explicit words only, no numeric menu.
# check is read-only; install/upgrade/rollback explicitly mutate this host.
set -Eeuo pipefail
umask 077
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
BASE=https://raw.githubusercontent.com/liucong552-art/jieshu
REF=3e416ac0fb25c6a783198f26be1392e937d04215
EXPECTED_SHA=66a79fd8ff9f4b00c43a62ef3530251cd6934301bfc5412d497b47d94a3f70d1
OLD_MAIN_SHA=69058c8069e78d902c4814e1300c5aa38e2b91340f936cdb9cdc09a14936f359
fail(){ echo "STOP: $*" >&2; exit 1; }
usage(){
  echo '用法: bash portbw-generic.sh check|install|upgrade|verify|rollback [--iface NAME]'
  echo 'check 自动区分：已管理安装 -> 升级只读预检；干净系统 -> 新装只读预检'
  echo '执行 upgrade 前必须先确认旧版 SHA 与管理记录一致，且已保存 VPS 快照。'
}
[[ ${EUID:-$(id -u)} -eq 0 ]] || fail 'root required'
(( $#>=1 )) || { usage; exit 2; }
action="$1"; shift
case "$action" in check|install|upgrade|verify|rollback) ;; *) usage;exit 2;; esac
if [[ "$action" == verify || "$action" == rollback ]];then
  (( $# == 0 )) || fail 'verify/rollback do not take interface options'
fi
for tool in curl sha256sum bash python3 ip nft tc systemctl;do command -v "$tool" >/dev/null || fail "missing $tool";done
work=$(mktemp -d /tmp/portbw-generic-candidate-XXXXXXXX)
echo "GENERIC_CANDIDATE_REF=$REF"
echo "TEMP_DIR=$work"
curl -fsSL --retry 3 "$BASE/$REF/portbw.py" -o "$work/portbw.py"
curl -fsSL --retry 3 "$BASE/$REF/portbw-install.sh" -o "$work/portbw-install.sh"
printf '%s  %s\n' "$EXPECTED_SHA" "$work/portbw.py" | sha256sum -c -
grep -Fxq "EXPECTED_SHA='$EXPECTED_SHA'" "$work/portbw-install.sh" || fail 'installer target source hash mismatch'
bash -n "$work/portbw-install.sh"
python3 -B -m py_compile "$work/portbw.py"
case "$action" in
  check)
    if [[ -e /var/lib/portbw-resident-release/current.env ||
          -L /var/lib/portbw-resident-release/current.env ]];then
      echo "MODE=managed_upgrade_preflight"
      bash "$work/portbw-install.sh" preflight-upgrade "$@"
    elif [[ -e /usr/local/lib/portbw/portbw.py ||
            -L /usr/local/lib/portbw/portbw.py ||
            -e /usr/local/sbin/portbw ||
            -L /usr/local/sbin/portbw ||
            -e /etc/portbw/config.json ||
            -L /etc/portbw/config.json ]] ||
         { [[ -d /var/lib/portbw/ports ]] &&
           find /var/lib/portbw/ports -maxdepth 1 -type f -name '*.json' -print -quit | grep -q .; };then
      echo 'MODE=legacy_unmanaged_existing_install'
      echo 'STOP: existing portbw state without managed release marker; no installation/upgrade allowed.'
      echo 'Preserve installed source, systemd unit/timer and all port records.'
      exit 4
    else
      echo "MODE=clean_install_preflight"
      bash "$work/portbw-install.sh" check "$@"
    fi
    ;;
  install)
    bash "$work/portbw-install.sh" check "$@"
    bash "$work/portbw-install.sh" install "$@"
    ;;
  upgrade)
    bash "$work/portbw-install.sh" preflight-upgrade "$@"
    bash "$work/portbw-install.sh" upgrade "$@"
    ;;
  verify) bash "$work/portbw-install.sh" verify ;;
  rollback) bash "$work/portbw-install.sh" rollback ;;
esac
