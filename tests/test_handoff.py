import copy
import unittest
import tempfile
from pathlib import Path

from arch_m3.handoff import HandoffError, validate_host, validate_metadata, validate_tar_path, require_posix_staging


class HostTests(unittest.TestCase):
    def host(self):
        return dict(system='Darwin', architecture='arm64', model='Mac15,3', board='J504AP', macos='27.2.1')

    def test_accepts_only_native_target(self):
        validate_host(self.host())

    def test_rejects_wrong_model_board_architecture_and_os(self):
        for key, value in [('model', 'Mac15,4'), ('board', 'J613AP'), ('architecture', 'x86_64'), ('system', 'Linux')]:
            with self.subTest(key=key):
                host = self.host()
                host[key] = value
                with self.assertRaises(HandoffError):
                    validate_host(host)

    def test_rejects_old_or_malformed_macos(self):
        for value in ('13.4', 'not-a-version', ''):
            host = self.host()
            host['macos'] = value
            with self.assertRaises(HandoffError):
                validate_host(host)


class DescriptorTests(unittest.TestCase):
    def metadata(self):
        return {'os_list': [{'name': 'Minimal', 'package': 'arch-m3-minimal.zip',
            'extras': {}, 'boot_object': 'm1n1.bin', 'next_object': 'm1n1/boot.bin', 'supported_fw': ['14.8.3'],
            'partitions': [{'name': 'EFI', 'type': 'EFI', 'size': '524288000B', 'format': 'fat',
                            'source': 'esp', 'volume_id': '0x2abf9f91', 'copy_firmware': True, 'copy_installer_data': True},
                           {'name': 'Root', 'type': 'Linux', 'size': '3719299072B',
                            'image': 'root.img', 'expand': True}]}]}

    def test_accepts_expected_local_payload(self):
        result = validate_metadata(self.metadata(), 3719299072)
        self.assertEqual(result['relative_payload'], 'os/arch-m3-minimal.zip')
        self.assertEqual(result['required_firmware'], '14.8.3')

    def test_rejects_network_and_traversal_payloads(self):
        for name in ('https://example.com/image.zip', '../image.zip', '/tmp/image.zip', 'sub/image.zip'):
            metadata = self.metadata()
            metadata['os_list'][0]['package'] = name
            with self.assertRaises(HandoffError):
                validate_metadata(metadata, 3719299072)

    def test_rejects_unreviewed_operational_fields(self):
        for change in (lambda p: p.update(extras=['https://example.invalid/unreviewed']),
                       lambda p: p['partitions'][0].update(expand=True),
                       lambda p: p['partitions'][1].update(format='fat'),
                       lambda p: p['partitions'][1].update(source='esp'),
                       lambda p: p['partitions'][0].update(volume_id='0x12345678'),
                       lambda p: p.update(script='unreviewed.sh')):
            with self.subTest(change=change):
                metadata = self.metadata()
                change(metadata['os_list'][0])
                with self.assertRaises(HandoffError):
                    validate_metadata(metadata, 3719299072)

    def test_rejects_root_size_mismatch(self):
        with self.assertRaises(HandoffError):
            validate_metadata(self.metadata(), 4096)

    def test_rejects_missing_firmware_copy_or_wrong_boot_object(self):
        for mutate in (lambda p: p['partitions'][0].update(copy_firmware=False),
                       lambda p: p.update(boot_object='different.bin'),
                       lambda p: p.update(supported_fw=['13.5'])):
            metadata = self.metadata()
            mutate(metadata['os_list'][0])
            with self.assertRaises(HandoffError):
                validate_metadata(metadata, 3719299072)


class StagingTests(unittest.TestCase):
    def test_posix_staging_probe_leaves_no_files(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            require_posix_staging(path)
            self.assertEqual(list(path.iterdir()), [])


class ArchivePathTests(unittest.TestCase):
    def test_allows_internal_framework_symlink(self):
        validate_tar_path('./Frameworks/Python.framework/Versions/Current', '3.13')

    def test_rejects_archive_or_link_escape(self):
        for path, link in [('../outside', None), ('/outside', None), ('safe', '/etc/passwd'), ('safe', '../outside')]:
            with self.subTest(path=path, link=link):
                with self.assertRaises(HandoffError):
                    validate_tar_path(path, link)


if __name__ == '__main__':
    unittest.main()
