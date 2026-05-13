# tests/ldb/test_sst.py
import unittest
import warnings

from level_db_dumper.ldb.sst import read_entries
from tests.ldb.helpers import make_sst


class SSTEntryReaderTests(unittest.TestCase):
    def test_single_put_entry(self) -> None:
        data = make_sst([(b"key", b"value", 1, False)])
        entries = list(read_entries(data))
        self.assertEqual(len(entries), 1)
        user_key, value, seq_num, is_deletion = entries[0]
        self.assertEqual(user_key, b"key")
        self.assertEqual(value, b"value")
        self.assertEqual(seq_num, 1)
        self.assertFalse(is_deletion)

    def test_deletion_tombstone_yielded(self) -> None:
        data = make_sst([(b"key", b"", 5, True)])
        entries = list(read_entries(data))
        self.assertEqual(len(entries), 1)
        user_key, value, seq_num, is_deletion = entries[0]
        self.assertEqual(user_key, b"key")
        self.assertEqual(seq_num, 5)
        self.assertTrue(is_deletion)

    def test_multiple_entries_in_order(self) -> None:
        pairs = [(b"aaa", b"1", 1, False), (b"bbb", b"2", 2, False), (b"ccc", b"3", 3, False)]
        data = make_sst(pairs)
        entries = list(read_entries(data))
        self.assertEqual(len(entries), 3)
        keys = [e[0] for e in entries]
        self.assertEqual(keys, [b"aaa", b"bbb", b"ccc"])

    def test_invalid_footer_returns_empty(self) -> None:
        self.assertEqual(list(read_entries(b"\x00" * 100)), [])

    def test_sequence_numbers_preserved(self) -> None:
        data = make_sst([(b"k", b"v", 42, False)])
        entries = list(read_entries(data))
        self.assertEqual(entries[0][2], 42)
