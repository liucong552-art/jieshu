"""Offline tests for access logging; real Debian/3proxy acceptance is separate."""
import contextlib
import datetime as dt
import importlib.util
import io
import pathlib
import sys
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

core = load_module("socks5", "socks5.py")
audit = load_module("socks5_audit", "socks5-audit.py")


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.node = {
            "username": "u123", "password": "passABC", "port": 40007,
            "maxconn": 128, "connections": 64, "id": "s5-demo",
        }
        self.settings = {"wan_if": "eth0"}

    def test_default_audit_enabled(self):
        cfg = core.proxy_config(self.node, self.settings)
        self.assertIn("\nlog\n", cfg)
        self.assertIn("S5AUDIT %E %C %c %n %R %r %I %O", cfg)
        self.assertIn("deny u123 * * 25,465,587 CONNECT", cfg)
        self.assertIn("deny u123 * * * UDPASSOC,BIND", cfg)
        self.assertIn("socks -4 -p40007 -i0.0.0.0 -Deeth0", cfg)
        self.assertNotIn("passABC", cfg.split("logformat")[1])

    def test_old_config_compatibility_for_migration(self):
        cfg = core.proxy_config(self.node, self.settings, access_log=False)
        self.assertNotIn("S5AUDIT", cfg)
        self.assertNotIn("\nlog\n", cfg)
        self.assertTrue(cfg.endswith("socks -4 -p40007 -i0.0.0.0 -Deeth0\n"))

    def test_existing_guard_audit_cli_not_repurposed(self):
        health = core.parser().parse_args(["audit", "40007"])
        self.assertEqual(health.action, "audit")
        a = core.parser().parse_args(["access", "40007", "7"])
        self.assertEqual((a.action, a.port, a.days), ("access", "40007", "7"))


class ParserTests(unittest.TestCase):
    def test_parse_success_and_rejected_records(self):
        end = int(dt.datetime.now(dt.timezone.utc).timestamp())
        good = f"{end} S5AUDIT 000 38.244.61.82 40555 example.com 93.184.215.14 443 99 100"
        parsed = audit.parse_record(good, end-86400, end)
        self.assertEqual(parsed[2:4], ("38.244.61.82", "example.com"))
        self.assertIsNone(audit.parse_record(good, end-172800, end-86400))
        self.assertIsNone(audit.parse_record("hacker S5AUDIT unsafe", end-86400, end))
        self.assertIsNone(audit.parse_record(good.replace(" 99 100", " -1 100"), end-86400, end))
        self.assertIsNone(audit.parse_record(good.replace("38.244.61.82", "127.0.0.1"), end-86400, end))

    def test_domain_and_failures_and_minutes(self):
        end = int(dt.datetime.now(dt.timezone.utc).timestamp())
        minute = end - 40
        lines = [
            f"{minute} S5AUDIT 000 1.1.1.1 30000 EXAMPLE.COM 93.184.215.14 443 15 40",
            f"{minute+1} S5AUDIT 000 2.2.2.2 30001 example.com 93.184.215.14 443 15 40",
            f"{minute+2} S5AUDIT 000 1.1.1.1 30002 8.8.8.8 8.8.8.8 443 15 40",
            f"{minute+3} S5AUDIT 110 3.3.3.3 30003 fail.example 93.184.215.14 443 0 0",
            "not a proxy record",
        ]
        domains, clients, first, last, minutes, events, bad, failed = audit.summarize(lines, end-86400, end)
        self.assertEqual(domains["example.com"], 2)
        self.assertEqual(sum(domains.values()), 2)
        self.assertEqual(clients["1.1.1.1"], 2)
        self.assertNotIn("3.3.3.3", clients)
        self.assertEqual((events,bad,failed), (4,0,1))
        self.assertEqual(first["1.1.1.1"], minute)
        self.assertEqual(last["1.1.1.1"], minute+2)
        self.assertTrue(any(len(ips)>1 for ips in minutes.values()) or
                        dt.datetime.fromtimestamp(minute, audit.BJ).minute !=
                        dt.datetime.fromtimestamp(minute+1, audit.BJ).minute)

    def test_endpoint_parsing(self):
        self.assertEqual(audit.peer_ip("1.2.3.4:5555"), "1.2.3.4")
        self.assertEqual(audit.peer_ip("[2001:db8::a]:443"), "2001:db8::a")
        self.assertIsNone(audit.peer_ip("broken"))

    def test_report_four_sections_and_warning(self):
        end = int(dt.datetime.now(dt.timezone.utc).timestamp())
        line = f"{end} S5AUDIT 000 38.244.61.82 4242 test.example 93.184.215.14 443 20 30"
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            audit.display(40007, 7, "socks5-@s5-demo.service",
                          journal_lines=[line], ss_snapshot={"38.244.61.82": 2})
        output = buf.getvalue()
        for heading in ("【1 / 4", "【2 / 4", "【3 / 4", "【4 / 4"):
            self.assertIn(heading, output)
        self.assertIn("test.example", output)
        self.assertIn("38.244.61.82", output)
        self.assertIn("2 条连接", output)
        self.assertNotIn("警告：指定时间段没有", output)

    def test_no_logs_not_confused_with_no_abuse(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            audit.display(40007, 7, "socks5-@s5-demo.service", journal_lines=[], ss_snapshot={})
        self.assertIn("不能据此判断无人使用或没有滥用", buf.getvalue())

    def test_rejects_bad_args(self):
        with self.assertRaises(ValueError):
            audit.display(40007, 0, "socks5-@s5-demo.service", journal_lines=[])
        with self.assertRaises(ValueError):
            audit.display(40007, 7, "../evil.service", journal_lines=[])


if __name__ == "__main__":
    unittest.main()
