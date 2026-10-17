#!/usr/bin/env bash
# Helan-only guided launcher for the optimized portbw candidate.
# Does not run vless.sh, modify VLESS config, or change the GitHub main branch.
# Explicit menu selection is required before any host install/upgrade/rollback.
set -Eeuo pipefail
umask 077
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

REF=e93be192f008d0fe33dd88543cce2e84a30d6ac7
BASE=https://raw.githubusercontent.com/liucong552-art/jieshu
EXPECTED_SHA=52eaa233f831236973dff6b43d8f320659b29226939ee5ba132d2b9cf31eebfb
SCRIPT_VERSION=portbw-helan-cpu-candidate-20261017
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
echo '  1) 只读预检查（不安装）'
echo '  2) 全新安装优化版（修改 Helan systemd/nft/tc）'
echo '  3) 从已管理的旧版升级（先备份，修改 systemd/nft/tc）'
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
  1) bash "$WORK/portbw-install.sh" check --iface eth0 ;;
  2)
    echo '将安装独立限速组件；不自动创建任何端口策略，不操作 VLESS/WG 服务。'
    bash "$WORK/portbw-install.sh" check --iface eth0
    bash "$WORK/portbw-install.sh" install --iface eth0
    echo '安装完成。使用 portbw report 查看；需要限速时再手动 portbw set <端口> <上行Mbps> <下行Mbps>。'
    ;;
  3)
    echo '将升级已由 portbw 受管理的版本；保留已保存策略，并创建持久备份。'
    bash "$WORK/portbw-install.sh" upgrade --iface eth0
    ;;
  4) bash "$WORK/portbw-install.sh" verify ;;
  5) bash "$WORK/portbw-install.sh" rollback ;;
  6) /usr/local/sbin/portbw report ;;
  *) fail '选项只能为 0 至 6' ;;
esac
echo "测试下载文件保留在：$WORK"
