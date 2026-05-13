import struct
import unittest
import warnings

from level_db_dumper.ldb._crc32c import masked_crc32c
from level_db_dumper.ldb.log import read_records

_TYPE_FULL = 1
_TYPE_FIRST = 2
_TYPE_LAST = 4


def _make_record(payload: bytes, record_type: int = _TYPE_FULL) -> bytes:
    crc = masked_crc32c(bytes([record_type]) + payload)
    return struct.pack("<IHB", crc, len(payload), record_type) + payload


class LogRecordReaderTests(unittest.TestCase):
    def test_full_record_yields_payload(self) -> None:
        data = _make_record(b"hello world")
        self.assertEqual(list(read_records(data)), [b"hello world"])

    def test_fragmented_record_reassembled(self) -> None:
        data = _make_record(b"hel", _TYPE_FIRST) + _make_record(b"lo", _TYPE_LAST)
        self.assertEqual(list(read_records(data)), [b"hello"])

    def test_bad_crc_skipped_with_warning(self) -> None:
        record = _make_record(b"good")
        # Corrupt the CRC (first 4 bytes)
        bad = b"\x00\x00\x00\x00" + record[4:]
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = list(read_records(bad))
        self.assertEqual(result, [])
        self.assertTrue(any("CRC" in str(w.message) for w in caught))

    def test_truncated_data_yields_nothing(self) -> None:
        # Only 3 bytes — not enough for a 7-byte header
        self.assertEqual(list(read_records(b"\x01\x02\x03")), [])

    def test_multiple_records(self) -> None:
        data = _make_record(b"first") + _make_record(b"second")
        self.assertEqual(list(read_records(data)), [b"first", b"second"])

    def test_block_padding_skipped(self) -> None:
        # Place a record, pad to near block boundary, place another record
        record = _make_record(b"after padding")
        block_size = 32768
        # Position the second record at exactly the start of block 1
        padding = b"\x00" * (block_size - len(_make_record(b"before")))
        data = _make_record(b"before") + padding + record
        result = list(read_records(data))
        self.assertIn(b"before", result)
        self.assertIn(b"after padding", result)
