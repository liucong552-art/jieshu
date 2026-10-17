# Helan portbw A/B evidence — 2026-10-17

Source: operator-provided Helan terminal transcript; benchmark scripts under `tests/`. Values below are **unprofiled Python + child-process single-core CPU**, not whole-VPS CPU.

- A: immutable main `portbw.py`, SHA256 `69058c8069e78d902c4814e1300c5aa38e2b91340f936cdb9cdc09a14936f359`.
- B: indexed feature candidate `portbw.py`, SHA256 `52eaa233f831236973dff6b43d8f320659b29226939ee5ba132d2b9cf31eebfb`.
- Debian 13.5 Helan, 1 vCPU, nft/tc in throwaway network namespaces, 90 rounds for each A/B trial. The host simultaneously runs VLESS and WG, hence whole-system CPU cannot be assigned to portbw.
- All trials completed and rule audits passed before/after each.
- **A always ran before B:** this is useful initial evidence but not a randomized or counterbalanced order.

| Scenario | A CPU % | B CPU % | Lower CPU % | A mean round ms | B mean round ms |
|---|---:|---:|---:|---:|---:|
| Static idle 1 port | 2.601 | 2.132 | 18.03 | 30.709 | 26.176 |
| Static idle 10 ports | 5.479 | 3.211 | 41.39 | 63.293 | 36.815 |
| Static idle 25 ports | 16.460 | 5.163 | 68.63 | 207.609 | 57.543 |
| Static 1 port, IPv4 UDP 3 Mbps offered | 2.688 | 2.142 | 20.31 | 35.026 | 28.871 |
| Static 10 ports, IPv4 UDP 3 Mbps offered | 5.719 | 3.400 | 40.55 | 75.118 | 42.519 |
| Auto 1 port, IPv4 UDP 3 Mbps offered | 3.116 | 2.655 | 14.79 | 40.732 | 35.374 |
| Auto 10 ports, IPv4 UDP 3 Mbps offered | 6.341 | 3.901 | 38.48 | 78.139 | 48.444 |

## Observed traffic and state transitions

- Static inbound IPv4 UDP: offered ~3 Mbps, delivered ~0.983 Mbps in A and B (1 Mbps configured).
- Auto inbound IPv4 UDP: offered ~3 Mbps, delivered ~0.531–0.532 Mbps averaged over a 90-second run in A and B. The automated logs for both show `43000 up/down: 自动降速 0.5 Mbps，滚动保护 20 秒`.
- IPv6 namespace was available, but no **IPv6 payload traffic** was tested in these runs.
- Existing observations do **not** establish TCP behavior, download-direction enforcement in isolation, TCP+UDP aggregate throughput under simultaneous load, IPv4/IPv6 aggregation, auto recovery/cooldown, fault injection, systemd watchdog, installer rollback, or sustained 1-hour behavior.
- CPU measured by the probe excludes traffic generator and kernel-per-packet policing CPU. Whole-machine samples mix unrelated host work.
- A/B limit rates are validated at a gross throughput level only, not a rigorous jitter/error-bar performance SLA.

## New feature-branch test tools (not yet real-kernel validated)

As follow-up, the test generator and runner now accept `TEST_PROTO=udp|tcp` and `TEST_FAMILY=ipv4|ipv6`. The runner's CPU comparison still uses the normal unprofiled path; the existing independent A cProfile pass remains available. GitHub CI confirms syntax and mocked regressions only. **A passing CI result does not imply true TCP/IPv6 compliance.**

### Proposed actual Helan next validations

```bash
curl -fsSL 'https://raw.githubusercontent.com/liucong552-art/jieshu/opt/portbw-cpu-snapshot-index-20261016/tests/portbw_helan_ab.sh' -o /tmp/portbw-helan-ab.sh
TEST_SECONDS=60 TEST_SIZES=1,10 TEST_TRAFFIC=udp TEST_PROTO=tcp TEST_FAMILY=ipv4 RUN_AB_AFTER_BASELINE=1 bash /tmp/portbw-helan-ab.sh
TEST_SECONDS=60 TEST_SIZES=1,10 TEST_TRAFFIC=udp TEST_PROTO=udp TEST_FAMILY=ipv6 RUN_AB_AFTER_BASELINE=1 bash /tmp/portbw-helan-ab.sh
```

The last trial is **not automatically sufficient** for true bidirectional/dual-protocol aggregate or lifecycle correctness. Those need distinct active concurrent probes and recovery injection before production consideration.
