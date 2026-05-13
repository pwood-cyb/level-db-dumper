import struct
import unittest
import warnings

from level_db_dumper.ldb._crc32c import masked_crc32c
from level_db_dumper.ldb.log import read_records

_TYPE_FULL = 1
_TYPE_FIRST = 2
_TYPE_MIDDLE = 3
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

    def test_fragmented_record_with_middle(self) -> None:
        data = (
            _make_record(b"hel", _TYPE_FIRST)
            + _make_record(b"lo w", _TYPE_MIDDLE)
            + _make_record(b"orld", _TYPE_LAST)
        )
        self.assertEqual(list(read_records(data)), [b"hello world"])

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
        block_size = 32768
        # End the first record exactly 4 bytes before the block boundary.
        # The 4-byte gap (< _HEADER_SIZE=7) triggers the boundary skip directly.
        record_after = _make_record(b"after padding")
        before_payload_size = block_size - 7 - 4  # header(7) + payload + 4 trailing bytes = block_size
        before_payload = b"x" * before_payload_size
        data = _make_record(before_payload) + b"\x00" * 4 + record_after

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = list(read_records(data))

        crc_warnings = [w for w in caught if "CRC" in str(w.message)]
        self.assertEqual(crc_warnings, [], "block-boundary skip should emit no CRC warnings")
        self.assertIn(before_payload, result)
        self.assertIn(b"after padding", result)
