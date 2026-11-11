import unittest
from growth_checks import evaluate_growth

class GrowthChecks(unittest.TestCase):
    def sample(self):
        return dict(DISK_BYTES=str(12*1024**3), FS_BYTES=str(11*1024**3), EXTENT_BYTES=str(1024**3), DATA_SHA='a'*64, WRITE_RC='0')
    def test_valid_growth(self):
        self.assertEqual(evaluate_growth(self.sample(), self.sample()), [])
    def test_rejects_missing_failed_small_and_changed_results(self):
        for key, value in [('DISK_BYTES',''), ('FS_BYTES',str(3719299072)), ('EXTENT_BYTES','0'), ('DATA_SHA',''), ('WRITE_RC','1')]:
            with self.subTest(key=key):
                broken=self.sample(); broken[key]=value
                self.assertTrue(evaluate_growth(broken,self.sample()))
        changed=self.sample(); changed['DATA_SHA']='b'*64
        self.assertTrue(evaluate_growth(self.sample(),changed))

class GrowthInputSafety(unittest.TestCase):
    def test_symlink_overlay_rejected_before_resize(self):
        import tempfile
        import json
        from pathlib import Path
        from unittest.mock import patch
        from integration_growth import main
        from integration_reboot import sha
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory)/'fixture'; base.mkdir()
            external=Path(directory)/'external.qcow2'; external.write_bytes(b'private overlay')
            (base/'root.qcow2').symlink_to(external)
            for name in ('efi.qcow2','vars.fd','code.fd','root-base.img','efi-base.img'):
                (base/name).write_bytes(b'fixture')
            prep=dict(firmware_code=str(base/'code.fd'),firmware_sha256=sha(base/'code.fd'),
                      raw_parents_sha256={n:sha(base/n) for n in ('root-base.img','efi-base.img')},
                      overlay_initial_sha256={n:sha(base/(n+'.qcow2')) for n in ('root','efi')},vars_initial_sha256=sha(base/'vars.fd'))
            (base/'grub-preparation.json').write_text(json.dumps(prep))
            with patch('integration_growth.subprocess.run',side_effect=AssertionError('Mutation before input validation')):
                with self.assertRaises(ValueError):
                    main(base,Path(directory)/'report')
