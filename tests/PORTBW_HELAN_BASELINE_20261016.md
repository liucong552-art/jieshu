# Helan portbw original-baseline evidence (2026-10-16)

## Source and safety boundary

- **A**: immutable `main/portbw.py`, SHA256 `69058c8069e78d902c4814e1300c5aa38e2b91340f936cdb9cdc09a14936f359`.
- **B**: experimental feature branch only. No evidence of B's Helan CPU gain yet.
- Host: Helan, Debian 13.5, kernel 6.12.88+deb13-amd64, 1 vCPU; VLESS and WG services continue in the host. Rules were placed in a separate netns for baseline measurements.
- Mode: idle static policies, two directions, real nft+tc; 1 and 10 ports; 60 measurement rounds each.
- Data source: operator-pasted Helan command outputs and 30-second original-code cProfile traces. Not inferred from whole-VPS utilization.

## Original A: CPU and command counts

| Measurement | 1 port | 10 ports |
|---|---:|---:|
| Python process one-core CPU | 0.995% | 7.619% |
| nft/tc subprocesses one-core CPU | 2.164% | 3.119% |
| Python + child one-core CPU | **3.159%** | **10.738%** |
| Whole VPS CPU (includes unrelated processes) | 12.586% | 18.734% |
| Mean round wall (ms) | 41.458 | 123.039 |
| P95 round wall (ms) | 67.602 | 237.830 |
| nft list table calls / 60 ticks | 120 | 120 |
| tc qdisc calls / 60 ticks | 60 | 60 |
| tc JSON filter calls / 60 ticks | 120 | 120 |
| tc text stats calls / 60 ticks | 120 | 120 |

CPU percent represents **elapsed wall-clock denominator**, not a percent of the cProfile cumulative time. Whole VPS CPU includes VLESS, WG and all host processes; it is not portbw service CPU. No packet load in this run, so per-packet kernel policing overhead is unmeasured. 1-minute baselines are not 1-hour production compliance results.

## Original A: cProfile evidence, 10 static ports, 30 seconds

| Function | Calls | Cumulative profile time (s) |
|---|---:|---:|
| `reconcile` | 30 | 4.210 |
| `tc_ok` | 300 | 1.975 |
| `_used_tc_prefs` | 2,400 | 1.193 |
| `tc_rate_is_ok` | 2,400 | 0.556 |
| `nft_ok` | 300 | 0.413 |
| `_check_owned_table` | 360 | 0.335 |
| `_tc_filter_body` | 2,400 | 0.333 |
| `_rule_exact` | 11,700 | 0.220 |
| `tc_find` | 2,400 | 0.182 |
| `_tc_slot_owned` | 98,400 | 0.541 |

Do not add cumulative function times because nested calls overlap. cProfile adds instrumentation overhead and includes waiting: `time.sleep` appeared as 25.893 s in the 30-s profile, **not** as 25.893 s of consumed CPU. The highest per-port growth is in Python rule scanning; prioritize shared indexes instead of changing the 1-second sampling cadence.

## Implemented in feature branch (not production-tested)

1. Healthy `ensure_base`: one nft table snapshot after strict base checking, still re-snapshot after repair.
2. `reconcile`: build trusted per-round nft rule, object, limit, order and generation indexes.
3. `tc_snapshot`: build per-round pref groups and keyed text-filter blocks; keep strict per-slot action/rate checking.
4. `traffic_sample`: reuse generation handles.
5. Unit tests: nft healthy/missing/repair, strict foreign object failure, tc duplicated/foreign/missing slots, text-index equivalence, nft indexed/normal validation equivalence.
6. Benchmark corrections: CPU A/B runs **without cProfile**; separate A diagnostic pass; parseable per-trial CPU result markers even with auto-transition logs.

No validated Helan B CPU estimate is available yet. CI validates source and mocks; **no kernel bandwidth semantics or install/rollback claims follow from it**.

## Subsequent acceptance criteria

- First: A/B same Helan, same 1/10/25 policy sets, same direction, same idle/loaded traffic, same timing. Use repeated reversed-order runs to detect drift.
- Record process CPU, child CPU, whole VPS CPU, p95/p99 round time, commands per round, memory and failures.
- Then real IPv4/IPv6 TCP/UDP shared policing, both directions, auto trigger/hold/cooldown/recovery and injection of missing/foreign/duplicated rules.
- Finally repeated 3-minute and 1-hour comparable workload A/B. No modification of `main`, no MEGABOX rollout without explicit permission.

### Helan command (feature-branch test loader)

```bash
curl -fsSL 'https://raw.githubusercontent.com/liucong552-art/jieshu/opt/portbw-cpu-snapshot-index-20261016/tests/portbw_helan_ab.sh' -o /tmp/portbw-helan-ab.sh &&
TEST_SECONDS=60 TEST_SIZES=1,10 RUN_AB_AFTER_BASELINE=1 bash /tmp/portbw-helan-ab.sh
```

The script downloads the unchanged main source, pins and verifies A/B SHA256, uses isolated network namespaces and reports JSON files under `/tmp/portbw-cpu-*/results`. It does not invoke the managed installer or host-level network operations. Tests may still encounter real kernel/environment errors and must not be treated as passed until output is reviewed.
