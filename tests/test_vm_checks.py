import unittest
import tempfile
from pathlib import Path
from vm_checks import evaluate_guest_checks, reset_result


class VmResultTests(unittest.TestCase):
    def report(self):
        return ('M3_KERNEL=7.2.12-3-1-ARCH\r\nM3_MULTI=active\r\n'
                'M3_FIRSTBOOT=active\r\nM3_SYSTEM=running\r\n'
                'M3_FAILED_COUNT=0\r\nM3_PACMAN_RC=0\r\nM3_SIGNATURE_RC=0\r\nM3_FSTAB_RC=0\r\nM3_GRUB_RC=0\r\n'
                'M3_ROOT_UUID=cebcecda-3de8-40d8-957e-4957efc0915b\r\nM3_EFI_UUID=799B-7FAC\r\n')

    def test_requires_named_target_and_successful_firstboot_with_efi(self):
        self.assertEqual(evaluate_guest_checks(self.report(), True)['failures'], [])
        for before, after in [('M3_MULTI=active', 'M3_MULTI=inactive'),
                              ('M3_FIRSTBOOT=active', 'M3_FIRSTBOOT=failed'),
                              ('M3_FAILED_COUNT=0', 'M3_FAILED_COUNT=1'),
                              ('M3_PACMAN_RC=0', 'M3_PACMAN_RC=1')]:
            self.assertTrue(evaluate_guest_checks(self.report().replace(before, after), True)['failures'])

    def test_unlabelled_active_and_echoed_commands_cannot_pass(self):
        text = "root# printf 'M3_MULTI=active'; systemctl is-active target\nactive\n"
        self.assertTrue(evaluate_guest_checks(text, True)['failures'])

    def test_missing_or_invalid_uuid_markers_fail(self):
        for field in ('ROOT_UUID', 'EFI_UUID'):
            for value in ('', 'not-a-uuid'):
                import re
                changed = re.sub(r'M3_' + field + r'=[^\r\n]*', 'M3_' + field + '=' + value, self.report())
                self.assertTrue(evaluate_guest_checks(changed, True)['failures'])
        self.assertTrue(evaluate_guest_checks(self.report().replace('M3_ROOT_UUID=cebcecda-3de8-40d8-957e-4957efc0915b\r\n', ''), True)['failures'])

    def test_stale_success_is_removed_without_touching_other_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)
            (p / 'vm-fixture-result.json').write_text('{}')
            (p / 'keep.log').write_text('keep')
            reset_result(p)
            self.assertFalse((p / 'vm-fixture-result.json').exists())
            self.assertEqual((p / 'keep.log').read_text(), 'keep')

    def test_invalid_rerun_clears_previous_success_before_validation(self):
        from integration_vm import run
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)
            (p / 'vm-fixture-result.json').write_text('{}')
            with self.assertRaises(ValueError):
                run(p / 'unused', p, 'invalid')
            self.assertFalse((p / 'vm-fixture-result.json').exists())

    def test_duplicate_markers_fail_closed(self):
        text = self.report() + 'M3_PACMAN_RC=1\n'
        self.assertTrue(evaluate_guest_checks(text, True)['failures'])


if __name__ == '__main__':
    unittest.main()
