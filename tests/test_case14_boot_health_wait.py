#!/usr/bin/env python3
import unittest
from unittest.mock import Mock
from case14_boot_health_wait import has_fresh_handshake, await_coldboot_recovery, RecoveryTimeout


class BootWaitTests(unittest.TestCase):
    def test_handshake_180s_boundary_and_future_rejected(self):
        self.assertTrue(has_fresh_handshake("key 820", 1000))
        self.assertFalse(has_fresh_handshake("key 819", 1000))
        self.assertFalse(has_fresh_handshake("key 1001", 1000))
        self.assertFalse(has_fresh_handshake("key 0", 1000))

    def test_new_handshake_does_not_mask_down_nat(self):
        health = Mock(side_effect=[RuntimeError("NAT down"), None])
        read = Mock(return_value="key 995")
        clock = Mock(return_value=0)
        sleep = Mock()
        elapsed = await_coldboot_recovery(read, health, timeout_seconds=300,
                   epoch=lambda: 1000, monotonic=clock, sleep=sleep, emit=lambda _: None)
        self.assertEqual(elapsed, 0.0)
        self.assertEqual(health.call_count, 2)
        sleep.assert_called_once()

    def test_stale_handshake_never_checks_health(self):
        health = Mock()
        times = iter([0,301])
        with self.assertRaises(RecoveryTimeout):
            await_coldboot_recovery(lambda:"key 1",health,timeout_seconds=300,
                       epoch=lambda:1000, monotonic=lambda:next(times),
                       sleep=lambda _:None, emit=lambda _:None)
        health.assert_not_called()


if __name__ == "__main__":
    unittest.main()
