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
