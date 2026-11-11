import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from arch_m3.audit import AuditError, inspect_archive, evaluate_system


def payload(path, extra=()):
    root = bytearray(4096)
    root[1080:1082] = b'\x53\xef'
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('root.img', root)
        z.writestr('esp/EFI/BOOT/BOOTAA64.EFI', b'MZ' + bytes(128))
        z.writestr('esp/m1n1/boot.bin', b'boot')
        for name, data in extra:
            z.writestr(name, data)


class ArchiveTests(unittest.TestCase):
    def test_accepts_console_payload_structure(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'image.zip'
            payload(p)
            report = inspect_archive(p)
            self.assertEqual(report['root_bytes'], 4096)
            self.assertEqual(report['filesystem'], 'ext4')
            self.assertEqual(len(report['sha256']), 64)

    def test_rejects_archive_traversal(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'image.zip'
            payload(p, [('../outside', b'bad')])
            with self.assertRaises(AuditError):
                inspect_archive(p)

    def test_rejects_missing_boot_chain(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'image.zip'
            with zipfile.ZipFile(p, 'w') as z:
                z.writestr('root.img', bytes(4096))
            with self.assertRaises(AuditError):
                inspect_archive(p)

    def test_rejects_symlink_members(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'image.zip'
            payload(p)
            with zipfile.ZipFile(p, 'a') as z:
                entry = zipfile.ZipInfo('esp/link')
                entry.create_system = 3
                entry.external_attr = 0o120777 << 16
                z.writestr(entry, '/etc/passwd')
            with self.assertRaises(AuditError):
                inspect_archive(p)

    def test_rejects_wrong_expected_digest(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'image.zip'
            payload(p)
            with self.assertRaises(AuditError):
                inspect_archive(p, expected_sha256='0' * 64)


class SystemTests(unittest.TestCase):
    def system(self):
        return dict(packages={'base': '1', 'pacman': '7', 'linux-asahi': '7.2',
                              'm1n1': '1.9.9', 'uboot-asahi': '2026', 'networkmanager': '1'},
                    board_dtb=True, board_dtb_in_boot_bundle=True,
                    kernel=True, initramfs=True, grub_root_uuid=True,
                    default_target='multi-user.target', root_password_locked=True)

    def test_accepts_console_system_without_claiming_hardware_boot(self):
        report = evaluate_system(self.system())
        self.assertEqual(report['failures'], [])
        self.assertFalse(report['hardware_boot_verified'])

    def test_rejects_missing_board_dtb(self):
        s = self.system()
        s['board_dtb'] = False
        self.assertTrue(evaluate_system(s)['failures'])

    def test_rejects_desktop_or_omarchy_runtime(self):
        for pkg in ['hyprland', 'omarchy', 'omarchy-dev', 'sddm', 'gnome-shell', 'plasma-workspace']:
            with self.subTest(pkg=pkg):
                s = self.system()
                s['packages'][pkg] = '1'
                self.assertTrue(evaluate_system(s)['failures'])

    def test_reports_unlocked_root_as_a_security_finding(self):
        s = self.system()
        s['root_password_locked'] = False
        self.assertTrue(evaluate_system(s)['warnings'])

    def test_rejects_missing_network_package(self):
        s = self.system()
        del s['packages']['networkmanager']
        self.assertTrue(evaluate_system(s)['failures'])


if __name__ == '__main__':
    unittest.main()
