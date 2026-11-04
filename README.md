# VLESS Reality / WG-NAT / SOCKS5

命令使用 **root + Bash**，示例端口换成实际端口。长命令和低频操作点击展开，所有内容都在本 README 内。

[查询](#queries) · [新建节点](#create) · [修改与重置](#modify) · [排查](#trouble-guide) · [封禁与删除](#remove) · [安装与更新](#install)

<a id="queries"></a>

## 一、查询与检查

| 查询什么 | 命令 / 直接跳转 |
|---|---|
| VLESS 节点、到期、临时节点配额及 IP 占用 | `vless_audit.sh` |
| 指定端口的节点链接 | [按端口查链接](#node-link) |
| 下次流量重置日期与倒计时 | [查重置时间](#quota-reset-time) |
| VLESS 今天 / 某端口每日流量 | `vless_traffic` / `vless_traffic 40000` |
| 全部端口限速 | `portbw report` |
| 自动降速与恢复日志 | [查限速日志](#speed-logs) |
| 当前来源 IP / TCP 连接 | [查来源 IP](#active-ips) |
| 共享嫌疑、访问目标、异常端口 | `PORT=40000 DAYS=7 vless-abuse`（[首次安装](#abuse-install)） |
| 全部受管理黑名单 | [查黑名单](#blacklist-report) |
| SOCKS5 账号、到期、剩余配额及 IP 占用 | `socks5 list` |
| SOCKS5 今天 / 某端口每日流量 | `socks5-traffic` / `socks5-traffic 41004`（[说明](#socks5-daily)） |
| SOCKS5 连接链接 | `socks5 link 41004` |
| SOCKS5 访问域名与连接错误 | [SOCKS5 审计](#socks5-access) |
| NAT 出口机运行状态 | 在 NAT 出口机执行 `bash /root/nat.sh status` |
| 导出有效临时节点订阅（生成文件） | [导出订阅](#subscription) |
| 配额重置日期、限速采样进度、精确字节等 | [按需补充查询](#advanced-queries) |

日常看上表即可，补充查询按需执行。每日统计和 portbw 需先安装；每日流量与总配额含义不同，来源 IP 数也不等于实际人数。

<a id="advanced-queries"></a>
<a id="socks5-query"></a>

<details>
<summary>补充查询：只在总览未提供所需信息时使用</summary>

| 什么时候用 | 命令 | 比日常总览多什么 |
|---|---|---|
| 查配额归属、重置周期 / 日期，或手工 / 主节点端口配额 | `pq_audit.sh` | 遍历所有受管理配额；`vless_audit.sh` 不显示重置字段，主节点行也不汇报配额 |
| 查单端口的基础速度和内核规则状态 | `portbw show 40000` | 只筛该端口，不是更完整的自动限速详情 |
| 查自动限速采样、连续进度、保护剩余时间 | `portbw auto status 40000` | 自动模式的实时采样与计时细节 |
| 限速总览报异常，或脚本需要判断检查失败 | `portbw audit` | 核查 nft/tc 规则；异常会返回失败状态 |
| 查 SOCKS5 配额的精确字节数 | `socks5 quota 41004` | `list` 已有余额，本命令另给精确字节与持久化用量 |
| 查 SOCKS5 完整账号资料和密码 | `socks5 show 41004 --credentials` | 详细 JSON，含敏感凭据 |
| 排查 SOCKS5 出口、路由和服务 | `socks5 status` | 运行环境，不是重复查余额 |
| SOCKS5 防护 / 服务检查需明确失败结果 | `socks5 audit 41004` | 使用账号总览检查逻辑，异常时返回失败；不是访问日志审计 |

`pq_audit.sh` 与 `vless_audit.sh` 对临时节点的 LIMIT / USED / LEFT 使用同一配额快照逻辑，日常不必连续执行。`vless-abuse` 则分析访问日志，不能用节点状态表代替。

</details>

<a id="node-link"></a>

<details>
<summary>按端口查询 VLESS 节点链接</summary>

修改最前面的端口：

```bash
PORT=40001; MAIN_PORT=$(awk -F= '$1=="PORT"{print $2; exit}' /var/lib/vless-reality/main/main.env /etc/default/vless-reality 2>/dev/null); if [ -n "$MAIN_PORT" ] && [ "$PORT" = "$MAIN_PORT" ]; then [ -s /root/vless_reality_vision_url.txt ] && cat /root/vless_reality_vision_url.txt || { echo "主节点链接文件不存在" >&2; exit 1; }; else mapfile -t files < <(grep -l "^PORT=${PORT}$" /var/lib/vless-reality/temp/*.env 2>/dev/null); [ "${#files[@]}" -eq 1 ] || { [ "${#files[@]}" -eq 0 ] && echo "未找到端口 ${PORT} 的节点" >&2 || echo "端口 ${PORT} 匹配到多个临时节点，请先运行 vless_audit.sh 检查" >&2; exit 1; }; url="${files[0]%.env}.url"; [ -s "$url" ] && cat "$url" || { echo "节点存在，但链接文件不存在：$url" >&2; exit 1; }; fi
```

</details>

<a id="active-ips"></a>

<details>
<summary>查看当前来源 IP 与 TCP 连接</summary>

依次为 IP_LIMIT 当前槽位、当前 TCP 连接。槽位持续访问会续期；`IP_LIMIT=0` 不记录槽位。

```bash
PORT=40000; source /usr/local/lib/vless-reality/iplimit-lib.sh; vr_il_active_ips "$PORT" | tr ' ' '\n'
```

```bash
PORT=40000; ss -Htn state established "( sport = :$PORT )"
```

</details>

<a id="daily-traffic"></a>

<details>
<summary>VLESS 每日流量：查询、字段与保留规则</summary>

按北京时间保留最近 30 个自然日；默认看今天，指定端口看历史。UP / DOWN 是用户上传 / 下载，TOTAL 为当日合计，独立于配额。节点删除后历史随采集清理，不能补查安装前的数据。

- 数据保存在 `/var/lib/vless-reality/traffic/daily.json`；更新统计脚本或重启会保留已保存记录，仍按 30 天规则清理。调整、删除或重置配额不会清零每日记录。
- 同名重建节点或复用端口，新节点不会继承旧记录。正常每分钟采集，查询时也会采集；节点到期或删除后，下一次成功采集会清理对应历史。
- 统计包含 TCP 协议开销；跨午夜的采样增量可能有日期归属误差，断电或外部清空计数器可能丢失尚未保存的增量。

```bash
# 查看所有有效用户今天的流量
vless_traffic

# 按端口查看某个用户最近 30 个自然日的每日明细
vless_traffic 40002

# 查看主节点的每日明细（不受主节点端口设置影响）
vless_traffic main

# 按节点 ID 查询（也支持完整 TAG）
vless_traffic tmp001

# 导出某个用户保留的历史记录，流量单位为字节
vless_traffic 40002 --json
```

</details>



<a id="speed-logs"></a>

<details>
<summary>自动限速日志：全部端口、单端口、全部尚存历史</summary>

以下依次查询：最近 24 小时全部端口、最近 24 小时指定端口、指定端口全部尚存历史。北京时间输出；旧日志不代表当前配置，当前值以 `portbw report` 为准。

```bash
TZ=Asia/Shanghai journalctl -u portbw-watch.service \
  --since '24 hours ago' --no-pager -o short-iso \
  | grep -E '自动降速|恢复基础速度|失败|Error|Traceback' \
  || echo '最近24小时没有匹配的降速、恢复或报错日志'
```

```bash
PORT=40002
TZ=Asia/Shanghai journalctl -u portbw-watch.service \
  --since '24 hours ago' --no-pager -o short-iso \
  | grep -E "${PORT} (up|down): (自动降速|恢复基础速度)" \
  || echo "最近24小时端口 ${PORT} 没有降速或恢复记录"
```

```bash
PORT=40002
TZ=Asia/Shanghai journalctl -u portbw-watch.service \
  --no-pager -o short-iso \
  | grep -E "${PORT} (up|down): (自动降速|恢复基础速度)" \
  || echo "端口 ${PORT} 没有尚存的降速或恢复历史记录"
```

</details>

<a id="vless-audit"></a>

### VLESS 滥用与共享查询

首次使用先执行文末的[审计命令安装](#abuse-install)，以后只需一行。在 VLESS VPS 执行，适用于普通 / WG-NAT 临时节点。

```bash
PORT=40000 DAYS=7 vless-abuse
```

改 `PORT` 选择端口；`DAYS=1～90` 查最近天数，`DAYS=0` 查创建以来仍保留的日志。输出来源 IP、目标、异常端口、共享线索及当前 TCP 连接；只读，不自动封禁。历史取决于已记录且保留的日志，风险标记不是滥用定论。



<a id="socks5-daily"></a>

<details>
<summary>SOCKS5 每日流量查询</summary>

按端口查看每日用量，不能用它代替实时剩余配额。

```bash
socks5-traffic                      # 查看所有端口今天的上传/下载用量
```

```bash
socks5-traffic 41004                # 查看端口 41004 最近 30 天的每日用量
```

</details>

<a id="socks5-access"></a>

<details>
<summary>SOCKS5 访问审计：概览、全部域名、错误明细</summary>

以下命令按需选用，不必全部执行。端口使用本机监听端口；天数范围 1～90，北京时间显示。域名仅统计成功且含域名的记录；日志通常在连接结束时写入，未记录 / 已清理的历史不能补查。

域名按原始主机名分别统计，不合并子域名，也不自动排除 CDN / 广告域名；直接通过 IP 连接时不能反推出域名。连接记录次数不是打开网页的次数，不能只凭错误码或访问域名认定恶意行为。

```bash
# 访问概览：完整主机域名 Top 20、来源 IP 历史 Top 20、同一分钟不同来源 IP、当前 TCP 连接
socks5 access 40002 7

# 专项查询：列出全部成功连接的原始主机域名及次数，不限制为前 20 名
socks5 access-domains 40002 7

# 专项查询：所有非零错误码的汇总次数，以及最近 50 条错误的时间/IP/目标明细
socks5 access-errors 40002 7

# 只改变错误明细显示数量；错误码统计依然覆盖全部查询时段
socks5 access-errors 40002 7 --limit 200

# 显示全部非零错误连接明细（高流量端口可能输出很长）
socks5 access-errors 40002 7 --all

```

</details>

<a id="subscription"></a>

<details>
<summary>导出有效临时节点订阅（生成本地文件）</summary>

生成 `/root/vless_temp_subscription.txt` 和 `/root/vless_temp_subscription_base64.txt`，只包含有效且在运行的临时节点，不含主节点。不是在线订阅网址；Base64 也不是加密。

```bash
vless_temp_sub.sh
```

</details>

<a id="create"></a>

## 二、新建节点

<a id="temp-create"></a>

### VLESS 临时节点

在 **VLESS VPS** 执行。下面两种命令二选一：示例有效期 7 天，总配额 50 GiB，最多 3 个活跃来源 IP；WG-NAT 命令需先完成[WG-NAT 部署](#wg-nat)。

普通临时节点：

```bash
DAYS=7; IP_VERSION=4 IP_LIMIT=3 PQ_GIB=50 D=$((DAYS*24*60*60)) vless_mktemp.sh
```

WG-NAT 临时节点：

```bash
DAYS=7; IP_VERSION=4 IP_LIMIT=3 PQ_GIB=50 D=$((DAYS*24*60*60)) vless_mktemp_nat.sh
```

<details>
<summary>其他创建方式：分钟、小时、固定端口、IPv6</summary>

### 按分钟

普通临时节点：

```bash
MINUTES=30; IP_VERSION=4 IP_LIMIT=3 PQ_GIB=1 D=$((MINUTES*60)) vless_mktemp.sh
```

WG-NAT 临时节点：

```bash
MINUTES=30; IP_VERSION=4 IP_LIMIT=3 PQ_GIB=1 D=$((MINUTES*60)) vless_mktemp_nat.sh
```

### 按小时

普通临时节点：

```bash
HOURS=2; IP_VERSION=4 IP_LIMIT=3 PQ_GIB=1 D=$((HOURS*60*60)) vless_mktemp.sh
```

WG-NAT 临时节点：

```bash
HOURS=2; IP_VERSION=4 IP_LIMIT=3 PQ_GIB=1 D=$((HOURS*60*60)) vless_mktemp_nat.sh
```

### 固定端口

下面示例固定使用端口 `40000`，有效期为 1 小时。

普通临时节点：

```bash
HOURS=1; IP_VERSION=4 PORT_START=40000 PORT_END=40000 IP_LIMIT=3 PQ_GIB=1 D=$((HOURS*60*60)) vless_mktemp.sh
```

WG-NAT 临时节点：

```bash
HOURS=1; IP_VERSION=4 PORT_START=40000 PORT_END=40000 IP_LIMIT=3 PQ_GIB=1 D=$((HOURS*60*60)) vless_mktemp_nat.sh
```

固定端口时，`PORT_START` 和 `PORT_END` 必须设置为同一个端口。

### 创建 IPv6 入站节点

IPv6 只需改一个参数，按下面两步操作：

1. 在 `/etc/default/vless-reality` 中填写 `PUBLIC_IPV6_DOMAIN`，并确保该域名的 AAAA 记录指向当前 VLESS VPS。
2. 将上面任意创建命令中的 `IP_VERSION=4` 改成 `IP_VERSION=6`，其他参数不用改。

例如，创建 IPv6 临时节点：

```bash
HOURS=2; IP_VERSION=6 IP_LIMIT=3 PQ_GIB=1 D=$((HOURS*60*60)) vless_mktemp.sh
```

WG-NAT 同样只需把 `IP_VERSION=4` 改成 `IP_VERSION=6`；客户端通过 IPv6 连接 VLESS VPS，出站仍是 NAT 机的公网 IPv4。

常用调整：

- 不限制来源 IP：改为 `IP_LIMIT=0`
- 不限制流量：删除 `PQ_GIB=...`
- 修改固定端口：同时修改 `PORT_START` 和 `PORT_END`

创建成功后会直接输出端口、到期时间和节点链接。

</details>

<details>
<summary>创建参数、节点类型与自动重置规则</summary>

普通节点用 VPS 出口，WG-NAT 节点用 NAT 出口；`id` 可省略或填写英文 / 数字 / 点 / 下划线 / 连字符。

| 参数 | 含义 |
|---|---|
| `D` | 有效期秒数，由示例前面的分钟 / 小时 / 天数计算 |
| `PQ_GIB` | 上传+下载合计配额；不限量时省略，不能填 0 |
| `IP_LIMIT` | 活跃来源 IP 槽位数；0 为不限数量 |
| `IP_STICKY_SECONDS` | 闲置占位秒数，默认 120；持续访问会刷新 |
| `PORT_START` / `PORT_END` | 固定端口时两项填相同端口 |
| `IP_VERSION` | 入站协议族 4 / 6 |

创建时有配额且有效期严格超过 30 天，才每 30×24 小时自动重置；不是每月 1 日，重置也不延长有效期。

</details>

<a id="socks5-create"></a>

<details>
<summary>新建 SOCKS5 账号：分钟、小时、天、固定端口与公网映射</summary>

命令直接修改数字：`IP_LIMIT`=最多来源 IP 数量；`IP_STICKY_SECONDS`=来源 IP 闲置占位时长（秒）；`PQ_GIB`=上传+下载合计总配额（GiB）。持续活动的 IP 会刷新占位时间，超时后释放名额，不是强制断开已建立连接。

#### 按分钟

创建有效期 **30 分钟**、最多 **1 个来源 IP**、**IP 占位 60 秒（1 分钟）**、总配额 **1 GiB** 的账号：

```bash
MINUTES=30; IP_LIMIT=1 IP_STICKY_SECONDS=60 PQ_GIB=1 D=$((MINUTES*60)) socks5 add
```

#### 按小时

创建有效期 **2 小时**、最多 **2 个来源 IP**、**IP 占位 300 秒（5 分钟）**、总配额 **5 GiB** 的账号：

```bash
HOURS=2; IP_LIMIT=2 IP_STICKY_SECONDS=300 PQ_GIB=5 D=$((HOURS*3600)) socks5 add
```

#### 按天

创建有效期 **7 天**、最多 **3 个来源 IP**、**IP 占位 600 秒（10 分钟）**、总配额 **50 GiB** 的账号：

```bash
DAYS=7; IP_LIMIT=3 IP_STICKY_SECONDS=600 PQ_GIB=50 D=$((DAYS*86400)) socks5 add
```

#### 指定固定端口

创建有效期 **1 小时**、最多 **1 个来源 IP**、**IP 占位 60 秒**、总配额 **1 GiB**、监听端口 `41004` 的账号：

```bash
HOURS=1; IP_LIMIT=1 IP_STICKY_SECONDS=60 PQ_GIB=1 PORT=41004 D=$((HOURS*3600)) socks5 add
```

省略 `PORT` 自动选择本机空闲端口；`IP_LIMIT=0` 不限制来源 IP；删除 `PQ_GIB=...` 表示不限总配额。创建时可选 `id=myproxy` 自定义内部 ID，但**日常命令直接使用端口即可，不用记 ID**。

家宽主机在路由器后面时，需要把公网 **TCP** 端口映射到本机 SOCKS5 监听端口。若外部端口与本地端口不同，例如外部 `51004` 映射到本机 `41004`：

```bash
HOURS=1; IP_LIMIT=1 IP_STICKY_SECONDS=60 PORT=41004 D=$((HOURS*3600)) socks5 add --host proxy.example.com --public-port 51004
```

**重要：下面管理命令使用的是本机监听端口 `41004`，不是路由器映射的外部端口 `51004`。**

</details>

<a id="modify"></a>

## 三、修改与重置

<a id="quota-ip"></a>

### 配额与来源 IP

`pq_add.sh` 会清零已用量和自动重置周期；需要保留周期时用下面的专用命令。

<details>
<summary>设置 / 取消配额、设置 / 取消来源 IP 数量限制</summary>

各命令独立，按需执行；修改临时节点后用 `vless_audit.sh` 核对，手工 / 主节点端口配额用 `pq_audit.sh`。`pq_add.sh 40000 50` 是重新设置 50 GiB，会清零用量与自动重置周期，不是追加 50 GiB；保周期请用下面的专用命令。`pq_del.sh` 取消配额，`ip_del.sh` 取消来源 IP 数量限制，均不删除节点。

```bash
pq_add.sh 40000 50
```


```bash
pq_del.sh 40000
```

```bash
ip_set.sh 40000 2 300
```

```bash
ip_del.sh 40000
```

</details>

<a id="quota-keep-cycle"></a>

### 手动重置指定临时节点流量并保留原自动重置日期

示例：端口 `40000` 重置为 `100 GiB`，已用量清零，并备份节点与配额。保留有效未来重置日期，逾期按原周期顺延；超过 30 天且周期被清零的节点按创建日期恢复，不超过 30 天的节点不新增周期。

<details>
<summary>展开手动重置命令（仅修改开头的 PORT 和 GIB）</summary>

```bash
# 手动重置指定临时节点流量并保留原自动重置日期（示例：40000 重置为 100 GiB）
# 已有重置日期不改变；长期节点若周期被清零则按原创建日期恢复；有效期不超过30天的节点不新增自动重置
# 执行会清零该端口已用流量，并备份原配额与节点配置；仅修改开头的 PORT 和 GIB 即可换端口与配额
PORT=40000 GIB=100 bash -c 'set -Eeuo pipefail; source /usr/local/lib/vless-reality/quota-lib.sh; (( EUID == 0 )) || vr_die "请用root执行"; [[ "$PORT" =~ ^[0-9]{1,5}$ ]] && (( PORT >= 1 && PORT <= 65535 )) || vr_die "端口非法"; BYTES="$(vr_parse_gib_to_bytes "$GIB")" || vr_die "流量值非法"; vr_ensure_runtime_dirs; vr_acquire_lock_fd 7 "${VR_LOCK_DIR}/temp.lock" 120 "节点锁繁忙"; export VR_TEMP_LOCK_HELD=1; vr_pq_lock; T="$(vr_temp_meta_by_port "$PORT")"; Q="$(vr_quota_meta_file "$PORT")"; [[ -n "$T" && -f "$T" && -f "$Q" ]] || vr_die "节点或配额不存在"; TAG="$(vr_meta_get "$T" TAG)"; [[ "$(vr_meta_get "$Q" OWNER_KIND)" == temp && "$(vr_meta_get "$Q" OWNER_TAG)" == "$TAG" && "$(vr_meta_get "$Q" PORT)" == "$PORT" ]] || vr_die "配额归属异常"; [[ "$(vr_meta_get "$T" PQ_LIMIT_BYTES)" == "$(vr_meta_get "$Q" ORIGINAL_LIMIT_BYTES)" ]] || vr_die "原始配额不一致"; START="$(vr_meta_get "$T" CREATE_EPOCH)"; DURATION="$(vr_meta_get "$T" DURATION_SECONDS)"; EXPIRE="$(vr_meta_get "$T" EXPIRE_EPOCH)"; INTERVAL="$(vr_meta_get "$Q" RESET_INTERVAL_SECONDS)"; NEXT="$(vr_meta_get "$Q" NEXT_RESET_EPOCH)"; QCREATED="$(vr_meta_get "$Q" CREATED_EPOCH)"; for N in "$START" "$DURATION" "$EXPIRE" "$INTERVAL" "$NEXT" "$QCREATED"; do [[ "$N" =~ ^[0-9]+$ ]] || vr_die "时间配置错误"; done; NOW="$(date +%s)"; (( START > 0 && START <= NOW && EXPIRE > NOW && EXPIRE == START + DURATION )) || vr_die "节点已到期或日期异常"; if (( INTERVAL == 0 && NEXT == 0 )); then if (( DURATION > 2592000 )); then INTERVAL=2592000; NEXT=$((START + ((NOW-START)/INTERVAL+1)*INTERVAL)); fi; elif (( INTERVAL > 0 && NEXT > 0 )); then if (( NEXT <= NOW )); then NEXT=$((NEXT+((NOW-NEXT)/INTERVAL+1)*INTERVAL)); fi; else vr_die "自动重置配置不完整"; fi; BACKUP="$(mktemp -d "/root/pq-keepcycle-${PORT}-XXXXXXXX")"; chmod 700 "$BACKUP"; cp -p "$Q" "$BACKUP/quota.env"; cp -p "$T" "$BACKUP/node.env"; echo "备份完成: $BACKUP"; vr_pq_write_meta "$PORT" "$BYTES" 0 "$BYTES" temp "$TAG" "$DURATION" "$EXPIRE" "$NEXT" "$INTERVAL" "$QCREATED" "$NOW" "$NOW" 1; vr_pq_rebuild_port "$PORT" "$BYTES"; vr_meta_upsert "$T" PQ_LIMIT_BYTES "$BYTES"; vr_meta_upsert "$T" PQ_GIB "$GIB"; vr_meta_upsert "$Q" REBUILD_PENDING 0; vr_pq_unlock; flock -u 7; echo "已重置端口 $PORT 为 $GIB GiB"; if (( INTERVAL > 0 )); then TZ=Asia/Shanghai date -d "@$NEXT" "+下次自动重置: %F %T (北京时间)"; else echo "原本无自动重置，保持无自动重置"; fi; pq_audit.sh | grep -F "┃${PORT}│" || true'
```

</details>

<a id="quota-reset-time"></a>

<details>
<summary>查询指定端口下次自动重置时间（只读，含倒计时）</summary>

在 VLESS VPS 上执行，仅修改开头的 `PORT`。输出北京时间和距离预定重置时间的剩余时长，不清零流量，也不修改自动重置日期。

```bash
PORT=40001
META="/var/lib/vless-reality/quota/${PORT}.env"

if [ ! -f "$META" ]; then
    echo "未找到端口 $PORT 的配额配置"
else
    NEXT=$(awk -F= '$1=="NEXT_RESET_EPOCH"{print $2;exit}' "$META")
    INTERVAL=$(awk -F= '$1=="RESET_INTERVAL_SECONDS"{print $2;exit}' "$META")

    if [[ "$NEXT" =~ ^[0-9]+$ && "$INTERVAL" =~ ^[0-9]+$ ]] && (( NEXT > 0 && INTERVAL > 0 )); then
        NOW=$(date +%s)
        echo "端口：$PORT"
        echo "下次重置（北京时间）：$(TZ=Asia/Shanghai date -d "@$NEXT" '+%Y-%m-%d %H:%M:%S')"

        if (( NEXT > NOW )); then
            S=$((NEXT - NOW))
            printf "剩余：%d天 %d小时 %d分钟 %d秒\n" \
                $((S/86400)) $((S%86400/3600)) \
                $((S%3600/60)) $((S%60))
        else
            echo "已到预定重置时间，请检查重置定时器"
        fi
    else
        echo "此端口未启用自动流量重置，或重置配置无效"
    fi
fi
```

`NEXT_RESET_EPOCH` 是配置中的预定时间。项目的 `pq-reset.timer` 在开机约 15 分钟后首次检查，之后通常每小时检查一次；达到预定时间后可能需等下一轮检查才实际重置。出现“已到预定重置时间”时，可以先查询定时器和执行日志：

```bash
systemctl status pq-reset.timer
systemctl list-timers --all pq-reset.timer
TZ=Asia/Shanghai journalctl -u pq-reset.service -n 50 --no-pager
```

</details>

<a id="portbw"></a>

### 自动限速标准：40→18 Mbps，持续 45 秒触发

在实际需要限速的服务器执行；示例端口为 `40000`。整行复制即可：

```bash
portbw auto set 40000 --up 40 --down 40 --trigger 100 --after 45s --auto-up 18 --auto-down 18 --hold 120s --cooldown 0s
```

<details>
<summary>自动限速参数、恢复规则与关闭自动模式</summary>

上传 / 下载分别触发。100% 指本方向 40 Mbps；85% 只用于采样连续性判断，整段窗口仍需达标。保护至少 120 秒，高负载会续期；恢复后零冷却，再次触发仍需重新满足 45 秒条件。手动 set/up/down 会关闭自动模式，删除节点不会自动删除独立限速规则。仅覆盖本机端口，不覆盖任意 WG/NAT 转发；完整双向限速使用默认 nft+tc 模式。

同一端口的 TCP/UDP、IPv4/IPv6 共用上传额度，并共用另一份下载额度，不是每种协议各分一份。静态限速中 `0` 表示该方向不限速。`--nft-only` 不支持下载限速。

自动模式只有 `--cooldown` 可省略，默认 `60s`；零冷却必须明确填 `--cooldown 0s`，其他自动参数均必填。两方向均须满足 `0 < 降速值 < 基础速度`；`--trigger` 的单位为百分比，不是 Mbps。

设置后用 `portbw report` 核对；需要采样进度或内核故障检查时，见[补充查询](#advanced-queries)。

```bash
portbw auto off 40000  # 关闭自动模式，恢复本端口的基础上传 / 下载限速
```

</details>

<details>
<summary>静态限速：设置、修改、取消</summary>

**40001：TCP+UDP 合计上传 10 Mbps / 合计下载 20 Mbps：**

```bash
portbw set 40001 10 20  # 40001：TCP+UDP 合计上传 10 Mbps / 合计下载 20 Mbps
```

**上传上限改为 15 Mbps：**

```bash
portbw up 40001 15      # 上传上限改为 15 Mbps
```

**下载上限改为 30 Mbps（直接限速，不是触发阈值）：**

```bash
portbw down 40001 30    # 下载上限改为 30 Mbps（直接限速，不是触发阈值）
```

**仅关闭下载限速；上传额度不变：**

```bash
portbw down 40001 0     # 仅关闭下载限速；上传额度不变
```

**仅取消端口限速，不删除 VLESS 节点：**

```bash
portbw del 40001        # 仅取消端口限速，不删除 VLESS 节点
```

</details>

<details>
<summary>SOCKS5：修改配额、IP 限制及主动恢复防护</summary>

**查看当前占位数量、具体来源 IP 和剩余占位时间：**

```bash
socks5 ip-show 41004                # 查看当前占位数量、具体来源 IP 和剩余占位时间
```

**最多 2 个来源 IP，闲置占位 60 秒（重置已有占位记录）：**

```bash
socks5 ip-set 41004 2 60            # 最多 2 个来源 IP，闲置占位 60 秒（重置已有占位记录）
```

**取消来源 IP 数量限制：**

```bash
socks5 ip-del 41004                 # 取消来源 IP 数量限制
```

**重新设置 5 GiB 总配额，已用量从零开始：**

```bash
socks5 pq-set 41004 5 --confirm-reset  # 重新设置 5 GiB 总配额，已用量从零开始
```

**取消总配额（不限流量）：**

```bash
socks5 pq-del 41004                 # 取消总配额（不限流量）
```

需要主动检查并恢复防护规则或异常服务时，另行执行（会修改运行状态）：

```bash
socks5 watch
```

SOCKS5 与 VLESS 使用**同一套独立 `portbw` 限速方法**，无需重复设置命令。请在**实际运行 SOCKS5 的家宽主机**按照[端口限速](#portbw)安装并设置；把自动限速示例里的 `40000` 改成 SOCKS5 的**本机监听端口**（如 `41004`），即可使用相同的静态限速或 **40→18 Mbps、100% 持续 45 秒、滚动保护 120 秒、零冷却**的自动限速。查询所有端口时，同样使用前文的 `portbw report`。

**注意：** 如果路由器把公网端口 `51004` 映射到家宽主机的 `41004`，限速应设置在本机端口 **`41004`**，不是公网端口 `51004`。SOCKS5 仅支持 TCP CONNECT，不支持 UDP ASSOCIATE；`portbw` 独立按本机端口管理 TCP+UDP。SOCKS5 账号创建、到期、删除均不会自动增删 `portbw` 规则；升级 `portbw` 也不会修改 SOCKS5 账号、配额和服务。已安装非本系列管理的旧版 `portbw` 的主机先参考[旧版 portbw 迁移说明](#portbw-install)安全迁移；已有受管理版本按 `preflight-upgrade` / `upgrade` 操作。

</details>

<a id="troubleshooting"></a>

## 四、故障排查

<a id="trouble-guide"></a>

### 出问题时，从现象找入口

| 现象 | 先检查什么 | 后续动作 |
|---|---|---|
| `command not found` | 对应组件是否安装成功；是否只下载或只运行了 `check` | 查看对应安装步骤；不要为了一个可选命令重装全部节点 |
| `portbw.py` SHA 不匹配 | 两个文件是否来自同一次下载，文件内容是否被编辑过 | 重新取得配套文件，不删除 SHA 校验 |
| 服务 active / 端口监听，但客户端不通 | 域名解析、云安全组、系统防火墙、客户端链接、来源 IP 槽位和配额 | 按下面的服务 / 域名 / WG 查询继续定位；从外部设备复测 |
| 只有某个用户突然连不上 | 是否到期、配额耗尽、IP 槽位被占、手工暂停或黑名单生效 | VLESS 先查 `vless_audit.sh`，SOCKS5 先查 `socks5 list`，不要先清零 |
| 查询不到历史访问记录 | 该节点是否确实记录过访问日志，是否已被轮替清理 | 无记录不能证明无人使用；查询命令不能补回旧日志 |
| 到点还没看到配额重置 | 是否启用周期、节点是否已到期、是否尚未轮到定时器 | 看[重置日期](#quota-reset-time)和 `pq-reset.timer` / service 日志 |
| 下载速度没有准确显示 5 MB/s | Mbps 与 MB/s 是否混淆、方向与本机端口是否正确、网络是否受限 | 先看 `portbw report`，再按异常情况选择[补充查询](#advanced-queries) |
| 删节点后同端口仍被限速或封禁 | 独立 portbw、端口暂停、来源黑名单是否还有规则 | 分别按[限速](#portbw) / [封禁](#port-block)查询和处理；删节点不等于移除全部手工规则 |
| 重启后短时间 WG-NAT 不通 | WG 握手、路由、监听和看门狗日志 | 按[WG-NAT](#wg-nat) / [看门狗规则](#release-notes)检查恢复过程；不要反复 `nat.sh init/add` |

`systemctl status` 有时进入分页界面，按 `q` 退出。命令显示 `inactive` 不一定都是故障：按需运行的 oneshot 采集服务执行后退出是正常情况，应结合 timer 状态和日志判断。

<details>
<summary>服务、节点日志、流量定时器、域名和 WG-NAT 的排查命令</summary>

#### 主节点

```bash
systemctl status xray.service
TZ=Asia/Shanghai journalctl -u xray.service -n 120 --no-pager
```

#### 临时节点、配额或规则异常

先查询节点状态及临时节点配额：

```bash
vless_audit.sh
```

需要查手工配额、主节点端口配额或重置日期时，再用[补充查询](#advanced-queries)。

确认需要恢复管理规则或服务时，再执行（会修改运行状态）：

```bash
vless_restore_all.sh
```

#### 按端口查看临时节点日志

```bash
PORT=40000; mapfile -t files < <(grep -l "^PORT=${PORT}$" /var/lib/vless-reality/temp/*.env 2>/dev/null); [ "${#files[@]}" -eq 1 ] || { echo "无法唯一找到端口 ${PORT} 对应的临时节点" >&2; exit 1; }; TAG=${files[0]##*/}; TAG=${TAG%.env}; TZ=Asia/Shanghai journalctl -u "${TAG}.service" -n 100 --no-pager
```

#### 每日流量统计

```bash
systemctl status vless-traffic.timer vless-traffic-shutdown.service
TZ=Asia/Shanghai journalctl -u vless-traffic.service -n 50 --no-pager
```

定时器负责每分钟触发采集，采集服务执行完成后退出属于正常行为。若默认查询仍显示多天数据，请先按[每日流量更新步骤](#maintenance)更新。

#### 域名解析

```bash
getent ahostsv4 proxy.example.com
curl -4 https://api.ipify.org

getent ahostsv6 proxy6.example.com
ip -6 addr show scope global
```

#### WG-NAT

```bash
/usr/local/sbin/wg_nat_healthcheck.sh
```

仍有问题时，在 NAT 出口机执行：

```bash
bash /root/nat.sh status
```

</details>

<a id="remove"></a>

## 五、暂停、封禁与删除

<a id="port-block"></a>

先区分操作目标，下面两种封禁由不同 nftables 表管理，解除其中一种不会自动解除另一种。

| 目标 | 范围 | 持久性 | 使用入口 |
|---|---|---|---|
| 暂停整个端口 | 本机 INPUT，外部 IPv4 / IPv6、TCP / UDP | 临时规则，重启或防火墙重载后可能失效 | 端口暂停命令 |
| 按来源 IP / 网段封禁某端口 | IPv4，PREROUTING、DNAT 前，TCP / UDP | 保存配置并启用启动恢复服务 | 来源黑名单命令 |

<a id="pause-port"></a>

### 端口暂停：封禁、解封、状态查询

<details>
<summary>展开端口暂停命令及适用范围</summary>

在**运行该 VLESS 节点的服务器**（例如 `MEGABOX`）以 root 身份执行。**下面三条命令互相独立，每次只改各自的 `PORT=40022` 数字即可。** 不需要安装脚本，也不创建配置文件。

本功能同时封禁**外部 IPv4 / IPv6 的 TCP / UDP 入站**（四种组合）；`lo` 回环流量不拦截。采用每个端口独立的 `inet pause_vless_端口` 临时表，不停止或重启 Xray、WG、systemd，不修改 UUID、配额、IP_LIMIT、已有流量统计或其他端口的规则。**仅处理发往本机的 INPUT 流量**，不处理 FORWARD 转发端口或从本机主动发起的出站连接。

#### 1. 临时封禁（只改 PORT）

```bash
(
PORT=40022
[[ "$PORT" =~ ^[1-9][0-9]{0,4}$ ]] && (( PORT <= 65535 )) || { echo "❌ 端口无效"; exit 1; }
T="pause_vless_$PORT"
if ! nft list table inet "$T" >/dev/null 2>&1; then
  nft -f - >/dev/null 2>&1 <<EOF
add table inet $T
add chain inet $T input { type filter hook input priority -20; policy accept; }
add rule inet $T input iifname != "lo" tcp dport $PORT reject with tcp reset
add rule inet $T input iifname != "lo" udp dport $PORT drop
EOF
fi
R=$(nft list chain inet "$T" input 2>/dev/null) || R=""
if grep -Fq "iifname != \"lo\" tcp dport $PORT reject with tcp reset" <<<"$R" &&
   grep -Fq "iifname != \"lo\" udp dport $PORT drop" <<<"$R"; then
  echo "✅ $PORT 已临时封禁（IPv4 + IPv6 + TCP + UDP）"
else
  echo "❌ $PORT 封禁失败或存在旧版规则；如存在旧版临时表，请先执行第 2 条解封，再重试"
  exit 1
fi
)
```

#### 2. 解除封禁（只改 PORT，删除本功能的整张表）

```bash
(
PORT=40022
[[ "$PORT" =~ ^[1-9][0-9]{0,4}$ ]] && (( PORT <= 65535 )) || { echo "❌ 端口无效"; exit 1; }
T="pause_vless_$PORT"
if nft list table inet "$T" >/dev/null 2>&1; then
  nft delete table inet "$T" >/dev/null 2>&1
fi
if nft list table inet "$T" >/dev/null 2>&1; then
  echo "❌ $PORT 解封失败，临时封禁表仍存在"
  exit 1
else
  echo "✅ $PORT 已解封，临时表、链、规则均已删除"
fi
)
```

#### 3. 查询封禁状态（只改 PORT，只输出中文结果）

```bash
(
PORT=40022
[[ "$PORT" =~ ^[1-9][0-9]{0,4}$ ]] && (( PORT <= 65535 )) || { echo "❌ 端口无效"; exit 1; }
T="pause_vless_$PORT"
R=$(nft list chain inet "$T" input 2>/dev/null) || R=""
if grep -Fq "iifname != \"lo\" tcp dport $PORT reject with tcp reset" <<<"$R" &&
   grep -Fq "iifname != \"lo\" udp dport $PORT drop" <<<"$R"; then
  echo "✅ $PORT 已封禁（IPv4 + IPv6 + TCP + UDP）"
else
  echo "❌ $PORT 未完整封禁（或没有临时封禁规则）"
fi
)
```

**无残留说明：** 解除封禁会删除这个端口专属的 nftables 表以及其中全部链和规则，不产生本功能的配置文件、定时任务或后台进程。命令本身仍可能留在 Bash history；已有 TCP 连接在内核中的状态、系统日志不会因此自动清除。

**注意：** 本功能只检查其专属临时规则，不能替代外部网络连通性测试。解除后若还有其他防火墙规则，端口仍可能无法访问；封禁时服务显示 `active`、端口显示 `LISTEN` 是正常的。临时规则不设到期时间，通常在重启或防火墙规则重载后失效。若端口存在之前创建的旧版 IPv4-only 临时表，第 1 条不会擅自覆盖；先用第 2 条删除旧表，再执行第 1 条重新封禁即可。

</details>

<a id="source-blacklist"></a>

### 来源 IP / CIDR 黑名单

在需要封禁的 Debian 12 服务器上以 root 身份执行。无需下载、安装或修改管理脚本；每条命令都是**单行命令**。只需修改最前面的 **P=40001**（本机目标端口）和 **IPS="..."**（空格隔开的 IPv4 或 CIDR 网段）。例如 **1.2.3.4**、**27.47.34.0/24**，也可以同时输入。带掩码的地址必须写规范网络地址，如 **27.47.34.0/24**，不要写 **27.47.34.26/24**。IPv4 单地址会规范化为 /32。

新封禁统一使用独立 **inet jsh_cidrban** 表；原 README 使用的 **inet jsh_ipban** 表和现有单 IP 黑名单不受新增封禁影响。两种表的规则都按来源 IPv4 + 目标端口，在 PREROUTING 阶段丢弃 TCP / UDP 流量（DNAT 前）；不针对 IPv6。**这是服务器级别的封禁，不是按 VLESS 用户隔离的功能。** 切勿误填 SSH 管理端口，操作前建议保留已有 SSH 会话。

#### 1. 永久拉黑（单 IP / 网段混合，一行）

<details>
<summary>展开永久拉黑命令</summary>

~~~bash
P=40001 IPS="1.2.3.4 5.6.7.8 27.47.34.0/24" bash -c 'set -euo pipefail; (( EUID==0 )) || { echo "需root权限"; exit 1; }; [[ $P =~ ^[1-9][0-9]{0,4}$ ]] && (( P<=65535 )) || { echo "端口无效"; exit 1; }; read -r -a A <<< "$IPS"; (( ${#A[@]} > 0 )) || { echo "IP列表为空"; exit 1; }; NETS=$(python3 -B -c "import ipaddress,sys; [print(ipaddress.IPv4Network(s,strict=True)) for s in sys.argv[1:]]" "${A[@]}"); exec 9>/run/jsh-cidrban.lock; flock -x 9; if ! nft list table inet jsh_cidrban >/dev/null 2>&1; then printf "%s\n" "add table inet jsh_cidrban" "add chain inet jsh_cidrban pre { type filter hook prerouting priority -150; policy accept; }" | nft -f -; fi; for NET in $NETS; do MARK="jshcidr:$P:$NET"; if ! nft -a list chain inet jsh_cidrban pre | grep -Fq "comment \"$MARK\""; then printf "add rule inet jsh_cidrban pre ip saddr %s meta l4proto { tcp, udp } th dport %s counter drop comment \"%s\"\n" "$NET" "$P" "$MARK" | nft -f -; fi; done; umask 077; nft list table inet jsh_cidrban >/etc/jsh-cidrban.nft.tmp; mv -f /etc/jsh-cidrban.nft.tmp /etc/jsh-cidrban.nft; printf "%s\n" "[Unit]" "Description=Jieshu CIDR port blacklist" "After=nftables.service" "Before=network.target" "[Service]" "Type=oneshot" "ExecStart=/usr/sbin/nft -f /etc/jsh-cidrban.nft" "[Install]" "WantedBy=multi-user.target" >/etc/systemd/system/jsh-cidrban.service; systemctl daemon-reload; systemctl enable jsh-cidrban.service >/dev/null; echo "已封禁端口 $P：${A[*]}"'
~~~

重复运行相同 IP/网段和端口会跳过已有的受管理规则；不同端口可以分别添加。规则保存至 **/etc/jsh-cidrban.nft**，启用 **jsh-cidrban.service** 尝试在重启后恢复。现有 **jsh_ipban** 不会被覆盖。此命令会修改 nftables、防火墙配置与 systemd 状态。

<a id="blacklist-report"></a>

</details>

#### 2. 一键查询全部黑名单（只读，按端口排序）

~~~bash
{ nft -n list chain inet jsh_cidrban pre 2>/dev/null | sed -n 's/.*comment "jshcidr:\([0-9][0-9]*\):\([^"]*\)".*/\1 \2/p'; nft -n list set inet jsh_ipban banned 2>/dev/null | awk '/elements =/ {inside=1} inside {gsub(/[{},]/," "); for(i=1;i<=NF-2;i++) if($i ~ /^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$/ && $(i+1)=="." && $(i+2) ~ /^[0-9]+$/) print $(i+2),$i}'; } | sort -k1,1n -k2,2V -u | awk 'BEGIN{print "========== IP黑名单总览 =========="} {if($1!=p){if(NR>1)printf "  小计：%d项\n\n",c; p=$1; c=0; ports++; printf "【端口 %s】\n",p} addr=$2; if(addr ~ /\/32$/)sub(/\/32$/,"",addr); printf "  %-22s %s\n",addr,(index(addr,"/")?"整个网段":"单独IP"); c++; total++} END{if(total){printf "  小计：%d项\n",c}else print "没有查到这两套黑名单的封禁条目"; printf "\n总计：%d个端口，%d项封禁\n",ports,total}'
~~~

依次显示每个端口的封禁地址、单独 IP / 整个网段和封禁条目小计，并显示总端口数、总条目数。**只读取 nftables 当前规则，不创建文件、不修改防火墙、不清零计数器。** 同时兼容原有的 jsh_ipban 与新的 jsh_cidrban；显示的是封禁条目数，而不是已经拦截的数据包数。若存在手工写在其他防火墙表中的黑名单，本查询不会收录。

#### 3. 解除指定 IP 或网段（混合批量，一行）

<details>
<summary>展开批量解封命令</summary>

~~~bash
P=40001 IPS="1.2.3.4 27.47.34.0/24" bash -c 'set -euo pipefail; (( EUID==0 )) || { echo "需root权限"; exit 1; }; [[ $P =~ ^[1-9][0-9]{0,4}$ ]] && (( P<=65535 )) || { echo "端口无效"; exit 1; }; read -r -a A <<< "$IPS"; (( ${#A[@]} > 0 )) || { echo "IP列表为空"; exit 1; }; NETS=$(python3 -B -c "import ipaddress,sys; [print(ipaddress.IPv4Network(s,strict=True)) for s in sys.argv[1:]]" "${A[@]}"); exec 8>/run/jsh-ipban.lock; flock -x 8; exec 9>/run/jsh-cidrban.lock; flock -x 9; N=0; for NET in $NETS; do if [[ $NET == */32 ]] && nft list set inet jsh_ipban banned >/dev/null 2>&1; then IP=${NET%/32}; if nft get element inet jsh_ipban banned "{ $IP . $P }" >/dev/null 2>&1; then nft delete element inet jsh_ipban banned "{ $IP . $P }"; N=$((N+1)); fi; fi; if nft list chain inet jsh_cidrban pre >/dev/null 2>&1; then MARK="jshcidr:$P:$NET"; for H in $(nft -a list chain inet jsh_cidrban pre | grep -F "comment \"$MARK\"" | sed -n "s/.*# handle \([0-9][0-9]*\).*/\1/p" || true); do nft delete rule inet jsh_cidrban pre handle "$H"; N=$((N+1)); done; fi; done; if nft list table inet jsh_ipban >/dev/null 2>&1; then umask 077; nft list table inet jsh_ipban >/etc/jsh-ipban.nft.tmp; mv -f /etc/jsh-ipban.nft.tmp /etc/jsh-ipban.nft; fi; if nft list table inet jsh_cidrban >/dev/null 2>&1; then REM=$(nft -j list chain inet jsh_cidrban pre | python3 -B -c "import json,sys; print(sum(\"rule\" in x for x in json.load(sys.stdin)[\"nftables\"]))"); if [[ $REM == 0 ]]; then systemctl disable jsh-cidrban.service >/dev/null 2>&1 || true; nft delete table inet jsh_cidrban; rm -f /etc/jsh-cidrban.nft /etc/jsh-cidrban.nft.tmp /etc/systemd/system/jsh-cidrban.service; systemctl daemon-reload; else umask 077; nft list table inet jsh_cidrban >/etc/jsh-cidrban.nft.tmp; mv -f /etc/jsh-cidrban.nft.tmp /etc/jsh-cidrban.nft; fi; fi; echo "端口 $P 已解除 $N 条指定封禁；其他端口保持不变"'
~~~

可同时解封原版 jsh_ipban 中的独立 IPv4 和新版 jsh_cidrban 的独立 IPv4（/32）或 CIDR 网段。只解封 P 对应的规则，不删除其他端口封禁；新表规则清空时会清理新模块的持久化文件和服务。**出于避免误删不受此功能管理的规则考虑，旧版 jsh_ipban 即使元素清空也会保留表及其恢复服务（空表不会实际封禁）。**

</details>

#### 4. 清空某一个端口的受管理 IP 黑名单（一行）

<details>
<summary>展开清空指定端口黑名单命令</summary>

~~~bash
P=40001 bash -c 'set -euo pipefail; (( EUID==0 )) || { echo "需root权限"; exit 1; }; [[ $P =~ ^[1-9][0-9]{0,4}$ ]] && (( P<=65535 )) || { echo "端口无效"; exit 1; }; exec 8>/run/jsh-ipban.lock; flock -x 8; exec 9>/run/jsh-cidrban.lock; flock -x 9; OLD=0; NEW=0; if nft list set inet jsh_ipban banned >/dev/null 2>&1; then IPS=$(nft -j list set inet jsh_ipban banned | python3 -B -c "import json,sys,ipaddress; a=[x[\"set\"] for x in json.load(sys.stdin)[\"nftables\"] if \"set\" in x and x[\"set\"].get(\"name\")==\"banned\"]; assert len(a)==1; e=a[0].get(\"elem\",[]); v=[x[\"elem\"][\"val\"] if isinstance(x,dict) and \"elem\" in x else x for x in e]; pairs=[x[\"concat\"] for x in v if isinstance(x,dict) and isinstance(x.get(\"concat\"),list) and len(x[\"concat\"])==2]; assert len(pairs)==len(v),\"元素格式异常\"; [print(ipaddress.IPv4Address(x[0])) for x in pairs if int(x[1])==int(sys.argv[1])]" "$P"); for IP in $IPS; do nft delete element inet jsh_ipban banned "{ $IP . $P }"; OLD=$((OLD+1)); done; umask 077; nft list table inet jsh_ipban >/etc/jsh-ipban.nft.tmp; mv -f /etc/jsh-ipban.nft.tmp /etc/jsh-ipban.nft; fi; if nft list chain inet jsh_cidrban pre >/dev/null 2>&1; then HANDLES=$(nft -j -a list chain inet jsh_cidrban pre | python3 -B -c "import json,sys; a=[x[\"rule\"] for x in json.load(sys.stdin)[\"nftables\"] if \"rule\" in x]; [print(x[\"handle\"]) for x in a if str(x.get(\"comment\",\"\")).startswith(\"jshcidr:\"+sys.argv[1]+\":\")]" "$P"); for H in $HANDLES; do [[ $H =~ ^[0-9]+$ ]] || exit 1; nft delete rule inet jsh_cidrban pre handle "$H"; NEW=$((NEW+1)); done; REM=$(nft -j list chain inet jsh_cidrban pre | python3 -B -c "import json,sys; print(sum(\"rule\" in x for x in json.load(sys.stdin)[\"nftables\"]))"); if [[ $REM == 0 ]]; then systemctl disable jsh-cidrban.service >/dev/null 2>&1 || true; nft delete table inet jsh_cidrban; rm -f /etc/jsh-cidrban.nft /etc/jsh-cidrban.nft.tmp /etc/systemd/system/jsh-cidrban.service; systemctl daemon-reload; else umask 077; nft list table inet jsh_cidrban >/etc/jsh-cidrban.nft.tmp; mv -f /etc/jsh-cidrban.nft.tmp /etc/jsh-cidrban.nft; fi; fi; echo "端口 $P 已清除：原版单IP $OLD 条，混合规则 $NEW 条；其他端口保留"'
~~~

只清理所填 P 在旧版 jsh_ipban 集合中的独立 IP，以及新版 jsh_cidrban 表中标记为 jshcidr:该端口: 的规则；**不会清空其他端口，也不会碰本节的独立整端口暂停规则或 IP_LIMIT 等限制。** 原版表为空时仍会保留空表（避免误删其他未被识别的旧版配置）；新表完全没有剩余规则时会删除自己的表、恢复服务与配置。

</details>

#### 5. 验证与注意事项

~~~bash
nft -a list chain inet jsh_cidrban pre
nft -a list set inet jsh_ipban banned 2>/dev/null
systemctl is-enabled jsh-cidrban.service
~~~

- **封禁生效**：规则中的 counter packets / bytes 代表命中的数据包数 / 字节数，不是 TCP 连接数；新增规则不会强制清除已经建立的连接跟踪状态。
- **重启恢复**：已安装的 jsh-cidrban.service 负责读取保存的规则；当前运行时已核对不等于已经在重启场景验证，重启或防火墙重载后须再查询。
- **并发安全**：原版和新版有各自的锁；本节解封命令依固定顺序取得两把锁。不要在多台终端同时执行封禁、解封或清空命令；不要手工编辑管理表的规则注释。
- **适用范围**：只对本机收到的对应端口数据包匹配，可能影响 NAT/转发，勿把大范围网段误当成某个城市的全部地址。规则不覆盖 IPv6。
- **验证说明**：以上属于 README 操作命令，已核对 Bash 结构及所使用的 nftables 规则格式；README 文件本身不会改变当前服务器。仍需在目标 Debian 12 环境实际验证。

<a id="node-manage"></a>

<details>
<summary>删除指定 VLESS 临时节点 / 清空全部临时节点</summary>

### 按端口强制删除临时节点

**执行后会删除该临时节点及其配额、IP 限制。**

修改最前面的端口：

```bash
PORT=40000; mapfile -t files < <(grep -l "^PORT=${PORT}$" /var/lib/vless-reality/temp/*.env 2>/dev/null); [ "${#files[@]}" -eq 1 ] || { [ "${#files[@]}" -eq 0 ] && echo "没找到端口 ${PORT} 对应的临时节点" >&2 || echo "端口 ${PORT} 匹配到多个临时节点，请先运行 vless_audit.sh 检查" >&2; exit 1; }; TAG=${files[0]##*/}; TAG=${TAG%.env}; FORCE=1 /usr/local/sbin/vless_cleanup_one.sh "$TAG"
```

该命令只删除临时节点，不会删除主节点；普通临时节点和 WG-NAT 临时节点均适用。独立 `portbw` 限速策略和本手册的手工黑名单 / 端口暂停规则不随节点删除自动撤销，复用端口前需分别检查。

### 清空全部临时节点

**执行后会清空所有临时节点，请确认操作范围。**

```bash
vless_clear_all.sh
```

</details>

<details>
<summary>删除指定 SOCKS5 账号</summary>

**删除本机端口 41004 对应的 SOCKS5 账号：**

```bash
socks5 del 41004                    # 删除本机端口 41004 对应的 SOCKS5 账号
```

为兼容旧版，也可以继续输入创建时返回的账号 ID。

</details>

<a id="install"></a>

## 六、安装与更新

按组件展开。**WG-NAT 保留完整两端部署顺序，其他组件也保留完整安装和更新步骤。**

<details>
<summary>环境要求与各脚本运行位置</summary>

### 使用前准备

- VLESS / WG-NAT：Debian 11+ 或 Ubuntu 20.04+，使用 `root`，系统以 systemd 管理服务。
- SOCKS5 的系统验收范围见[SOCKS5 安装说明](#socks5)；端口限速需要 Debian/Ubuntu + systemd。
- 一个 A 记录指向 VLESS VPS 公网 IPv4 的域名；创建 IPv6 临时节点时，另备一个 AAAA 记录指向该 VPS 的域名。
- 放行主节点 TCP 端口（默认 `443`）及实际使用的临时节点 TCP 端口（默认分配范围 `40000–50050`）。
- WG-NAT 使用的 UDP 端口默认是 `51820`，需结合两端防火墙与实际部署放行。
- 本文命令使用 **Bash**；端口、域名、公钥和 Peer 名称均需替换为自己的实际值。

> `nat.sh` 在 NAT 出口机运行，`vpswg.sh` 和 `natjichang.sh` 在 VLESS VPS 运行。共享 NAT 上执行 `init/add/del` 可能重启整个 WG 接口并影响其他 VPS，应安排维护窗口。

### 先确认运行位置

| 组件 / 文件 | 在哪台机器运行 | 用途 |
|---|---|---|
| `vless.sh` | VLESS VPS | 安装主节点和普通临时节点管理工具 |
| `vpswg.sh` | VLESS VPS | 配置 WG-NAT 的 VPS 端 |
| `natjichang.sh` | VLESS VPS | 安装 WG-NAT 临时节点工具 |
| `nat.sh` | NAT 出口机 | 管理一个或多个 VPS 共用的 NAT 出口 |
| `traffic.py` | VLESS VPS | 可选：每日流量统计 |
| `portbw-install.sh`、`portbw.py` | 实际需要限速的服务器 | 可选：按本机端口限速 |
| `socks5-install.sh`、`socks5.py`、`socks5-traffic.py`、`socks5-audit.py` | 独立 SOCKS5 主机 | 可选：SOCKS5 账号、流量与访问审计 |

`tests/` 和 `.github/workflows/` 用于测试及持续集成，无需复制到业务服务器。

</details>

<a id="vless-install"></a>

<details>
<summary>6.1 VLESS 主节点：安装 → 配置 → 创建主节点 → 检查</summary>

### 1. 安装

在 **VLESS VPS** 执行：

```bash
apt-get update && apt-get install -y curl ca-certificates nano
```

依赖安装成功后，下载并安装管理工具（修改系统）：

```bash
curl -fsSL 'https://raw.githubusercontent.com/liucong552-art/jieshu/main/vless.sh' -o /root/vless.sh && chmod 700 /root/vless.sh && bash /root/vless.sh
```

### 2. 修改配置

```bash
nano /etc/default/vless-reality
```

下面是**配置文件内容示例**，写入编辑器，不是终端执行命令：

```bash
PUBLIC_DOMAIN=proxy.example.com
PUBLIC_IPV6_DOMAIN=
CAMOUFLAGE_DOMAIN=www.apple.com
REALITY_DEST=www.apple.com:443
REALITY_SNI=www.apple.com
PORT=443
NODE_NAME=VLESS-REALITY-IPv4
```

在 nano 中修改后，按 `Ctrl+O`、回车保存，再按 `Ctrl+X` 退出。

通常只需要修改：

- `PUBLIC_DOMAIN`：A 记录必须指向当前 VPS
- `PUBLIC_IPV6_DOMAIN`：仅创建 IPv6 临时节点时填写
- `PORT`、`NODE_NAME`：按需修改

脚本默认伪装目标是 `www.apple.com`。需要更换时，请同时修改 `CAMOUFLAGE_DOMAIN`、`REALITY_DEST` 和 `REALITY_SNI`。

安装管理工具成功只代表工具已经就位，**还需要下面第 3 步创建主节点**。

### 3. 创建或更新主节点

```bash
bash /root/onekey_reality_ipv4.sh
```

主节点链接：

```bash
cat /root/vless_reality_vision_url.txt
```

修改配置后重新执行主节点脚本即可。默认会保留原 UUID 和 Reality 密钥。

<details>
<summary>高级选择：固定版本或更换全部主节点凭据（日常无需执行）</summary>

仅需固定 Xray 版本时，将 `vX.Y.Z` 换成实际存在的版本号：

```bash
XRAY_VERSION=vX.Y.Z bash /root/onekey_reality_ipv4.sh
```

仅当你明确要更换主节点 UUID 和 Reality 密钥时执行；旧主节点链接会失效，之后需重新分发链接：

```bash
ROTATE_CREDENTIALS=1 bash /root/onekey_reality_ipv4.sh
```

</details>

### 4. 怎样确认安装成功

在 VLESS VPS 查询：

```bash
systemctl is-active xray.service
ss -ltn '( sport = :443 )'
```

若改过主节点端口，把 `443` 换成实际值。服务通常应显示 `active`，监听列表应包含该端口；再把上面的完整 `vless://` 链接导入自己的兼容客户端，从另一台设备实际连接并访问网页。**服务 active、端口 LISTEN 只是本机检查，不等于外部客户端一定可用。**

客户端连不上时，先看[故障排查](#trouble-guide)，不要通过清空防火墙、删节点或重置流量来试错。

</details>

<a id="wg-nat"></a>

<details>
<summary>6.2 WG-NAT：完整五步部署、NAT 管理与 Peer 探测</summary>

WG-NAT 让 VLESS VPS 上的指定临时节点通过另一台机器的公网 IPv4 出口访问互联网。

### 1. 初始化 NAT 出口机

在 **NAT 出口机** 执行（下载脚本并初始化 WG，可能影响现有连接）：

```bash
curl -fsSL 'https://raw.githubusercontent.com/liucong552-art/jieshu/main/nat.sh' -o /root/nat.sh && chmod 700 /root/nat.sh && bash /root/nat.sh init
```

无法识别公网网卡时：

```bash
WAN_IF=eth0 bash /root/nat.sh init
```

### 2. 配置 VLESS VPS

在 **VLESS VPS** 执行（下载脚本并修改 WG 配置及路由）：

```bash
curl -fsSL 'https://raw.githubusercontent.com/liucong552-art/jieshu/main/vpswg.sh' -o /root/vpswg.sh && chmod 700 /root/vpswg.sh && bash /root/vpswg.sh
```

脚本会输出 VPS WireGuard 公钥。以后忘记时，在 **VLESS VPS** 查询：

```bash
cat /etc/wireguard/wg-nat.pub
```

### 3. 在 NAT 机添加 VPS

在 **NAT 出口机** 执行：

```bash
bash /root/nat.sh add hy2 hy2.example.com '这里替换成VPS公钥'
```

这条命令中的三个参数分别是：

- `hy2`：这台 VLESS VPS 在 NAT 机上的名称，可自行改成 `vps1`、`hk1` 等；以后查看、更新和删除都使用这个名称。
- `hy2.example.com`：VLESS VPS 的公网 IPv4 域名，也可以直接填写公网 IPv4。
- `'这里替换成VPS公钥'`：在 VLESS VPS 执行 `cat /etc/wireguard/wg-nat.pub` 得到的公钥。

NAT 机会自动分配 WG 地址，并打印一条完整的 VPS 回填命令；**使用包含 Peer 探测功能的新版 `nat.sh` 执行 `add` 时**，还会尝试自动为本次新增/更新的 Peer 启用探测定时器（需安装 `ping`，且启动 systemd timer 成功）。如果探测启用失败，Peer 本身仍可能创建成功，请检查警告。**已经存在的旧 Peer 不会因为仅更新脚本文件或 VPS 的 V4 就自动启用探测**，可参考本节后面的 `probe-enable`。**共享 NAT 注意：`add` 会重启整个 WG 接口，其他 VPS 可能短暂断线，请选择维护窗口。**

### 4. 回到 VPS 执行回填命令

原样执行 NAT 机输出的命令。输出丢失时，可以重新执行上一步同名的 `nat.sh add`，NAT 机会再次打印回填命令。

忘记 NAT 出口机公钥时，在 **NAT 出口机** 查询：

```bash
cat /etc/wireguard/wg-exit.pub
```

回填完成后检查出口：

```bash
/usr/local/sbin/wg_nat_healthcheck.sh
```

出现以下结果后再继续：

```text
OK EXIT_IP=x.x.x.x
```

### 5. 安装 WG-NAT 临时节点工具

在 **VLESS VPS** 执行（下载脚本并安装 / 更新 WG-NAT 节点工具）：

```bash
curl -fsSL 'https://raw.githubusercontent.com/liucong552-art/jieshu/main/natjichang.sh' -o /root/natjichang.sh && chmod 700 /root/natjichang.sh && bash /root/natjichang.sh
```

### NAT 出口机管理

以下命令都在 **NAT 出口机** 执行。

#### 查看已经添加的 VPS

```bash
bash /root/nat.sh list
```

先用这条命令查看每台 VPS 的名称。后面的 `hy2` 必须替换成这里显示的实际名称。

#### 查看完整运行状态

```bash
bash /root/nat.sh status
```

用于查看 WireGuard 接口、所有 VPS Peer、Endpoint 和握手状态。连接异常时先执行这条命令。

#### 删除某台 VPS 的 NAT 接入记录

例如删除名称为 `hy2` 的 VPS：

```bash
bash /root/nat.sh del hy2
```

`hy2` 只是示例。删除前先执行 `bash /root/nat.sh list`，复制需要删除的实际名称。删除时会停用对应探测，但会重启整个 WG 接口，其他 VPS 可能短暂断线。

#### 更新 VPS 的域名、IP 或公钥

使用与原来相同的名称再次执行 `add`：

```bash
bash /root/nat.sh add hy2 hy2.example.com '当前VPS公钥'
```

同名 `add` 会更新该 VPS 的连接信息，并保留原来分配的 WG 地址；更新时整个 WG 接口仍会重启。VPS 公钥可在 VLESS VPS 执行以下命令重新查询：

```bash
cat /etc/wireguard/wg-nat.pub
```

#### 忘记公钥时

```bash
# 在 VLESS VPS 查询 VPS 公钥
cat /etc/wireguard/wg-nat.pub

# 在 NAT 出口机查询 NAT 公钥
cat /etc/wireguard/wg-exit.pub
```

### 单独查看或控制某台 VPS 的探测（可选）

下列命令在 **NAT 出口机** 执行。先运行 `bash /root/nat.sh list` 确认名称，把示例 `hy2` 换成实际 Peer 名：

```bash
bash /root/nat.sh probe-once hy2        # 立即发送一次探测
bash /root/nat.sh probe-status hy2      # 查看探测定时器
bash /root/nat.sh probe-enable hy2      # 手动为旧 Peer 开启探测
bash /root/nat.sh probe-disable hy2     # 手动停止指定 Peer 探测
```

上述探测命令本身不会重启 `wg-quick` 或修改其他 Peer 的密钥、Endpoint、WG 路由和防火墙；但 `probe-enable` **会**创建/启用对应的 systemd 探测任务。添加 Peer 时仅在自动启用成功的情况下才无需再执行 `probe-enable`。对于历史 Peer，可在确认映射后单独执行，无需重跑 `nat.sh add`。

**确认探测确实在运行（示例名称 `hy2`，NAT 机执行）：**

```bash
systemctl is-enabled vr-wg-wg-exit-peer-probe@hy2.timer
systemctl is-active vr-wg-wg-exit-peer-probe@hy2.timer
TZ=Asia/Shanghai journalctl -u vr-wg-wg-exit-peer-probe@hy2.service -n 30 --no-pager
wg show wg-exit latest-handshakes
```

`WG_PROBE_SENT` 只代表程序*尝试发送*了数据探测包，不代表对端已收到或真正握手成功；还需要结合实际握手时间和客户端连通性检查。无业务流量时握手时间不一定每 10 秒改变，WireGuard 会按协议需要协商新密钥。

</details>

<a id="daily-install"></a>

<details>
<summary>6.3 VLESS 每日流量：独立安装 / 更新</summary>

在已经安装 VLESS 的 **VLESS VPS** 上，以 `root` 执行。此功能独立安装，支持主节点、普通临时节点和 WG-NAT 临时节点，包括未设置流量配额的节点；无需重新运行主脚本或重启 Xray。

### 安装

在 VLESS VPS 下载并安装 / 更新统计组件：

```bash
curl -fsSL 'https://raw.githubusercontent.com/liucong552-art/jieshu/main/traffic.py' -o /root/vless_traffic.py && python3 /root/vless_traffic.py --install
```

</details>

<a id="portbw-install"></a>

<details>
<summary>6.4 portbw：完整首次安装、受管理版本升级与旧版本迁移</summary>

### 安装 / 更新 portbw（需要同时下载两个文件）

**运行位置：需要限速的服务器。首次安装和升级分开操作。**

1. 仅限没有旧 portbw 的新安装环境，先安装依赖（修改系统）：

```bash
apt-get update && apt-get install -y curl ca-certificates python3 iproute2 nftables util-linux coreutils procps
```

依赖安装成功后，下载两个配套文件；以下命令仅下载，不安装、不创建限速策略：

```bash
curl -fsSL 'https://raw.githubusercontent.com/liucong552-art/jieshu/main/portbw-install.sh' -o /root/portbw-install.sh && \
curl -fsSL 'https://raw.githubusercontent.com/liucong552-art/jieshu/main/portbw.py' -o /root/portbw.py
```

两次下载均成功后再继续。已有 portbw 的主机应看下面的升级说明，不要执行新安装流程。

2. 预检环境和配套源码（不安装 portbw）：

```bash
bash /root/portbw-install.sh check
```

**只在出现 `CHECK PASS` 后继续。** 若提示已有安装，不要删旧文件来强行通过，改看下面的升级 / 迁移说明。

3. 执行实际安装（修改系统）：

```bash
bash /root/portbw-install.sh install
```

应出现 `INSTALL PASS` 和 `VERIFY PASS`；仅下载文件、语法检查或运行 `check` 都不会完成安装。首次安装不会自动创建端口限速策略。

4. 核对安装结果：

```bash
command -v portbw
bash /root/portbw-install.sh verify
systemctl is-active portbw-watch.service
portbw report
portbw audit
```

命令路径应为 `/usr/local/sbin/portbw`，Watchdog 通常为 `active`；尚未设置端口时列表为空属于正常情况。核对通过后，选择后面的静态设置或自动设置。

如预检要求指定物理网卡，先用 `ip -4 route get 1.1.1.1` 查看，再在 `check` 和 `install` 后分别加 `--iface eth0`，把 `eth0` 换成实际物理网卡名；不要根据示例猜网卡。

<details>
<summary>已有受管理版本：升级方法</summary>

**升级已由本系列通用安装器管理的已知 v1/v2/候选版：** 先按上方两条下载命令重新下载同一版安装器和源码，先记录当前的 `portbw report` 与 `portbw audit`，保存可恢复的 VPS 快照，再在维护窗口执行（不要重新执行首次安装 `install`）：

下面三步用 `&&` 串联，前一步失败时不会继续下一步；预检失败时先处理原因，不能跳过：

```bash
bash /root/portbw-install.sh preflight-upgrade && \
bash /root/portbw-install.sh upgrade && \
bash /root/portbw-install.sh verify
```

全部成功后核对：

```bash
portbw report
portbw audit
```

首次安装的 `check` 要求干净环境，已有受管理安装要用 **`preflight-upgrade`**。升级工具只接受有 `/var/lib/portbw-resident-release/current.env` 管理记录，且已安装源码 SHA 与记录一致的受支持旧版；未知来源的旧版即使已有端口配置也**不允许直接覆盖或伪造管理记录**。安装器会持久保存备份，但不能取代 VPS 快照。不要执行 `nft flush ruleset`、`tc qdisc del ... root`，不要停止其他业务的 nft/tc 系统规则。

</details>

<details>
<summary>其他旧仓库 / 无管理记录版本：迁移说明</summary>

**其他旧仓库/无管理记录版本的迁移（不能直接 `install`/`upgrade`）：** 特别是 `zuizhongheji` 等独立旧版及使用旧 tc flower 槽位的机器，先记录每个端口的**基础上/下行、降速上/下行、触发百分比、持续秒数、滚动保护、冷却**，执行 `portbw report` 与 `portbw audit` 并制作 VPS 快照。只可在维护窗口按照确切旧版校验过的迁移工具或逐端口安全删除方法移除旧限速，再安装此通用版并重新添加规则；在删除到重建期间可能暂时失去限速保护。不要把普通安装器用于未知来源旧版本，更不要手动清空整个 nftables ruleset、网卡 root qdisc 或其他业务规则。

</details>

</details>

<a id="socks5"></a>

<details>
<summary>6.5 SOCKS5：首次安装、更新与每日流量组件</summary>

在**单独的家宽主机**上用 `root` 安装，与 VLESS VPS 分开。原 README 记录过 Debian 12 真机验收；仓库的审计验收文档另记录了 Debian 13 暂存环境的检查，并列出了仍待补充的升级 / 干净安装场景。不能据此推断所有发行版和场景均已验收；Ubuntu 22.04/24.04 LTS 仍需独立验证。

### 1. 安装 / 更新

在家宽主机执行；在线安装器会下载并校验配套模块。已有账号的主机按本节末尾的 `update` 流程操作；升级可能重启实例并短暂中断连接。

```bash
apt-get update && apt-get install -y curl ca-certificates
AUTO_DEPS=1 bash <(curl -fsSL 'https://raw.githubusercontent.com/liucong552-art/jieshu/main/socks5-install.sh') install
```

主机位于路由器 NAT 后面时，可以在 `install` 后加 `--host proxy.example.com`（换成自己的公网域名/IP）。必要时加 `--wan-if eth0` 指定物理出口网卡。

**更新现有 SOCKS5 管理器（建议先做 VPS 快照；升级期间已有 3proxy 实例可能短暂重启）：**

```bash
AUTO_DEPS=1 bash <(curl -fsSL 'https://raw.githubusercontent.com/liucong552-art/jieshu/main/socks5-install.sh') update
```

若 `/root/` 已放有本地 SOCKS5 配套源码，安装器可能优先使用它们，应核对是否为同一版本；SHA 不匹配时停止并核对文件，不能跳过校验。初次部署使用上方首次安装的 `install` 命令。日志采集使用每个 SOCKS5 实例自己的 journal，不改变其他端口的记录；`socks5-traffic` 每日统计和 `portbw` 限速按原章节独立管理。

**首次开启或更新每日流量采集：**

```bash
socks5-traffic --install            # 首次开启或更新每日流量采集
```

</details>

<a id="maintenance"></a>

<details>
<summary>6.6 VLESS / WG-NAT / NAT / 每日统计的更新方法</summary>

> **更新范围必须区分**：运行 `vless.sh` 仅刷新 VLESS 侧相关管理组件；NAT 出口机的 `/root/nat.sh`、VPS 侧 `vpswg.sh` 与 `natjichang.sh` 需要分别管理。GitHub 上的 `main` 更新不会自动修改 VPS 硬盘里的旧脚本；需在对应服务器执行下面的更新步骤。生产环境建议固定已验收的提交 URL，而不是每次自动跟随 `main`。

#### VLESS 管理工具

```bash
curl -fsSL 'https://raw.githubusercontent.com/liucong552-art/jieshu/main/vless.sh' -o /root/vless.sh && chmod 700 /root/vless.sh && bash /root/vless.sh
```

需要更新 Xray 主程序或重新应用主配置时：

```bash
bash /root/onekey_reality_ipv4.sh
```

#### 每日流量统计

已安装统计组件时，在 **VLESS VPS** 重新执行以下命令即可更新：

```bash
curl -fsSL 'https://raw.githubusercontent.com/liucong552-art/jieshu/main/traffic.py' -o /root/vless_traffic.py && python3 /root/vless_traffic.py --install
```

无需删除历史数据，也无需重新安装主脚本。更新后运行 `vless_traffic`，标题应显示“今日”；运行 `vless_traffic main` 可查看主节点保留的每日明细。

#### VLESS VPS 的 WG-NAT 工具

```bash
curl -fsSL 'https://raw.githubusercontent.com/liucong552-art/jieshu/main/vpswg.sh' -o /root/vpswg.sh && chmod 700 /root/vpswg.sh && bash /root/vpswg.sh
curl -fsSL 'https://raw.githubusercontent.com/liucong552-art/jieshu/main/natjichang.sh' -o /root/natjichang.sh && chmod 700 /root/natjichang.sh && bash /root/natjichang.sh
```

#### NAT 出口机

**核对脚本是否一致（下载临时对照文件，不重启 WG）：**

```bash
( CANDIDATE=$(mktemp) || exit 1
trap 'rm -f -- "$CANDIDATE"' EXIT
curl -fsSL 'https://raw.githubusercontent.com/liucong552-art/jieshu/main/nat.sh' -o "$CANDIDATE" && sha256sum /root/nat.sh "$CANDIDATE"
)
```

下载成功后两行 SHA256 一样，表示服务器脚本与当前下载文件一致，无需为此重新初始化。下载失败则无法比较，不能把失败的空输出当成“已是最新版”。不同则先备份并确认来源及改动。**仅更新管理脚本文件，不等于执行 `init`，也不会自动为旧 Peer 启用探测**。如果目的是给既有 Peer 补上探测，请使用[WG-NAT 部署与管理](#wg-nat)的 `probe-status` / `probe-enable`，不要为此运行会影响所有 WG Peer 的 `init` 或 `add`。

**旧 NAT 机升级前先备份：** 在 NAT 出口机执行以下命令（备份包含 WG 私钥，切勿公开上传），然后安排维护窗口：

```bash
umask 077
mkdir -p /root/wg-backups
BACKUP_TS=$(date +%Y%m%d-%H%M%S)
tar -C /etc -czf "/root/wg-backups/wireguard-${BACKUP_TS}.tar.gz" wireguard
iptables-save > "/root/wg-backups/iptables-${BACKUP_TS}.rules"
```

**只有明确需要重新初始化或迁移 NAT 端 WG 配置时**，才在维护窗口执行以下命令；它会下载管理脚本并重新初始化 WG，可能造成共用出口所有 Peer 短暂中断：
```bash
curl -fsSL 'https://raw.githubusercontent.com/liucong552-art/jieshu/main/nat.sh' -o /root/nat.sh && chmod 700 /root/nat.sh && bash /root/nat.sh init
```

</details>

<a id="abuse-install"></a>

<details>
<summary>6.7 安装 VLESS 滥用审计命令（首次执行一次）</summary>

在 VLESS VPS 以 root 整段执行，需要 Python 3.9+、Asia/Shanghai 时区数据、journalctl 和 ss。只安装独立命令 `/usr/local/sbin/vless-abuse`，不修改节点、配额、WG、限速或防火墙，也不启用访问日志。

```bash
(
set -euo pipefail
(( EUID == 0 )) || { echo "请用 root 执行"; exit 1; }
DEST=/usr/local/sbin/vless-abuse
if [[ -e "$DEST" || -L "$DEST" ]]; then
    [[ -f "$DEST" && ! -L "$DEST" ]] && grep -Fxq '# jieshu-readme-vless-abuse-v1' "$DEST" || {
        echo "目标路径已有其他文件，停止安装：$DEST"; exit 1;
    }
fi
AUDIT_TMP=$(mktemp)
trap 'rm -f -- "$AUDIT_TMP"' EXIT
cat >"$AUDIT_TMP" <<'JIESHU_ABUSE_PY'
#!/usr/bin/env python3
# jieshu-readme-vless-abuse-v1
import os, sys, glob, re, json, time, ipaddress, subprocess, resource
from datetime import datetime
from collections import Counter, defaultdict, deque
from itertools import combinations
from zoneinfo import ZoneInfo

P=os.environ.get('PORT','')
D=os.environ.get('DAYS','')
if not (P.isdecimal() and D.isdecimal() and 1<=int(P)<=65535 and 0<=int(D)<=90):
    sys.exit('参数错误：PORT=1..65535，DAYS=0..90')
PORT=int(P)
DAYS=int(D)
CN=ZoneInfo('Asia/Shanghai')
MAX_MB=384

def safe(x,limit=125):
    return ''.join(c if c.isprintable() and c not in '\x1b\x7f' else '?' for c in str(x))[:limit]

def stamp(ts):
    return datetime.fromtimestamp(ts,CN).strftime('%Y-%m-%d %H:%M:%S')

def day(ts):
    return datetime.fromtimestamp(ts,CN).strftime('%Y-%m-%d')

def net(ip):
    a=ipaddress.ip_address(ip)
    prefix=24 if a.version==4 else 64
    return str(ipaddress.ip_network(f'{ip}/{prefix}',strict=False))

def peerip(raw):
    raw=re.sub(r'^(tcp|udp):','',raw,flags=re.I)
    if raw.startswith('['):
        h=raw[1:].split(']',1)[0]
    else:
        h=raw.rsplit(':',1)[0]
    h=h.split('%',1)[0]
    addr=ipaddress.ip_address(h)
    return str(addr.ipv4_mapped or addr) if addr.version==6 else str(addr)

def target(raw):
    host,port=raw.rsplit(':',1)
    port=int(port)
    if not 1<=port<=65535:
        raise ValueError('invalid port')
    host=host.strip('[]').lower().rstrip('.')
    if not host:
        raise ValueError('missing host')
    try:
        h=ipaddress.ip_address(host)
        return str(h),port,True
    except ValueError:
        return host,port,False

def make_stat():
    return {
        'count':0,'tcp':0,'udp':0,'first':None,'last':None,
        'days':Counter(),'day_spans':{},
        'mins':Counter(),'hours':Counter(),
        'targets':Counter(),'domains':Counter(),'ports':Counter(),
        'hostset':set(),'iphosts':set(),'portset':set(),
        'hostports':defaultdict(set),
        'smtp':0,'dns':0,'p2p':0,'tracker':0,'remote':0,
        'remotehosts':set(),'nonglobal':Counter(),'denied':0
    }

matches=[]
for f in glob.glob('/var/lib/vless-reality/temp/*.env'):
    try:
        with open(f,encoding='utf-8',errors='replace') as h:
            if any(line.strip()==f'PORT={PORT}' for line in h):
                matches.append(f)
    except OSError:
        pass

if len(matches)!=1:
    sys.exit(f'端口{PORT}对应节点数量={len(matches)}，应为1，请运行vless_audit.sh检查')

meta=matches[0]
tag=os.path.basename(meta)[:-4]
if not re.fullmatch(r'vless-temp-[A-Za-z0-9._-]+',tag):
    sys.exit('节点名称不合法')

unit=tag+'.service'
meta_values={}

with open(meta,encoding='utf-8',errors='replace') as f:
    for line in f:
        if '=' in line:
            k,v=line.strip().split('=',1)
            if k in ('CREATE_EPOCH','EXPIRE_EPOCH','IP_LIMIT','LANDING','IP_VERSION'):
                meta_values[k]=v

now=time.time()
created=meta_values.get('CREATE_EPOCH','')
if not created.isdecimal() or int(created)<=0:
    sys.exit('节点创建时间缺失或异常')

start=max(now-DAYS*86400,int(created)) if DAYS else int(created)
if start>now:
    sys.exit('节点创建时间在未来')

try:
    with open('/usr/local/etc/xray/'+tag+'.json',encoding='utf-8') as f:
        xcfg=json.load(f)
    access=xcfg.get('log',{}).get('access','默认控制台')
except (OSError,ValueError,TypeError,AttributeError):
    access='无法检查'

pat=re.compile(r'\bfrom\s+(\S+)\s+(accepted|rejected)\s+(?:(tcp|udp):)?(\S+)?',re.I)

S=defaultdict(make_stat)
top_domains=Counter()
top_ports=Counter()
top_targets=Counter()
minute_ips=defaultdict(set)
hour_ips=defaultdict(set)
day_ips=defaultdict(set)
hour_dst_ips=defaultdict(set)
hour_dst_ports=defaultdict(set)
near_pairs=Counter()
near_seen={}
recent=deque()
recent_count=Counter()

accepted=rejected=bad=unmatched=bad_json=0
first_event=last_event=None
reversed_clock=0
recent_time=-1
scanned=0
examples=[]

proc=subprocess.Popen(
    ['journalctl','-q','-u',unit,
     '--since=@'+str(int(start)),
     '--until=@'+str(int(now)),
     '-o','json','--no-pager'],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    errors='replace',
    env=dict(os.environ,TZ='Asia/Shanghai')
)

try:
    for raw in proc.stdout:
        scanned+=1

        if scanned%8192==0 and resource.getrusage(resource.RUSAGE_SELF).ru_maxrss>MAX_MB*1024:
            proc.kill()
            sys.exit(f'扫描到{scanned}行，超过{MAX_MB}MiB内存保护阈值，本次结果不完整，请缩小DAYS')

        try:
            ob=json.loads(raw)
            msg=ob.get('MESSAGE','')
            if not isinstance(msg,str):
                raise ValueError()
            ts=int(ob['__REALTIME_TIMESTAMP'])/1000000
        except (ValueError,TypeError,KeyError):
            bad_json+=1
            continue

        m=pat.search(msg)
        if not m:
            if ' accepted ' in msg or ' rejected ' in msg:
                unmatched+=1
                if len(examples)<3:
                    examples.append(safe(msg,170))
            continue

        try:
            ip=peerip(m.group(1))
        except (ValueError,IndexError):
            bad+=1
            continue

        if m.group(2).lower()=='rejected':
            rejected+=1
            S[ip]['denied']+=1
            continue

        if not m.group(3) or not m.group(4):
            bad+=1
            continue

        try:
            host,dp,is_ip=target(m.group(4))
        except (ValueError,IndexError):
            bad+=1
            continue

        proto=m.group(3).lower()
        accepted+=1
        first_event=ts if first_event is None else min(first_event,ts)
        last_event=ts if last_event is None else max(last_event,ts)

        dy=day(ts)
        minute=int(ts//60)
        hour=int(ts//3600)

        s=S[ip]
        s['count']+=1
        s[proto]+=1
        s['first']=ts if s['first'] is None else min(s['first'],ts)
        s['last']=ts if s['last'] is None else max(s['last'],ts)
        s['days'][dy]+=1
        s['mins'][minute]+=1
        s['hours'][hour]+=1

        if dy not in s['day_spans']:
            s['day_spans'][dy]=[ts,ts]
        else:
            s['day_spans'][dy][0]=min(s['day_spans'][dy][0],ts)
            s['day_spans'][dy][1]=max(s['day_spans'][dy][1],ts)

        ep=f'{proto}:{host}:{dp}'
        pp=f'{proto}/{dp}'
        s['targets'][ep]+=1
        s['ports'][pp]+=1
        s['hostset'].add(host)
        s['portset'].add(dp)

        top_targets[ep]+=1
        top_ports[pp]+=1

        if is_ip:
            s['iphosts'].add(host)
            s['hostports'][host].add(dp)
            hour_dst_ips[(ip,hour)].add(host)
            if not ipaddress.ip_address(host).is_global:
                s['nonglobal'][host]+=1
        else:
            s['domains'][host]+=1
            top_domains[host]+=1

        hour_dst_ports[(ip,hour)].add(dp)

        if proto=='tcp' and dp in (25,465,587,2525):
            s['smtp']+=1
        if dp in (53,853):
            s['dns']+=1
        if 6881<=dp<=6999 or dp in (51413,6969):
            s['p2p']+=1
        if re.search(r'(^|[.\-])(tracker|bittorrent|torrent|dht|announce)([.\-]|$)',host):
            s['tracker']+=1

        if proto=='tcp' and dp in (21,22,23,445,3389,5900,2375,6379,11211,27017):
            s['remote']+=1
            if is_ip:
                s['remotehosts'].add(host)

        minute_ips[minute].add(ip)
        hour_ips[hour].add(ip)
        day_ips[dy].add(ip)

        if ts<recent_time:
            reversed_clock+=1
            recent.clear()
            recent_count.clear()

        recent_time=ts

        while recent and recent[0][0]<ts-10:
            _,old=recent.popleft()
            recent_count[old]-=1
            if recent_count[old]==0:
                del recent_count[old]

        for other in recent_count:
            if other!=ip:
                pair=tuple(sorted((ip,other)))
                if near_seen.get(pair)!=minute:
                    near_pairs[pair]+=1
                    near_seen[pair]=minute

        recent.append((ts,ip))
        recent_count[ip]+=1

finally:
    proc.stdout.close()
    err=proc.stderr.read().strip()
    rc=proc.wait()

if rc:
    sys.exit('Journal读取失败：'+safe(err,350))

pair_mins=Counter()
pair_days=defaultdict(set)
pair_span={}
crowded=[]
overlap_mins=Counter()

for minute,ips in minute_ips.items():
    if len(ips)<2:
        continue

    for ip in ips:
        overlap_mins[ip]+=1

    if len(ips)>128:
        crowded.append((minute,len(ips),tuple(sorted(ips))))
        continue

    for pair in combinations(sorted(ips),2):
        pair_mins[pair]+=1
        pair_days[pair].add(day(minute*60))
        if pair not in pair_span:
            pair_span[pair]=[minute,minute]
        else:
            pair_span[pair][0]=min(pair_span[pair][0],minute)
            pair_span[pair][1]=max(pair_span[pair][1],minute)

rank=sorted(S,key=lambda ip:(-S[ip]['count'],-S[ip]['denied'],ip))

print('\n'+'='*72)
print(f'VLESS 滥用与共享深度审计 | 端口 {PORT}')
print('='*72)
print('节点:',unit)
print('类型:',meta_values.get('LANDING','普通/未标注'))
print('IP_LIMIT:',meta_values.get('IP_LIMIT','未知'))
print('查询范围:', '节点创建以来' if DAYS==0 else str(DAYS)+'天')
print('开始:',stamp(start))
print('结束:',stamp(now))
print('实际最早记录:',stamp(first_event) if first_event else '无')
print('实际最近记录:',stamp(last_event) if last_event else '无')
print('访问日志配置:',access)
print('成功代理连接:',format(accepted,','))
print('拒绝记录:',format(rejected,','))
print('不同来源IP:',len(S))
print('解析失败:',bad,'JSON异常:',bad_json,'其他格式:',unmatched)
print('日志时间倒退:',reversed_clock)

if examples:
    print('未识别日志样例:')
    for x in examples:
        print(' ',x)

if access=='none':
    print('警告：Xray访问日志被禁用')

if not accepted:
    print('警告：无成功代理记录，不代表无人使用')

print('\n【1/9 全部来源IP与访问详情】')

for i,ip in enumerate(rank,1):
    s=S[ip]
    peak=max(s['mins'].values(),default=0)
    flags=[]

    if s['smtp']:
        flags.append('SMTP='+str(s['smtp']))
    if s['p2p'] or s['tracker']:
        flags.append('P2P线索='+str(s['p2p']+s['tracker']))
    if len(s['remotehosts'])>=20 and s['remote']>=40:
        flags.append('远程端口大量多目标')
    if any(len(hour_dst_ips[(ip,h)])>=40 and len(hour_dst_ports[(ip,h)])>=12 for h in s['hours']):
        flags.append('疑似端口/主机扫描')
    if s['dns']>=500:
        flags.append('高频DNS='+str(s['dns']))
    if s['nonglobal']:
        flags.append('非公网目标='+str(sum(s['nonglobal'].values())))
    if any(len(v)>15 for v in s['hostports'].values()):
        flags.append('同目标IP多端口')
    if peak>=120:
        flags.append('高频连接='+str(peak)+'/分钟')
    if overlap_mins[ip]>=3:
        flags.append('多IP同分钟='+str(overlap_mins[ip]))

    print('\n'+'-'*72)
    print(f'{i}. {ip}')
    print('连接:',format(s['count'],','),'TCP:',format(s['tcp'],','),'UDP:',format(s['udp'],','))
    print('拒绝:',s['denied'])
    print('活跃:',len(s['days']),'天',len(s['mins']),'分钟')
    print('首次:',stamp(s['first']) if s['first'] else '-')
    print('最近:',stamp(s['last']) if s['last'] else '-')
    print('独立目标:',len(s['hostset']))
    print('独立目标IP:',len(s['iphosts']))
    print('目标端口种类:',len(s['portset']))
    print('峰值:',peak,'次/分钟')
    print('风险标记:','；'.join(flags) if flags else '未触发阈值，不代表没有风险')

    if s['nonglobal']:
        print('\n  非公网目标TOP10:')
        for pos,(host,num) in enumerate(s['nonglobal'].most_common(10),1):
            print(f'    {pos:2}. {safe(host,100)}  ({num:,}次)')

    multis=sorted(((len(v),k) for k,v in s['hostports'].items() if len(v)>=10),reverse=True)
    if multis:
        print('\n  同一目标IP多端口TOP10:')
        for pos,(cnt,host) in enumerate(multis[:10],1):
            print(f'    {pos:2}. {safe(host,100)}  ({cnt:,}个端口)')

    print('\n  访问目标TOP15（每个目标独立一行）:')
    for pos,(host,num) in enumerate(s['targets'].most_common(15),1):
        print(f'    {pos:2}. {safe(host,105)}  ({num:,}次)')
    rest=len(s['targets'])-15
    if rest>0:
        print(f'    其余{rest:,}种目标未展开，已全部计入统计')

if not rank:
    print('暂无成功代理连接记录')

print('\n【2/9 多IP共享嫌疑分析】')
print('不同IP出现的分钟:',sum(len(x)>=2 for x in minute_ips.values()))
print('不同IP出现的小时:',sum(len(x)>=2 for x in hour_ips.values()))

print('\n10秒以内不同来源IP建立连接的组合:')
for pair,k in near_pairs.most_common():
    cross=net(pair[0])!=net(pair[1])
    print(pair[0],'+',pair[1])
    print('  重叠分钟:',k)
    print('  网段:', '不同网段' if cross else '相同网段')
if not near_pairs:
    print('无')

print('\n同一分钟不同来源IP累计重叠:')
for pair,k in pair_mins.most_common():
    lo,hi=pair_span[pair]
    cross=net(pair[0])!=net(pair[1])
    print('\n',pair[0],'+',pair[1])
    print('  重叠:',k,'分钟')
    print('  跨越:',len(pair_days[pair]),'天')
    print('  首次:',stamp(lo*60))
    print('  最近:',stamp(hi*60))
    print('  网段:', '不同网段' if cross else '相同网段')
    if k>=3 and len(pair_days[pair])>=2 and cross:
        print('  标记:优先核对共享')
if not pair_mins:
    print('无')

if crowded:
    print('\n超过128个IP的分钟（跳过两两组合，保留全部IP）:')
    for m,k,ips in sorted(crowded,reverse=True):
        print(stamp(m*60),k,'个')
        for ip in ips:
            print(' ',ip)

print('\n同一分钟最多不同IP:',max((len(x) for x in minute_ips.values()),default=0))
print('\n多IP同分钟TOP30:')
shown=0
for m,ips in sorted(minute_ips.items(),key=lambda x:(-len(x[1]),-x[0])):
    if len(ips)<2:
        break
    print(stamp(m*60),'|',len(ips),'个来源IP')
    for ip in sorted(ips):
        print(' ',ip)
    shown+=1
    if shown>=30:
        break

print('\n【3/9 每日来源IP与活动时段】')
for dy in sorted(day_ips):
    print('\n',dy,'|',len(day_ips[dy]),'个来源IP')
    for ip in sorted(day_ips[dy],key=lambda x:(-S[x]['days'][dy],x)):
        a,b=S[ip]['day_spans'][dy]
        print(' ',ip)
        print('   连接:',format(S[ip]['days'][dy],','))
        print('   首次:',stamp(a)[11:],'最近:',stamp(b)[11:])

print('\n【4/9 常见滥用用途与异常端口】')
kinds=[
    ('SMTP发信端口25/465/587/2525','smtp'),
    ('P2P常见端口','p2p'),
    ('Tracker/DHT域名特征','tracker'),
    ('DNS端口53/853','dns'),
    ('远程登录与数据库端口','remote')
]
for title,kind in kinds:
    print('\n',title)
    found=False
    for ip in rank:
        if S[ip][kind]:
            found=True
            print(' ',ip,':',S[ip][kind],'次')
            print('  该来源IP目的端口TOP15:')
            for pos,(pp,num) in enumerate(S[ip]['ports'].most_common(15),1):
                print(f'    {pos:2}. {pp}  ({num:,}次)')
    if not found:
        print(' 无')

print('\n每个IP的目标离散度:')
for ip in rank:
    hs=[(len(hour_dst_ips[(ip,h)]),len(hour_dst_ports[(ip,h)]),h) for h in S[ip]['hours']]
    a,b,h=max(hs,default=(0,0,0))
    c,e,q=max(hs,key=lambda x:x[1],default=(0,0,0))
    print(ip)
    print('  单小时最多不同目标IP:',a)
    print('  当时不同目标端口:',b)
    print('  单小时最多不同目标端口:',e)

print('\n【5/9 全局访问排行TOP30】')
for name,c in [('域名',top_domains),('目标',top_targets)]:
    print('\n',name,'| 总种类:',len(c))
    for pos,(k,v) in enumerate(c.most_common(30),1):
        print(f'  {pos:2}. {safe(k,110)}  ({v:,}次)')

print('\n【6/9 每个来源IP连接峰值TOP3】')
for ip in rank:
    s=S[ip]
    print('\n',ip,'| 活跃:',len(s['days']),'天')
    for m,v in s['mins'].most_common(3):
        print('  ',stamp(m*60),f'{v:,}次/分钟')

print('\n【7/9 当前ESTABLISHED TCP连接】')
try:
    r=subprocess.run(
        ['ss','-Htn','state','established',f'( sport = :{PORT} )'],
        capture_output=True,text=True,errors='replace',timeout=8
    )
    if r.returncode:
        print('ss查询失败:',safe(r.stderr,170))
    else:
        peers=Counter()
        invalid=0
        for line in r.stdout.splitlines():
            try:
                peers[peerip(line.split()[-1])]+=1
            except (ValueError,IndexError):
                invalid+=1
        for ip,k in peers.most_common():
            print(' ',ip,k,'条')
        print('当前不同来源IP:',len(peers))
        print('当前已建立TCP连接:',sum(peers.values()))
        print('无法解析:',invalid)
        if len(peers)>=2:
            print('注意：当前多个IP有TCP连接，不等于证明多人共享')
except (OSError,subprocess.TimeoutExpired) as e:
    print('ss查询不可用:',safe(e))

print('\n【8/9 目标协议/端口统计（独立板块）】')
print('\n全局目标协议/端口TOP30：')
for pos,(pp,num) in enumerate(top_ports.most_common(30),1):
    print(f'  {pos:2}. {pp}  ({num:,}次)')
if not top_ports:
    print('  暂无可统计记录')
for ip in rank:
    print(f'\n来源IP：{ip}')
    print('  目标协议/端口（全部逐行）：')
    for pos,(pp,num) in enumerate(S[ip]['ports'].most_common(),1):
        print(f'    {pos:2}. {pp}  ({num:,}次)')
    if not S[ip]['ports']:
        print('    无成功代理连接的目标端口记录')

print('\n【9/9 统计边界与只读说明】')
print('全部可解析来源IP和连接均已参加统计。')
print('TOP访问目标仅限制展示条数，不限制统计范围。')
print('10秒内连接不等于真正同时在线。')
print('连接次数不等于流量大小或网页打开次数。')
print('SMTP、P2P、扫描指标只是风险线索，不能直接证明滥用。')
print('普通443端口也可能承载P2P流量。')
print('无法恢复未保留的历史日志。')
print('防火墙提前拦截的连接可能不产生Xray访问记录。')
print('本命令不修改节点、配额、WG、限速、防火墙或服务。')
print('\n审计完成。')
JIESHU_ABUSE_PY
python3 -B - "$AUDIT_TMP" <<'JIESHU_ABUSE_CHECK'
import ast, pathlib, sys
ast.parse(pathlib.Path(sys.argv[1]).read_text())
JIESHU_ABUSE_CHECK
install -m 0755 "$AUDIT_TMP" "$DEST"
echo "已安装 vless-abuse；查询：PORT=40000 DAYS=7 vless-abuse"
)
```

出现“已安装 vless-abuse”后，日常只用 `PORT=40000 DAYS=7 vless-abuse`。这是本 README 新增的独立工具，尚未包含在仓库原安装器中；运行 `vless.sh` 不会自动安装它。需要删除时执行：

```bash
rm -- /usr/local/sbin/vless-abuse
```

大流量端口建议先查 1～7 天；程序在读 journal 期间定期检查约 384 MiB 内存阈值并提示缩小范围，但不是严格峰值上限。计数按可解析日志，Top N 仅限制展示；单分钟超过 128 个来源时跳过该分钟的两两组合分析。

</details>

<a id="backup-recovery"></a>

<details>
<summary>备份位置与回退方法</summary>

### 操作前备份，以及回退的边界

升级主脚本、WG-NAT、SOCKS5 或 portbw 前，在服务商面板创建可恢复的整机快照，记录快照时间、当前端口、到期日期和关键查询结果。快照应能从服务商控制台恢复；仅下载一份 GitHub ZIP 不是服务器备份。

| 数据 / 配置 | 默认位置 | 说明 |
|---|---|---|
| VLESS 参数及 Xray 配置 | `/etc/default/vless-reality`、`/usr/local/etc/xray/` | 含域名及私钥等敏感配置 |
| VLESS 节点、配额和每日统计 | `/var/lib/vless-reality/` | 含节点凭据、到期时间和计量状态 |
| WireGuard | `/etc/wireguard/` | 两台机器分别备份；含私钥 |
| portbw 配置、策略、安装记录 | `/etc/portbw/`、`/var/lib/portbw/`、`/var/lib/portbw-resident-release/` | 与已安装程序版本和内核规则一起核对 |
| SOCKS5 配置和账号状态 | `/etc/socks5-manager/`、`/var/lib/socks5-manager/` | 使用默认路径时适用，含账号密码 |
| 手工黑名单持久文件 | `/etc/jsh-cidrban.nft`、`/etc/systemd/system/jsh-cidrban.service` | 仅在安装过相应黑名单功能时存在 |

该表用于定位，不是完整恢复脚本；系统服务、程序文件和运行时规则也有依赖，不能只把某一个 `.env` 文件复制回来就当成恢复成功。快照回退会回到旧状态，可能丢失快照之后的节点、配置和流量记录；恢复后需重新检查配额和客户端连接。

<details>
<summary>受管理 portbw 的专用回滚命令（只适用于安装器识别的备份）</summary>

在维护窗口、确认当前发行版和管理记录匹配且备份有效后，才使用：

```bash
bash /root/portbw-install.sh rollback
```

安装器会拒绝未知来源、版本不匹配或备份无效等情况。首次安装后已有策略也可能拒绝回滚；不要删管理记录来绕过。出现 `ROLLBACK PASS` 后，仍要检查旧服务状态、`portbw report`、`portbw audit` 及实际连接。此命令不是 VLESS / SOCKS5 的通用回滚工具。

</details>

SOCKS5 日志迁移后的回退不应依靠重新运行旧安装器覆盖；需要时使用已验证的整机快照恢复方法。VLESS / WG-NAT 也没有在本手册提供一条适用于所有版本的通用降级命令。

</details>

<a id="release-notes"></a>

<details>
<summary>版本说明与看门狗运行规则</summary>

以下保留项目原有的版本说明。历史机器上的验收与 CPU 数据供参考，不代表当前服务器实测结果；实际部署以所下载的源码和本机检查为准。

<details>
<summary>VLESS V4（2026-10-16）</summary>

- **正式版发布提交**：[`5509924ddde3219d1f1660e582c281bc913034ea`](https://github.com/liucong552-art/jieshu/commit/5509924ddde3219d1f1660e582c281bc913034ea)，对应 [PR #2](https://github.com/liucong552-art/jieshu/pull/2)。
- **V4 Watchdog CPU 优化**：批量复用 nftables 状态查询，减少 25 个临时节点巡检时的重复开销；不会改变已有节点的端口、UUID、配额及到期时间。实际 CPU 节省取决于真实连接数和流量，不能由节点数量推算。
- **WG-NAT 握手时间修复**：Watchdog 判断握手有效期时使用检查当下的时间，避免将本轮巡检开始之后出现的新握手误判为“未来握手”。
- **发布范围**：本次 V4 主要更新 `vless.sh`（及测试和 CI）。`nat.sh`、`vpswg.sh`、`natjichang.sh` 等仍为各自已发布的文件，运行 `vless.sh` **不会**自动重新部署这些独立脚本。
- **主动握手探测**：NAT 出口机的 `nat.sh` 支持为各 Peer 发送定时数据探测包。该功能与 V4 的 Watchdog 握手时间修复不同；只更新 VPS 的 V4 不会替旧 Peer 自动创建 NAT 端探测定时器。
- **生产升级提示**：优先做 VPS 快照和节点状态备份；在维护窗口升级，并确认回滚方法。安装 V4 管理模块可能刷新 nftables 规则与 systemd 定时器；无需为安装 V4 而重新创建现有节点或重新运行 WG 的 `init/add`。服务商按一小时平均 CPU 考核时，三分钟测量只能参考，不能代替完整一小时统计。

</details>

<details>
<summary>通用 portbw（2026-10-18）</summary>

- 适用于 Debian/Ubuntu + systemd，不限 Helan；`portbw-install.sh` 与 `portbw.py` 是正式配套文件，从本仓库同一次下载取得配套文件后，**必须继续执行 `check` 和 `install` 才真正安装。** 仅下载、`bash -n` 或 `check` 不会创建 `portbw` 命令。
- 常驻 Watchdog 取代旧版每秒启动的 timer，双向独立自动触发；修复 TCP 上/下行 policer burst 过小导致的实际吞吐下降，并改进 100% 阈值附近的持续负载判定。**触发阈值仍为用户设置的 100%，85% 只用于判断样本持续性，不是把触发阈值降低到 85%。**
- 曾在 2 vCPU、13 端口的 `vm-172` 上测得 Watchdog 五分钟单核 CPU 由旧版至少 14.916% 降至新版 4.306%；实际效果与端口、流量及服务器环境有关。相同源码也在 Helan 验证了下载/上传触发及恢复。此版**不会自动给任何端口创建限速策略**。
- `check` 和 `verify` 为只读诊断；`install`、`upgrade`、`rollback` 会修改系统，请先做 VPS 快照。仅支持受本系列安装器管理、记录和源码 SHA 一致的旧版原地升级；从其他仓库安装的旧版请按[portbw 迁移说明](#portbw-install)操作。所有命令**直接通过单词执行，不询问 1/2/3/4 数字选项**。

</details>

### 本项目提供什么、不应自行假定什么

| 能力 | 使用边界 |
|---|---|
| 按端口管理 VLESS / SOCKS5 配额与来源 IP | 同一节点被多人共用时，按该节点合并计量；不能区分链接背后的真实人数 |
| 端口自动限速 | 需独立安装并给端口设置策略，不会因创建节点自动套用本文标准 |
| 审计与手工封禁 | 审计给线索，封禁要另行执行；没有在这份手册中实现自动判定滥用并自动处罚 |
| SOCKS5 代理 | TCP CONNECT；不支持 UDP ASSOCIATE，应用需支持带认证的 SOCKS5 |
| 日志历史与每日流量 | 从实际开始记录且仍保留的数据查询，不能恢复未记录或已清理历史 |
| 节点管理与升级 | 不提供在本文中未列明的续费、后台面板、自动备份或通用卸载 / 降级功能；不要猜子命令 |

### 看门狗与生产运行规则

- **临时节点看门狗：** 连续第三次恢复失败后启动持久化的 72 小时宽限；宽限期内恢复健康，原 UUID、端口、到期时间不变，并取消倒计时。
- **宽限届满：** 最终重试依旧失败就按规则删除临时节点，即使当时 NAT 出口整体不可达也不豁免。自然到期节点按正常到期规则清理。
- **V4 CPU 批量优化与 WG 握手时间修复：** 已包含在正式版 `vless.sh`。它们不会替 NAT 出口机执行 `probe-enable`，也不保证把所有断线都归因于 Watchdog；发现问题请先比对 WG 握手、路由、Xray 服务和 Watchdog 日志。
- **NAT 主动探测：** 新版 `nat.sh` 在新增/更新 Peer 成功后会*尝试*启用该 Peer 的 systemd 定时器，正常情况下约每 10 秒发送一次普通 WG 内网探测包（不是每 10 秒强制产生一次加密握手）。依赖 `ping`，且 timer 启动必须成功；安装文件、成功创建 Peer、实际启用 timer 是三个不同状态。删除 Peer 会尝试停用对应探测。以前就存在的旧 Peer，不会因只更新 GitHub 或执行 VPS 端 `vless.sh` 而自动开启。
- **Peer 身份与地址：** `hy2`、`helan` 等是 NAT 管理员自行取的名称，**不能**单凭名字判断是哪台 VPS。启用探测前应核对 `/etc/wireguard/wg-exit-peers.d/<name>.peer` 的 `PublicKey`/`AllowedIPs`，与目标 VPS 的 `wg show wg-nat` 相匹配；避免把探测发给错误的 Peer。
- **生产 NAT：** `nat.sh init/add/del` 均可能重启整条 WG 接口，影响其他 VPS；必须备份、安排维护窗口并确认回滚方法，不可当作无中断热更新。

---

请仅在自己拥有或获得授权的服务器和网络环境中使用，并遵守所在地法律、服务商条款和网络使用规定。

</details>
