#!/usr/bin/env python3
"""Self-contained tests for the repository's read-only reboot readiness probe.

The Helan onepass suite.py is a separate test package, not part of this repo.
"""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).with_name('reboot_recovery_probe.py')
spec = importlib.util.spec_from_file_location('reboot_recovery_probe', SCRIPT)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class RebootProbeTests(unittest.TestCase):
    def test_delayed_listener_success(self):
        states = iter([(3, 'inactive'), (0, 'active'), (0, 'active')])
        sockets = iter([False, True])
        with patch('sys.argv', ['reboot_recovery_probe.py', '--node', 'svpersist', '--timeout', '150']), \
             patch.object(probe.pathlib.Path, 'is_file', return_value=True), \
             patch.object(probe.pathlib.Path, 'read_text', return_value='PORT=51888\n'), \
             patch.object(probe, 'command', side_effect=lambda *args: next(states)), \
             patch.object(probe, 'probe', side_effect=lambda *args: next(sockets)), \
             patch.object(probe.time, 'monotonic', side_effect=[0, 1, 2, 3]), \
             patch.object(probe.time, 'sleep'):
            self.assertEqual(probe.main(), 0)

    def test_active_unit_without_socket_never_passes(self):
        with patch('sys.argv', ['reboot_recovery_probe.py', '--node', 'svpersist', '--timeout', '10']), \
             patch.object(probe.pathlib.Path, 'is_file', return_value=True), \
             patch.object(probe.pathlib.Path, 'read_text', return_value='PORT=51888\n'), \
             patch.object(probe, 'command', return_value=(0, 'active')), \
             patch.object(probe, 'probe', return_value=False), \
             patch.object(probe.time, 'monotonic', side_effect=[0, 11]), \
             patch.object(probe.time, 'sleep'):
            self.assertEqual(probe.main(), 1)

    def test_invalid_tag_rejected(self):
        with patch('sys.argv', ['reboot_recovery_probe.py', '--node', '../unsafe']):
            with self.assertRaises(SystemExit):
                probe.main()


if __name__ == '__main__':
    unittest.main()
