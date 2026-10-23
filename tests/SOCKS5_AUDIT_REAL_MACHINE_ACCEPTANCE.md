# SOCKS5 access-audit staging branch: real-machine gate

Branch: feature/socks5-access-audit. **Do not merge to main until tests on real Debian hosts pass**. A mock or GitHub Actions job does not qualify.

## Contract

- Fresh nodes always emit 3proxy S5AUDIT connection records on stdout; each node has a separate systemd service and journal.
- Existing managed nodes are migrated on staging installer update. Each active node with a changed configuration is restarted once. This is NOT a zero-downtime upgrade.
- Preserve passwords, expiry, port, IP guard, quotas, portbw and all WG/VLESS state.
- To display four sections in Beijing time: PORT=40007; DAYS=7; socks5 access "$PORT" "$DAYS".
- Legacy socks5 audit PORT remains a service and protection health command.
- Domain ranking covers only successful (error code 0) requests with a hostname. Direct IP connections have no recoverable domain. 3proxy normally writes a connection record at completion, NOT at the start.
- Historical window is capped at 90 days; actual retention and rate-limiting are controlled by the existing journald setup. Do not pretend missing logs mean no abuse. This branch does not change global journald settings.
- Logs contain sensitive client IPs and destinations; avoid sharing raw logs, credentials or link URIs.
- Main installer is NOT a safe rollback mechanism after migration: restore a full machine snapshot if necessary.

## Offline checks (not real-machine acceptance)

    python3 -m py_compile socks5.py socks5-traffic.py socks5-audit.py
    bash -n socks5-install.sh
    python3 -m unittest discover -s tests -p test_socks5_access_audit.py -v

## Required old-machine acceptance (dedicated Debian 12 test VM / host only)

1. Take a full snapshot. Prepare at least two main-version SOCKS5 accounts with distinct ports, credentials, sticky IP policy, and nonzero traffic. Save redacted outputs of socks5 list, quota, ip-show, nft guard, portbw rules, journalctl, and client connectivity.
2. Confirm legacy .cfg contains no log directive and direct connections work with existing credentials.
3. Run this branch installer with an explicit source ref:

    S5_SOURCE_REF=feature/socks5-access-audit bash <(curl -fsSL https://raw.githubusercontent.com/liucong552-art/jieshu/feature/socks5-access-audit/socks5-install.sh) update

4. Observe planned connection drops while each legacy active service is restarted, then ensure ALL original accounts are active and listening, old credentials still work, IP/ACL/quota/expiry/limits are unchanged apart from legitimate test traffic.
5. Test authentication with correct/incorrect password; blocked private address and SMTP ports; BIND/UDPASSOC blocked; outbound route remains correct.
6. From an *external* SOCKS client, CONNECT using a hostname, close the connection, then find its S5AUDIT line under the correct systemd unit. Check client IP, target hostname, target port, error code and timestamp, without exposing credentials.
7. For each account verify all four report sections, no cross-account records, Beijing-time aggregation, per-minute two-client records, direct-IP-only requests, denied attempts, and active TCP connection accounting.
8. Repeat update: it must not restart accounts or reset quotas when already migrated.
9. Confirm watchdog, quota persistence, IP sticky, portbw throttling, expiry cleanup, and disk usage.
10. Reboot the test host. Confirm all active nodes restart and continue producing access logs. Check whether journald is actually persistent and retention is sufficient.
11. Rehearse failed-upgrade recovery from snapshot; document exact steps and timestamps.

## Required fresh-machine acceptance (different clean Debian 12 VM / host)

Take a snapshot; then install using the staging branch:

    AUTO_DEPS=1 S5_SOURCE_REF=feature/socks5-access-audit bash <(curl -fsSL https://raw.githubusercontent.com/liucong552-art/jieshu/feature/socks5-access-audit/socks5-install.sh) install

Create two test nodes:

    D=86400 IP_LIMIT=1 IP_STICKY_SECONDS=60 PQ_GIB=2 PORT=40007 socks5 add
    D=86400 IP_LIMIT=2 IP_STICKY_SECONDS=60 PQ_GIB=2 PORT=40008 socks5 add

Repeat all access/ACL/traffic/journal isolation/reboot tests from above.

## Gate to main

Record real OS/kernel, 3proxy package and version, machine type, test time, masked evidence, tester and pass/fail for every item. Until both scenarios pass, this branch is **NOT RELEASE READY**. No merge or deployment to production is approved by this document.
