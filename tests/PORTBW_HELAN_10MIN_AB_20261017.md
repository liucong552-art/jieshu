# Helan 10-minute CPU A/B: 25 static port policies

**Date:** 2026-10-17; source: user-provided original Helan terminal output (run at \`/tmp/portbw-cpu-YnUkkq3W/results\`).

## Precisely identified code

- Original A: \`main/portbw.py\`, SHA256 \`69058c8069e78d902c4814e1300c5aa38e2b91340f936cdb9cdc09a14936f359\`.
- Optimized B: feature candidate \`portbw.py\`, SHA256 \`52eaa233f831236973dff6b43d8f320659b29226939ee5ba132d2b9cf31eebfb\`.
- Both hashes validated on Helan. Main remained unchanged at commit \`41723a28129682421e13a62112111a1967f28f89\`.
- Debian 13, single vCPU; independent disposable network namespaces, genuine nft+tc rule audit.
- 25 static ports, no test traffic, 1-second sampling, **600 completed rounds per candidate**, reversed order B then A, \`SKIP_EXTRA_BASELINE=1\` (no cProfile overhead). 20 minutes total for both candidates.

## Measurements

| Metric | Original A | Optimized B | Reduction |
|---|---:|---:|---:|
| Python + nft/tc subprocess CPU, one-core equivalent | **16.157%** | **5.278%** | **67.3%** |
| Python process CPU | 11.852% | 2.263% | 80.9% |
| nft/tc subprocess CPU (calculated by subtraction) | 4.305% | 3.015% | 30.0% |
| Average reconciliation wall latency | 184.030 ms | 61.325 ms | 66.7% |
| p95 reconciliation latency | 333.970 ms | 106.545 ms | 68.1% |
| p99 reconciliation latency | 409.670 ms | 125.426 ms | 69.4% |
| Maximum round wall latency | 562.837 ms | 175.366 ms | — |
| nft list table reads per 600 rounds | 1,200 | 600 | 50% |
| tc JSON filter reads | 1,200 | 1,200 | none |
| tc textual stats reads | 1,200 | 1,200 | none |
| tc qdisc reads | 600 | 600 | none |
| Reconciliation rounds exceeding one second | 0 | 0 | — |

### Five-minute stability measurements

| Segment | Original A CPU | Optimized B CPU | A Python | B Python | A p95 latency | B p95 latency |
|---|---:|---:|---:|---:|---:|---:|
| Rounds 1–300 | 16.233% | 5.278% | 11.860% | 2.256% | 337.204 ms | 105.059 ms |
| Rounds 301–600 | 16.081% | 5.279% | 11.844% | 2.270% | 331.079 ms | 107.171 ms |

Neither version exceeded the 1-second round interval in either segment. The B CPU mean changed by only 0.001 percentage point between segments, so no obvious drift was visible over ten minutes.

## What these results establish

The CPU improvement is **real for the supervisor's idle reconciliation work** on the same Helan VPS, not calculated from unrelated whole-machine load. Previous independently measured runs found 25-port A/B ~68.6% improvement over 90s and ~66.8% improvement over 180s with the reverse order. This 600s reverse-order run is consistent.

The CPU measurement includes Python and child nft/tc commands, but excludes all kernel-per-packet work and any application traffic-generator CPU. No throughput was generated in this 10-minute experiment. Whole-machine CPU includes VLESS, WireGuard and other unrelated processes and must never be reported as the limiter's CPU. This trial is **not a 1-hour test** and does not need to become one; user explicitly set a 10-minute limit.

Other tests already separately demonstrated IPv4/IPv6 TCP+UDP ingress shared policing, IPv4+IPv6 outbound UDP sharing, automatic downshift and restoration, and foreign-object fail-closed handling. Production rollout and managed installer upgrade/rollback/systemd watchdog remain separate acceptance criteria.

## Remaining release gate

On **Helan only**, test clean main installation, a saved nonempty static policy, managed upgrade to the candidate, service watchdog and rule audit, explicit rollback to exact main SHA, and preservation of saved port policy. Do not touch GitHub main or MEGABOX. The installer operations modify Helan systemd and live nft/tc and must not be confused with isolated network-namespace CPU tests.

There is no request to run a 1-hour test; do not schedule or recommend one.
