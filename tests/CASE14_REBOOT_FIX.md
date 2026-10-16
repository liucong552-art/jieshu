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
