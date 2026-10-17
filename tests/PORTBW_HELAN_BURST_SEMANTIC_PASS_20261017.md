# Helan fixed-burst four-suite semantic acceptance — 2026-10-17

**User-run real kernel isolated netns**, result directory `/tmp/portbw-cpu-XYa2yNmb/results`. Actual installed Helan `portbw` was not upgraded. Main and MEGABOX unchanged.

Candidate SHA256: `f0ebe551e8c0345c045a558b39a8b13523b2be8195255c67db13eec3eff5dc1a`. Harness AST gate passed: corrected TCP backpressure, real tc shared action counters.

| Suite | Outcome | Key observations |
|---|---|---|
| aggregate | PASS | IPv4+IPv6 UDP demand 6 Mbps, delivered 1.001 Mbps, 9374 drops/overlimits; IPv4 TCP+UDP delivered 0.947 Mbps, 56 drops, both transports active; IPv6 TCP+UDP delivered 0.957 Mbps, 63 drops, both active |
| outbound | PASS | Unregulated 6.000 Mbps; regulated dual-stack UDP 0.989 Mbps, 9394 shared police drops/overlimits |
| faults | PASS | Missing owned rule repaired; foreign rule preserved and fail-closed; malformed sibling isolated |
| lifecycle | PASS | Both up/down transition from 1 to 0.5 Mbps under traffic, both restored to 1 Mbps, after cooldown returned to monitor; 37 ticks |

All four emitted `SEMANTIC_PASS` with the exact same candidate source SHA; no traceback in the supplied run.

Previous isolated 20/40 Mbps true TCP receiver-goodput test on same candidate: 19.953/39.214 Mbps with both nft and tc present; corresponding original CPU candidate gave 9.569/20.081 Mbps.

**Not yet passed**: managed live-host upgrade/rollback of the candidate and systemd watchdog with nonempty saved policies, public-WAN VLESS RTT tests, and sub-second burst/overshoot tolerance. An installer passing CI without these checks is not production approval. Do not modify `main` or MEGABOX.