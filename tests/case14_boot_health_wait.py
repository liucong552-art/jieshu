#!/usr/bin/env python3
"""Cold-boot readiness gate for Helan CASE14 tests, never a production service.

The watchdog is expected to fail-close NAT listeners until WG has a fresh
handshake, then restore them on a later scheduled sweep. A one-shot health
check immediately after reboot incorrectly reports this normal gap as a
permanent recovery failure. This helper never starts/stops any node.
"""
import time


class RecoveryTimeout(RuntimeError):
    pass


def has_fresh_handshake(wg_latest_handshakes, now, max_age_seconds=180):
    """Parse untrusted `wg show wg-nat latest-handshakes` text; fail closed."""
    for row in wg_latest_handshakes.splitlines():
        fields = row.split()
        if len(fields) != 2:
            continue
        try:
            epoch = int(fields[1])
        except ValueError:
            continue
        if epoch > 0 and now >= epoch and now - epoch <= max_age_seconds:
            return True
    return False


def await_coldboot_recovery(read_handshakes, validate_all_25_and_marked_egress,
                            timeout_seconds=300, poll_seconds=10,
                            epoch=time.time, monotonic=time.monotonic,
                            sleep=time.sleep, emit=print):
    """Require fresh WG handshake AND 25-node+marked-egress health.

    read_handshakes() -> text from `wg show wg-nat latest-handshakes`.
    validate_all_25_and_marked_egress() -> return on full success, raise on
    any failed listener, unit, rule or real marked-egress check.

    Timestamp freshness stays at the original 180 seconds; bounded waiting
    does not relax that threshold or claim healthy while fail-closed.
    """
    if timeout_seconds <= 0 or poll_seconds <= 0:
        raise ValueError("positive timeouts required")
    started = monotonic()
    deadline = started + timeout_seconds
    last_issue = "not checked"
    while True:
        try:
            handshake = has_fresh_handshake(read_handshakes(), int(epoch()))
            if handshake:
                validate_all_25_and_marked_egress()
                elapsed = round(monotonic() - started, 1)
                emit(f"PASS: fresh WG handshake, all 25 nodes and marked egress recovered in {elapsed}s")
                return elapsed
            last_issue = "no fresh WG handshake"
        except Exception as e:
            last_issue = str(e)
        if monotonic() >= deadline:
            raise RecoveryTimeout(
                f"WG/NAT cold-boot recovery exceeded {timeout_seconds}s; "
                f"last failure: {last_issue[-400:]}"
            )
        emit(f"WAIT: WG/NAT not fully ready: {last_issue[-160:]}")
        sleep(min(poll_seconds, max(0, deadline-monotonic())))
