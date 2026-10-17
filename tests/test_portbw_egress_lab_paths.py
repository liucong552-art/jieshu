#!/usr/bin/env python3
"""Pure no-network test of the Helan egress benchmark's runtime path setup."""
import importlib.util
from pathlib import Path
import unittest

P=Path(__file__).with_name("portbw_lab_egress_tcp_goodput.py")
spec=importlib.util.spec_from_file_location("egress_lab_tested",P)
lab=importlib.util.module_from_spec(spec)
spec.loader.exec_module(lab)

class TestEgressHarness(unittest.TestCase):
    def test_each_mode_private_paths(self):
        root=Path("/tmp/portbw-cpu-example")
        for mode in ("original","half_second","one_meg"):
            with self.subTest(mode=mode):
                result=lab.lab_environment(root,mode)
                self.assertEqual(result["PORTBW_STATE"],str(root/("state_"+mode)))
                self.assertEqual(result["PORTBW_CONF"],str(root/("config_"+mode)))
                self.assertEqual(result["PORTBW_LOCK"],str(root/("lock_"+mode)/"manager.lock"))
                self.assertEqual(result["PORTBW_RUN"],str(root/("run_"+mode)))
                self.assertEqual(result["PORTBW_UNITS"],str(root/("units_"+mode)))

if __name__=="__main__":
    unittest.main()
