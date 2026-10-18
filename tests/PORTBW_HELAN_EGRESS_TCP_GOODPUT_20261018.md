# Helan TCP download receiver-goodput A/B — 2026-10-18

Reported by user from HELAN isolated disposable network namespaces; not a production or public-WAN test.

## Real receiver measurements, 20-second runs

| tc egress burst mode | Configured 5 Mbps | Configured 20 Mbps | Configured 40 Mbps |
|---|---:|---:|---:|
| Existing 0.1-second small burst | 0.315 | 7.586 | 17.645 |
| Tested bounded ~0.5-second burst | **4.811** | **19.138** | **37.482** |
| Fixed 1 MiB burst | 4.791 | 19.108 | 37.492 |

Unlimited control in the original run: 6217.481 Mbps on local veth. Original 40 Mbps test had 3049 tc drops/overlimits, 20 Mbps had 1535, 5 Mbps had 223. These are receiver goodput measurements, not action-seen counter rates.

Data show a bounded half-second egress tc burst almost reaches the configured target; fixed 1 MiB confers no meaningful extra TCP goodput. As with ingress, the byte-rate stays unchanged while brief packet trains are tolerated.

The user's `half_second` and `one_meg` follow-up printed two `EGRESS_TCP_SUMMARY` records and a `RESULT_DIR`. Result SHA256 was `f0ebe551e8c0345c045a558b39a8b13523b2be8195255c67db13eec3eff5dc1a` (the previous upload-only candidate with temporary in-netns module override).

## Candidate code

This branch modifies only the **tc down burst allowance** to `max(64,min(1024,(rate+2047)//2048))` KiB, preserving prior ingress fix. No other policy rates, nft rules or service configuration have been changed.

**Important remaining gates:** run true Helan kernel tests on this exact new file hash, egress+ingress shared TCP/UDP v4/v6 tests, auto lifecycle and Watchdog, public VLESS download if desired, and verify safe installer/rollback. Old `portbw-onekey.sh` intentionally remains pinned to the older upload-only candidate, so this new build is NOT ready to install. Keep GitHub main, original CPU branch, and MEGABOX untouched.
