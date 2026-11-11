import unittest
from vm_archive import append_newc, newc_entry


class InitramfsFixtureTests(unittest.TestCase):
    def test_appended_cpio_starts_at_global_four_byte_boundary(self):
        combined = append_newc(b'abc', b'070701test')
        self.assertEqual(combined[:4], b'abc\0')
        self.assertEqual(combined[4:10], b'070701')

    def test_already_aligned_archive_is_not_shifted(self):
        self.assertEqual(append_newc(b'abcd', b'070701test'), b'abcd070701test')

    def test_newc_file_data_and_next_entry_are_aligned(self):
        entry = newc_entry('init', b'hello', 0o100755, 17)
        self.assertEqual(entry[:6], b'070701')
        self.assertEqual(int(entry[94:102], 16), 5)
        self.assertEqual(entry[110:115], b'init\0')
        self.assertEqual(entry[116:121], b'hello')
        self.assertEqual(len(entry) % 4, 0)


if __name__ == '__main__':
    unittest.main()
