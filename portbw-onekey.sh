#!/usr/bin/env bash
# Helan-only guided launcher for the optimized portbw candidate.
# Does not run vless.sh, modify VLESS config, or change the GitHub main branch.
# Explicit menu selection is required before any host install/upgrade/rollback.
set -Eeuo pipefail
umask 077
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

REF=fe6930a9071f314e31b854c1a4515f1f5d983bff
BASE=https://raw.githubusercontent.com/liucong552-art/jieshu
EXPECTED_SHA=66a79fd8ff9f4b00c43a62ef3530251cd6934301bfc5412d497b47d94a3f70d1
SCRIPT_VERSION=portbw-helan-dual-auto-snapshot-aware-20261018
fail(){ printf '拒绝继续：%s\n' "$*" >&2; exit 1; }

[[ $(id -u) -eq 0 ]] || fail '请使用 root'
[[ "$(hostname)" == helan ]] || fail '此测试入口仅允许在 Helan 测试机运行，不允许部署到生产服务器'
[[ -d /run/systemd/system ]] || fail '系统必须使用 systemd'
for c in curl sha256sum bash python3 nft tc ip ss systemctl;do
  command -v "$c" >/dev/null 2>&1 || fail "缺少依赖 $c；请先安装 nftables、iproute2、python3 等必要软件"
done
[[ "$(ip -o link show dev eth0 2>/dev/null)" != "" ]] || fail 'Helan 无 eth0，拒绝猜测网卡'

WORK="$(mktemp -d /tmp/portbw-release-candidate-XXXXXXXX)"
echo "SCRIPT_VERSION=$SCRIPT_VERSION"
echo "IMMUTABLE_REF=$REF"
echo "DOWNLOAD_DIR=$WORK"
curl -fsSL --retry 3 "$BASE/$REF/portbw.py" -o "$WORK/portbw.py"
curl -fsSL --retry 3 "$BASE/$REF/portbw-install.sh" -o "$WORK/portbw-install.sh"
printf '%s  %s\n' "$EXPECTED_SHA" "$WORK/portbw.py" | sha256sum -c - ||
  fail '候选 Python SHA256 不匹配'
grep -Fxq "EXPECTED_SHA='$EXPECTED_SHA'" "$WORK/portbw-install.sh" ||
  fail '安装器候选版本校验不匹配'
bash -n "$WORK/portbw-install.sh" || fail '安装器语法不正确'
python3 -B - "$WORK/portbw.py" <<'PY'
import ast,sys
with open(sys.argv[1],encoding="utf8") as f: ast.parse(f.read())
PY
echo '候选版本源代码和安装器初步校验：通过'
echo
echo '请选择要在 Helan 执行的操作：'
echo '  1) 只读预检查：有管理记录则升级预检；快照干净则新安装预检'
echo '  2) 快照恢复后全新安装（仅干净环境；修改 Helan systemd/nft/tc）'
echo '  3) 从 f0ebe Helan 当前版升级（备份，保留端口策略）'
echo '  4) 验证当前安装及 Watchdog'
echo '  5) 回滚此安装器管理的优化版'
echo '  6) 查看当前限速报告（只读）'
echo '  0) 退出'
echo
if (( $# > 0 ));then
  choice="$1"
else
  [[ -t 0 ]] || fail '非交互模式需指定 1、2、3、4、5、6 或 0'
  read -r -p '输入选项 [0-6]：' choice
fi
case "$choice" in
  0) echo '已退出；没有改变限速配置。' ;;
  1)
    if [[ -e /var/lib/portbw-resident-release/current.env ||
          -L /var/lib/portbw-resident-release/current.env ]];then
      echo '检测到管理记录：执行只读升级预检'
      bash "$WORK/portbw-install.sh" preflight-upgrade --iface eth0
    else
      echo '未检测到管理记录：执行只读全新安装预检（不自动覆盖任何旧组件）'
      bash "$WORK/portbw-install.sh" check --iface eth0
    fi
    ;;
  2)
    echo '将为 Helan 干净快照首次安装限速组件；不创建端口策略、不修改 VLESS/WireGuard'
    # install_fresh runs clean_check again under the deployment lock.
    bash "$WORK/portbw-install.sh" check --iface eth0
    bash "$WORK/portbw-install.sh" install --iface eth0
    ;;
  3)
    echo '将升级 Helan 已管理的 f0ebe 版；保留策略并持久备份。'
    bash "$WORK/portbw-install.sh" preflight-upgrade --iface eth0
    bash "$WORK/portbw-install.sh" upgrade --iface eth0
    ;;
  4) bash "$WORK/portbw-install.sh" verify ;;
  5) bash "$WORK/portbw-install.sh" rollback ;;
  6) /usr/local/sbin/portbw report ;;
  *) fail '选项只能为 0 至 6' ;;
esac
echo "测试下载文件保留在：$WORK"
