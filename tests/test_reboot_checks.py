import tempfile
import unittest
from pathlib import Path

from reboot_checks import evaluate_lifecycle, build_uefi_args, firmware_boot_evidence


class LifecycleChecks(unittest.TestCase):
    def phase(self, second=False):
        return dict(UEFI='1', BOOT_ID='22222222-2222-4222-8222-222222222222' if second else '11111111-1111-4111-8111-111111111111',
                    ROOT_UUID='72f5ea8a-8602-4203-a8db-b79d319a9568', EFI_UUID='226E-D70A',
                    SHADOW_SHA='a' * 64, PERSIST='saved-proof', FIRSTBOOT='inactive' if second else 'active',
                    SYSTEM='running', FAILED_COUNT='0', setup_prompt_seen=not second, firmware_grub_verified=True)

    def test_accepts_new_boot_id_and_persisted_identity(self):
        self.assertEqual(evaluate_lifecycle(self.phase(), self.phase(True)), [])

    def test_rejects_identity_password_and_persistence_changes(self):
        for field, value in [('ROOT_UUID', 'different'), ('EFI_UUID', 'different'),
                             ('SHADOW_SHA', 'b' * 64), ('PERSIST', ''), ('UEFI', '0'),
                             ('BOOT_ID', '11111111-1111-4111-8111-111111111111'),
                             ('setup_prompt_seen', True), ('FIRSTBOOT', 'active'), ('firmware_grub_verified', False)]:
            with self.subTest(field=field):
                second = self.phase(True)
                second[field] = value
                self.assertTrue(evaluate_lifecycle(self.phase(), second))

    def test_missing_boot_id_and_shadow_hash_do_not_pass(self):
        first, second = self.phase(), self.phase(True)
        del second['BOOT_ID']
        del first['SHADOW_SHA']
        self.assertTrue(evaluate_lifecycle(first, second))


class FirmwareLogTests(unittest.TestCase):
    def test_requires_grub_banner_and_actual_kernel_loading(self):
        log = "UEFI firmware\nGNU GRUB version 2:2.16-3\nBooting `Arch Linux'\nLoading Linux linux-asahi ...\nLoading initial ramdisk ...\n"
        self.assertTrue(firmware_boot_evidence(log)['verified'])
        self.assertFalse(firmware_boot_evidence('UEFI firmware\nLinux booted\n')['verified'])
        self.assertFalse(firmware_boot_evidence(log.replace('Loading initial ramdisk ...', ''))['verified'])


class FirmwareArgsTests(unittest.TestCase):
    def test_boots_only_through_firmware_with_persistent_file_overlays(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)
            for name in ('root.qcow2', 'efi.qcow2', 'vars.fd', 'code.fd'):
                (p / name).touch()
            args = build_uefi_args(p, p / 'code.fd')
            self.assertFalse(any(a in args for a in ('-kernel', '-initrd', '-append', '-snapshot')))
            self.assertEqual(args[args.index('-nic') + 1], 'none')
            self.assertIn('virt,acpi=off', args)
            drives = [args[i + 1] for i, value in enumerate(args) if value == '-drive']
            self.assertTrue(any('readonly=on' in d and 'code.fd' in d for d in drives))
            self.assertEqual(sum('format=qcow2' in d for d in drives), 2)
            self.assertFalse(any('snapshot=on' in d for d in drives))

    def test_rejects_missing_or_symlink_overlay(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)
            with self.assertRaises(ValueError):
                build_uefi_args(p, p / 'code.fd')


if __name__ == '__main__':
    unittest.main()
