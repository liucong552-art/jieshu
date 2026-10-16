import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

# Run against the corrected suite.py placed beside this test by the test package.
spec=importlib.util.spec_from_file_location('suite', Path(__file__).with_name('suite.py'))
s=importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)

class RebootReadinessTests(unittest.TestCase):
    def test_waits_until_xray_listens_after_initial_failure(self):
        active=[(3,'inactive'),(0,'active'),(0,'active')]
        probes=[False,True]
        seen=[]
        def status(cmd,timeout=8):return active.pop(0)
        def probe(*args,**kwargs):return probes.pop(0)
        with patch.object(s,'port',return_value=51888), \
             patch.object(s,'shell',side_effect=status), \
             patch.object(s,'tcp_probe',side_effect=probe), \
             patch.object(s,'msg',side_effect=seen.append), \
             patch.object(s.time,'monotonic',side_effect=[0,1,2,3,4,5]), \
             patch.object(s.time,'sleep'):
            self.assertEqual(s.wait_postboot_listener(timeout_seconds=150),51888)
        self.assertTrue(any('inactive' in v for v in seen))

    def test_no_false_success_when_inactive(self):
        with patch.object(s,'port',return_value=51888), \
             patch.object(s,'shell',return_value=(3,'inactive')), \
             patch.object(s,'tcp_probe',return_value=True), \
             patch.object(s,'msg'), \
             patch.object(s.time,'monotonic',side_effect=[0,151]), \
             patch.object(s,'RUN',Path('/tmp')):
            with self.assertRaises(s.CaseFail):s.wait_postboot_listener(timeout_seconds=150)

    def test_quota_and_authenticated_transfer_required(self):
        q={'SAVED_USED_BYTES':'94000','ORIGINAL_LIMIT_BYTES':'999999','LIMIT_BYTES':str(999999-94000)}
        class FakeHTTP:
            def shutdown(self):pass
        with patch.object(s,'wait_postboot_listener',return_value=52100), \
             patch.object(s,'qmeta',return_value=q), \
             patch.object(s,'health'), \
             patch.object(s,'local_http_server',return_value=FakeHTTP()), \
             patch.object(s,'real_proxy',return_value='OK') as real:
            result=s.postboot_persist({'persist_saved':92511,'persist_limit':999999})
        real.assert_called_once()
        self.assertIn('authenticated VLESS',result)

if __name__=='__main__':
    unittest.main()
