# Helan: validated IPv4/IPv6 UDP and TCP/UDP shared ingress (2026-10-17)

Operator-run test directory: `/tmp/portbw-cpu-QSQkWgn4/results`.

Pinned harness: `484df0a2ae43667c5e818047eb7d2e3c01faa834`; version `20261017-shared-police-pressure-v4`. Both source hashes passed verification.

- A: original main/portbw.py SHA256 `69058c8069e78d902c4814e1300c5aa38e2b91340f936cdb9cdc09a14936f359`.
- B: feature candidate SHA256 `52eaa233f831236973dff6b43d8f320659b29226939ee5ba132d2b9cf31eebfb`.
- Three shared **ingress** policer scenarios passed in separate real nft+tc network namespaces for both A and B.
- Tests use IPv6 **inside** temporary veth namespaces; they neither need nor imply publicly routed IPv6 on Helan.
- Duration 18 seconds per traffic scenario; throughput is application payload, not link-level accounting.

| Scenario | A delivered Mbps | B delivered Mbps | A overlimits | B overlimits |
|---|---:|---:|---:|---:|
| IPv4 UDP + IPv6 UDP on port 43000 | 1.000 | 0.998 | 9375 | 9379 |
| IPv4 TCP + UDP on port 43000 | 0.980 | 1.024 | 120 | 65 |
| IPv6 TCP + UDP on port 43000 | 0.966 | 0.930 | 76 | 88 |

Unpoliced control port 43080: TCP IPv4 **3.000 Mbps**, TCP IPv6 **3.000 Mbps**, combined UDP IPv4+IPv6 **5.999–6.000 Mbps**.

Actual TCP and UDP both participated (no trivial TCP starvation). The four flowers per direction use a single shared action; tc police overlimits/drops were observed to increase in all six subscenarios. A/B both logged `SEMANTIC_PASS`.

This demonstrates the **tested ingress shared-police semantics**, but not production-public IPv6, standalone egress enforcement, 1-hour CPU stability, upgrade/rollback, or byte-exact QoS error tolerances. TCP retransmissions, kernel burst allowance, and application payload sampling explain small 0.93–1.024 Mbps variations without alone establishing a correctness defect.

## Next tests added in feature branch

- Dedicated one-way, source-port-matched **egress** IPv4/IPv6 UDP traffic generator, sharing the outbound tc police action; separate unpoliced output test to disprove generator starvation.
- CPU runner's `--order BA` option to reverse the traditional A→B measurement order.
- Helan launcher's `SKIP_EXTRA_BASELINE=1` for long A/B runs without duplicated baseline/profiler overhead.
- No changes to original GitHub main or MEGABOX.

New tests are not considered passed until Helan executes them, even if GitHub CI reports success.
