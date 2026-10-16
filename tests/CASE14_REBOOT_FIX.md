# Helan security regression CASE 14 fix (tester, not V4 runtime)

The Oct 16 2026 Helan reboot logs show:
- 04:52:14 UTC managed restore finished
- 04:52:15 UTC CASE 14 recorded a failure ("not listening")
- 04:52:16 UTC temporary service started
- 04:52:21 UTC Xray finished startup

So the original CASE 14 single-shot TCP probe was too early. There is no evidence in
these logs that V4 runtime failed to restore the listener. The original FAIL remains
historical evidence; it must not be silently reclassified as PASS.

This patch applies to the **previous onepass test package's** suite.py, not the
GitHub V4 installer or any production system. A future re-run waits up to 150s,
requires service-active + TCP listener, verifies persisted quota consistency,
real WG health and authenticated VLESS/REALITY traffic after reboot. Timeout
saves journal evidence instead of passing.

Test locally by copying the original suite.py and applying:
    patch -p1 < helan-case14-reboot-readiness.patch
    python3 -m py_compile suite.py
    python3 -m unittest -v test_postboot_wait.py

Do not patch/restart a running one-hour measurement. Finish CASE 15 first.
Original V4 PR stays a draft until a new verified CASE 14 reboot run, the
one-hour CPU window, final health and other merge blockers all pass.

## Independent CASE 14 rerun: FAILED (2026-10-16 ~06:00 UTC)

- A different boot_id confirmed a genuine reboot.
- The disposable `svpersist` unit was active before its listener was ready at 06:00:29 UTC; TCP listening succeeded by 06:00:36. This confirms the original too-early listener probe was a tester issue.
- At 06:00:53 the **original 25-node invariant failed with 32 unit/listener errors predominantly on the 16 WG-NAT nodes**. The test stopped before verifying persisted quota and authenticated postboot VLESS traffic. Therefore CASE 14 remains **FAIL**; this rerun does not validate quota persistence.
- The temporary `svpersist` node was cleaned successfully.
- Code audit: the V4 watchdog intentionally fail-closes NAT listeners when the WG handshake is absent/stale; the watchdog timer first fires at OnBootSec=90s, while the rerun checked roughly within the first minute of the boot. A code comment documents that a cold WG handshake can sometimes take up to ~134s. This is a **plausible cause, not yet confirmed**. Check the WG handshake age, heartbeat timer, listener state, and watchdog logs from that boot to distinguish expected transient fail-closed from failure to auto-recover.

**No runtime fix is validated. Do not mark this case as PASS, merge PR #2, or deploy to MEGABOX until cold-boot WG/NAT recovery and quota persistence are fully re-tested.**


## Independent CASE 14 V2 rerun: PASS (2026-10-16 ~06:15 UTC)

Final report was supplied from Helan's `/root/helan_case14_rerun_v2_result/REPORT.md` and logs:

- Boot ID changed from `85f18434-8b0a-49cb-afb0-c4e0f8969c14` to `6eba4778-03dc-42fc-920f-74465820f2f2`, proving a real reboot.
- Disposable `svpersist` service active before socket was ready at 06:14:36; TCP ready 06:14:42. Test does not incorrectly fail during this startup interval.
- Persisted quota before reboot: **77,841 bytes**; after reboot before traffic: **77,841 bytes**; after authenticated VLESS/REALITY traffic: **93,140 bytes**. There was no measured rollback.
- At 06:14:42, WG had no fresh handshake and the suite correctly waited without declaring NAT healthy.
- At 06:15:16, WG handshake was fresh but some NAT services/listeners were still recovering. At 06:15:32, **all 25 baseline nodes and marked WG egress were healthy**.
- Recovery readiness wait: **49.9 seconds** after the temporary listener's readiness, within the bounded 300-second WG/NAT recovery gate. The existing 180-second handshake freshness threshold was not relaxed.
- Final verification of nft guards, quota monotonicity, actual authenticated VLESS transfer and WG/25-node health: **PASS** at 06:15:38.
- Disposable node cleanup: **PASS**, completed at 06:15:41. `helan-case14-rerun-v2.service` ended `inactive` rather than failed.

**Historical record:** the original one-pass suite ended **17 PASS, 1 FAIL** (CASE 14); the first independent rerun also FAILed prematurely while cold-boot WG/NAT was still recovering. These failures are not deleted/reclassified. The separate V2 test supplies successful missing recovery evidence after correcting the test readiness gates.

**Other Helan result:** prior 3600-second passive CPU sampling completed at **11.629% whole-host average on one vCPU**; final 25-node health CASE 16 also PASSed.

**Release boundary:** this validates the specified Helan behavior only. It does not guarantee external internet-client throughput, the 72-hour duration without simulated metadata, long-term production conditions, or the 2-vCPU MEGABOX provider's rolling single-core 30%-hour constraint. The V4 PR remains a draft; no main branch or MEGABOX change.
