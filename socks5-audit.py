#!/usr/bin/env python3
"""Read-only per-port 3proxy access audit (journalctl), Beijing-time display.

3proxy emits a record when a connection is logged (typically at completion);
these are *not* guaranteed to be the original connection start times.
"""
from __future__ import annotations

import collections
import datetime as dt
import ipaddress
import re
import subprocess
from zoneinfo import ZoneInfo

BJ = ZoneInfo("Asia/Shanghai")
UTC = dt.timezone.utc
DOMAIN = re.compile(r"(?i)^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?$")
MARKER = "S5AUDIT"
MAX_DAYS = 90


def parse_record(line: str, start: int, end: int):
    # logformat: G%t S5AUDIT %E %C %c %n %R %r %I %O
    fields = line.strip().split()
    if len(fields) != 10 or fields[1] != MARKER:
        return None
    try:
        stamp = int(fields[0])
        if not (start <= stamp <= end):
            return None
        err = int(fields[2])
        client = ipaddress.ip_address(fields[3])
        client_port = int(fields[4])
        remote = ipaddress.ip_address(fields[6])
        remote_port = int(fields[7])
        incoming, outgoing = int(fields[8]), int(fields[9])
        if not (0 <= client_port <= 65535 and 0 <= remote_port <= 65535):
            return None
        if min(incoming, outgoing) < 0:
            return None
    except (ValueError, OverflowError):
        return None
    # Ignore local manager's localhost authentication/ACL probes in the report.
    if client.is_loopback or client.is_unspecified:
        return None
    name = fields[5].lower().rstrip(".")
    # 3proxy may log '-' or an IP in %n when no domain was sent by client.
    domain = name if DOMAIN.fullmatch(name) else None
    return stamp, err, str(client), domain, str(remote), remote_port


def summarize(lines, start: int, end: int):
    domains = collections.Counter()
    clients = collections.Counter()
    first = {}
    last = {}
    minutes = collections.defaultdict(set)
    events = 0
    invalid = 0
    failed = 0
    for line in lines:
        if MARKER not in line:
            continue
        record = parse_record(line, start, end)
        if record is None:
            invalid += 1
            continue
        stamp, err, client, domain, _remote, _port = record
        events += 1
        # "success" means 3proxy's request result code is 0.
        if err != 0:
            failed += 1
            continue
        if domain:
            domains[domain] += 1
        clients[client] += 1
        first[client] = min(stamp, first.get(client, stamp))
        last[client] = max(stamp, last.get(client, stamp))
        minute = dt.datetime.fromtimestamp(stamp, BJ).strftime("%Y-%m-%d %H:%M")
        minutes[minute].add(client)
    return domains, clients, first, last, minutes, events, invalid, failed


def peer_ip(endpoint):
    # ss peer fields may be IPv4:port or [IPv6]:port.
    if endpoint.startswith("["):
        end = endpoint.find("]")
        value = endpoint[1:end] if end > 0 else ""
    else:
        value = endpoint.rsplit(":", 1)[0]
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        return None


def live_connections(port: int):
    result = subprocess.run(
        ["ss", "-Htn", "state", "established", f"( sport = :{port} )"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, timeout=15, check=False,
    )
    if result.returncode:
        raise RuntimeError("ss 查询失败: " + result.stderr.strip()[:250])
    ips = collections.Counter()
    for line in result.stdout.splitlines():
        cols = line.split()
        # Last column is the peer address with no -p/-e options enabled.
        if len(cols) < 4:
            continue
        addr = peer_ip(cols[-1])
        if addr:
            ips[addr] += 1
    return ips


def bj_time(stamp):
    return dt.datetime.fromtimestamp(stamp, BJ).strftime("%Y-%m-%d %H:%M:%S")


def display(port: int, days: int, unit: str, *, journal_lines=None, ss_snapshot=None):
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError("PORT 必须是有效数字端口")
    if type(days) is not int or not 1 <= days <= MAX_DAYS:
        raise ValueError(f"DAYS 必须是 1～{MAX_DAYS} 的整数")
    if not re.fullmatch(r"socks5-@[A-Za-z0-9][A-Za-z0-9_.-]{0,47}\.service", unit):
        raise ValueError("非法 SOCKS5 service")
    end = int(dt.datetime.now(UTC).timestamp())
    start = end - days * 86400
    if journal_lines is None:
        since = dt.datetime.fromtimestamp(start, UTC).strftime("%Y-%m-%d %H:%M:%S")
        # Stream only matching access records rather than buffering a whole
        # journal query in the Python process (important on busy machines).
        args = ["journalctl", "-u", unit, "--since", since, "--grep", MARKER,
                "-o", "cat", "--no-pager", "--quiet"]
        with subprocess.Popen(
            args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            env={"TZ": "UTC", "PATH": "/usr/sbin:/usr/bin:/sbin:/bin"},
        ) as process:
            try:
                stats = summarize(process.stdout, start, end)
                status = process.wait(timeout=120)
            except Exception:
                process.kill()
                process.wait()
                raise
            if status:
                raise RuntimeError("journalctl 查询失败: " + process.stderr.read().strip()[:250])
    else:
        stats = summarize(journal_lines, start, end)
    domains, clients, first, last, minutes, events, invalid, failed = stats
    print("=" * 64)
    print(f"SOCKS5 端口 {port} | 过去 {days} 天 | 结果按北京时间展示")
    print("=" * 64)
    print("【1 / 4 网站访问排行：最多前 20 名】")
    if domains:
        for i, (name, n) in enumerate(sorted(domains.items(), key=lambda x: (-x[1], x[0]))[:20], 1):
            print(f"{i:2d}. {name:<40s} {n} 次连接")
    else:
        print("暂无可识别的网站域名记录")
    print("\n【2 / 4 来源 IP 历史：最多前 20 名】")
    if clients:
        for i, (ip, n) in enumerate(sorted(clients.items(), key=lambda x: (-x[1], x[0]))[:20], 1):
            print(f"{i:2d}. 来源 IP：{ip} | {n} 次连接")
            print(f"    首次：{bj_time(first[ip])}  最近：{bj_time(last[ip])}")
    else:
        print("暂无来源 IP 历史记录")
    print("\n【3 / 4 同一分钟出现多个 IP 的历史：最新 30 条】")
    matches = [(minute, ips) for minute, ips in minutes.items() if len(ips) >= 2]
    for i, (minute, ips) in enumerate(sorted(matches, key=lambda x: x[0], reverse=True)[:30], 1):
        print(f"{i:2d}. {minute}：出现 {len(ips)} 个不同来源 IP")
        print("    " + "、".join(sorted(ips)))
    if not matches:
        print("暂无同一分钟多个 IP 的访问记录")
    print("\n【4 / 4 当前已建立 TCP 连接的来源 IP】")
    ips = live_connections(port) if ss_snapshot is None else ss_snapshot
    for i, (ip, n) in enumerate(sorted(ips.items(), key=lambda x: (-x[1], x[0])), 1):
        print(f"{i:2d}. {ip}：{n} 条连接")
    print(f"目前不同来源 IP：{len(ips)} 个；已建立 TCP 连接：{sum(ips.values())} 条")
    print("\n提示：网站访问次数 = 已记入日志的成功代理连接次数，不是打开网页次数。")
    print("3proxy 通常在连接结束时写入记录；同一分钟有多个 IP 不等于确实同时在线。")
    print("只有客户端请求使用域名时，才能识别网站域名；IP 请求无法反推域名。")
    print("历史取决于开启日志的时间、journald 保存期限与限流；此前未记录的历史无法补查。")
    print(f"读取到访问记录：{events} 条（成功 {events-failed}、错误码非零 {failed}、不完整 {invalid}）。")
    if events == 0:
        print("警告：指定时间段没有可识别的 S5AUDIT 记录；不能据此判断无人使用或没有滥用。")


if __name__ == "__main__":
    raise SystemExit("请使用 socks5 access <端口> [天数]")
