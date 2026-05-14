import unittest

from level_db_dumper.ldb.merge import merge


def _source(*entries: tuple[bytes, bytes, int, bool]):
    return iter(entries)


class MergeTests(unittest.TestCase):
    def test_single_source_single_key(self) -> None:
        result = merge([_source((b"k", b"v", 1, False))])
        self.assertEqual(result, {b"k": b"v"})

    def test_higher_seq_num_wins(self) -> None:
        s1 = _source((b"k", b"old", 1, False))
        s2 = _source((b"k", b"new", 5, False))
        result = merge([s1, s2])
        self.assertEqual(result[b"k"], b"new")

    def test_deletion_suppresses_key(self) -> None:
        s1 = _source((b"k", b"v", 1, False))
        s2 = _source((b"k", b"", 2, True))
        result = merge([s1, s2])
        self.assertNotIn(b"k", result)

    def test_lower_seq_deletion_does_not_suppress_newer_put(self) -> None:
        s1 = _source((b"k", b"", 1, True))
        s2 = _source((b"k", b"v", 5, False))
        result = merge([s1, s2])
        self.assertEqual(result[b"k"], b"v")

    def test_empty_sources(self) -> None:
        self.assertEqual(merge([]), {})

    def test_multiple_keys_independent(self) -> None:
        s1 = _source((b"a", b"1", 1, False), (b"b", b"2", 1, False))
        result = merge([s1])
        self.assertEqual(result, {b"a": b"1", b"b": b"2"})
