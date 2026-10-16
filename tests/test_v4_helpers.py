#!/usr/bin/env python3
"""Mock tests of Python modules embedded in the actual V4 installer."""
import importlib.util
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

INSTALLER = Path(__file__).resolve().parents[1] / 'vless.sh'


def extract(heredoc, name):
    source = INSTALLER.read_text(encoding='utf-8')
    pattern = (r"cat >'/usr/local/lib/vless-reality/" + re.escape(name) +
               r"' <<'" + re.escape(heredoc) + r"'\n(.*?)\n" + re.escape(heredoc))
    match = re.search(pattern, source, re.S)
    if not match:
        raise AssertionError('missing embedded helper: ' + name)
    compile(match.group(1), name, 'exec')
    return match.group(1) + '\n'


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class V4HelperTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        for name, marker in [('quota-query.py', '__VR_QUOTA_QUERY_PY__'),
                             ('watchdog-batch.py', '__VR_WD_BATCH_PY__')]:
            (self.root / name).write_text(extract(marker, name))
        self.q = load(self.root / 'quota-query.py', 'vrq_test')
        self.w = load(self.root / 'watchdog-batch.py', 'vrw_test')
        self.port = '51888'

    def snap(self, used=10, count_guard=True):
        p = self.port
        rules = {'pq_input': [{'comment': 'vr-pq-drop-in-' + p}],
                 'pq_output': [{'comment': 'vr-pq-drop-out-' + p}]}
        if count_guard:
            for direction, chain in (('in', 'pq_input'), ('out', 'pq_output')):
                rules[chain].append({'comment': 'vr-pq-count-' + direction + '-' + p})
        return ({'vr_pq_in_' + p: {'bytes': 7},
                 'vr_pq_out_' + p: {'bytes': 0}},
                {'vr_pq_q_' + p: {'used': used}}, rules)

    def test_active_and_exhausted(self):
        self.assertEqual(self.q.state(self.port, 100, 0, self.snap()), 'active')
        self.assertEqual(self.q.state(self.port, 100, 90, self.snap()), 'exhausted')

    def test_missing_guard_falls_back(self):
        with self.assertRaises(ValueError):
            self.q.state(self.port, 100, 0, self.snap(count_guard=False))

    def test_snapshot_disagreement_falls_back(self):
        with patch.object(self.q, 'snapshot', side_effect=[self.snap(), self.snap(used=100)]):
            with self.assertRaises(ValueError):
                self.q.checked_state(self.port, 100, 0)

    def test_invalid_or_incomplete_usage_falls_back(self):
        snap = self.snap()
        del snap[0]['vr_pq_in_' + self.port]
        with self.assertRaises(ValueError):
            self.q.state(self.port, 100, 0, snap)
        with self.assertRaises(ValueError):
            self.q.uint(True)

    def test_batch_requires_matching_ip_guards(self):
        qdir, idir = self.root / 'quota', self.root / 'iplimit'
        qdir.mkdir()
        idir.mkdir()
        (qdir / (self.port + '.env')).write_text(
            'ORIGINAL_LIMIT_BYTES=100\nSAVED_USED_BYTES=0\nREBUILD_PENDING=0\n')
        (idir / (self.port + '.env')).write_text('IP_VERSION=4\n')
        expected = {'vr-il-' + part + '-' + self.port
                    for part in ('refresh', 'claim', 'drop', 'family')}
        with patch.object(self.q, 'snapshot', return_value=self.snap()):
            result = self.w.batch(quota_dir=qdir, ip_dir=idir, quota_mod=self.q,
                ip_table_reader=lambda: ({'vr_il4_' + self.port}, expected))
        self.assertIn('Q|' + self.port + '|100|0|0|active', result)
        self.assertIn('I|' + self.port + '|4|active', result)
        with patch.object(self.q, 'snapshot', return_value=self.snap()):
            result = self.w.batch(quota_dir=qdir, ip_dir=idir, quota_mod=self.q,
                ip_table_reader=lambda: ({'vr_il4_' + self.port}, set()))
        self.assertNotIn('I|' + self.port, result)

    def test_pending_rebuild_not_cached(self):
        qdir, idir = self.root / 'quota', self.root / 'iplimit'
        qdir.mkdir()
        idir.mkdir()
        (qdir / (self.port + '.env')).write_text(
            'ORIGINAL_LIMIT_BYTES=100\nSAVED_USED_BYTES=0\nREBUILD_PENDING=1\n')
        with patch.object(self.q, 'snapshot', return_value=self.snap()):
            result = self.w.batch(quota_dir=qdir, ip_dir=idir, quota_mod=self.q,
                ip_table_reader=lambda: (set(), set()))
        self.assertEqual(result, '')


if __name__ == '__main__':
    unittest.main()
