import tempfile
import unittest
import zipfile
from pathlib import Path

from arch_m3.build import corrected_metadata, lock_shadow, make_overlay_commands


def fixture_overlay(path):
    for name in ('etc/systemd/system/arch-m3-root-password.service',
                 'etc/systemd/system/getty@tty1.service.d/10-root-password.conf',
                 'usr/local/lib/arch-m3/set-root-password'):
        p = path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('fixture')
    return path


class BuildPolicyTests(unittest.TestCase):
    def test_rejects_empty_overlay_before_locking_accounts(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                make_overlay_commands(Path(d), Path(d) / 'shadow')

    def test_lock_root_preserves_other_accounts(self):
        result = lock_shadow('root:$6$shared:1:0:99999:7:::\ndaemon:!:1:0:99999:7:::\n')
        self.assertEqual(result, 'root:!:1:0:99999:7:::\ndaemon:!:1:0:99999:7:::\n')

    def test_locks_other_preexisting_passwords_too(self):
        result = lock_shadow('root:$6$shared:1:0:99999:7:::\nalarm:$6$shared:1:0:99999:7:::\n')
        self.assertEqual(result.splitlines()[1].split(':')[1], '!')

    def test_ignores_macos_appledouble_metadata(self):
        with tempfile.TemporaryDirectory() as d:
            overlay = Path(d) / 'overlay'
            overlay.mkdir()
            fixture_overlay(overlay)
            (overlay / '._etc').write_bytes(b'macOS metadata')
            commands = make_overlay_commands(overlay, Path(d) / 'shadow')
            self.assertFalse(any('._etc' in command for command in commands))

    def test_lock_root_rejects_missing_or_duplicate_root(self):
        for value in ('daemon:!:1::::::\n', 'root:!:1::::::\nroot:!:1::::::\n'):
            with self.assertRaises(ValueError):
                lock_shadow(value)

    def test_metadata_uses_real_image_size_and_retains_firmware_contract(self):
        original = {'os_list': [{'name': 'Asahi Alarm Minimal', 'package': 'https://example/a.zip',
                    'supported_fw': ['14.8.3'], 'partitions': [
                    {'name': 'Root', 'size': '2209614225B', 'image': 'root.img', 'expand': True}]}]}
        result = corrected_metadata(original, 3719299072)
        product = result['os_list'][0]
        self.assertEqual(product['partitions'][0]['size'], '3719299072B')
        self.assertEqual(product['supported_fw'], ['14.8.3'])
        self.assertEqual(product['package'], 'arch-m3-minimal.zip')
        self.assertEqual(original['os_list'][0]['partitions'][0]['size'], '2209614225B')

    def test_overlay_rejects_absolute_destination_and_symlink_sources(self):
        with tempfile.TemporaryDirectory() as d:
            overlay = Path(d)
            (overlay / 'link').symlink_to('/etc/passwd')
            with self.assertRaises(ValueError):
                make_overlay_commands(overlay, Path(d) / 'locked-shadow')

    def test_overlay_commands_mask_ssh_and_set_console_target(self):
        with tempfile.TemporaryDirectory() as d:
            overlay = Path(d) / 'overlay'
            overlay.mkdir()
            fixture_overlay(overlay)
            commands = make_overlay_commands(overlay, Path(d) / 'shadow')
            self.assertIn('symlink /etc/systemd/system/sshd.service /dev/null', commands)
            self.assertIn('symlink /etc/systemd/system/default.target /usr/lib/systemd/system/multi-user.target', commands)
            self.assertIn('set_inode_field /etc/shadow mode 0100600', commands)


if __name__ == '__main__':
    unittest.main()
