# Helan upload TCP goodput: fixed 1 MiB ingress tc burst (2026-10-17)

## Provenance

User-provided original shell transcript from Helan. All throughput comparisons below ran in disposable `unshare --net` Linux network namespaces, not in the Helan host network namespace. Neither production VPS nor real Helan `40024` VLESS listener was touched. In particular, results are for local isolated TCP, not public Internet RTT.

- Original CPU optimized candidate: `portbw.py` SHA256 `52eaa233f831236973dff6b43d8f320659b29226939ee5ba132d2b9cf31eebfb`.
- TCP burst fix candidate (B): SHA256 `f0ebe551e8c0345c045a558b39a8b13523b2be8195255c67db13eec3eff5dc1a`.
- Fix code pinned for test to Git commit `48ac700dd734b7492d367342fb343eeaa99fc183`, with `tests/portbw_helan_burst_fix.sh`.
- Each measurement ran 24-second TCP transfer with a 4-second warmup, using receiver-measured steady Mbps, 0 ms injected network delay.

## Original defect reproduced

| Mode | Original A at 20 Mbit/s | Original B at 20 Mbit/s | Original A at 40 Mbit/s | Original B at 40 Mbit/s |
|---|---:|---:|---:|---:|
| nft + tc double police | 9.470 | 9.569 | 19.864 | 20.081 |
| tc only | 9.260 | 9.323 | 19.845 | 20.087 |
| nft only | 20.250 | 19.861 | 40.009 | 39.960 |
| nft + tc, forced 1 MiB tc burst | 19.850 | 20.099 | 39.337 | 39.725 |
| nft + tc, forced 4 MiB tc burst | 19.960 | 19.983 | 39.813 | 39.919 |

This isolates the underdelivery to **small tc ingress police burst allowance**, not a regression from CPU snapshot indexing and not a need to disable nft. The real bound remains a **per-port shared TCP+UDP/IPv4+IPv6 tc action**.

## Actual fixed source re-test, still with both policers enabled

| Configured rate | Fixed source B, both nft + tc | Fixed source B, nft only | Reached percentage of configured cap |
|---|---:|---:|---:|
| 20 Mbps | **19.953 Mbps** | 20.055 Mbps | **99.765%** |
| 40 Mbps | **39.214 Mbps** | 39.959 Mbps | **98.035%** |

- Unlimited local control: 7407.216 Mbps for both and 7796.847 Mbps for nft-only. These are disposable local veth results; they are not VPS Internet bandwidth.
- Fixed B both mode: 20-Mbps tc police `drops=652` and `overlimits=652`; 40-Mbps `drops=999` and `overlimits=999`.
- Both fixed-source scenarios completed; `RESULT_DIR=/tmp/portbw-cpu-zbmEbJdb/results`.
- No observed traceback in the final fixed-source run.
- The previously advertised candidate installer has **not** been promoted for this fix; the old source SHA guard intentionally rejects it.

## Fix policy and safety boundaries

The tentative code changes **only the tc ingress/up burst calculation**: `max(64, min(1024, ceil(rate_bytes_per_sec / 2048)))` KiB; this is a ~0.5-second allowance capped at 1 MiB. The tc egress/down burst remains the previous 0.1-second limited implementation, and the configured rate and nft policer remain unchanged.

A larger token bucket permits short interval bursts above the configured bit rate even when the sustained 24s average is correct; this is not evidence of sub-second strict shaping. **Do not claim rollout readiness from this TCP-only zero-RTT result**. Required next checks: real IPv4+IPv6 shared police under overload, TCP+UDP mixed participation, output direction unchanged, auto hold/cooldown/recovery, deliberate fault fail-closed behavior, and the separate installer SHA / rollback / systemd release gate. Public VLESS path with nonzero RTT also remains unverified. Production MEGABOX must never be touched; GitHub main and original CPU branch remain unchanged.
