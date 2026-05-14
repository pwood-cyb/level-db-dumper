import struct
import tempfile
import unittest
import warnings
from pathlib import Path

from level_db_dumper.reader import _to_text, dump_directory
from tests.ldb.helpers import (
    make_log_record,
    make_manifest,
    make_sst,
    make_version_edit_log_number,
    make_version_edit_new_file,
)
from level_db_dumper.ldb._varint import encode_varint


def _make_write_batch(seq_num: int, entries: list[tuple[bytes, bytes | None]]) -> bytes:
    """Build a WriteBatch payload: seq(8 LE) + count(4 LE) + entries."""
    payload = struct.pack("<QI", seq_num, len(entries))
    for key, value in entries:
        if value is None:
            payload += bytes([0]) + encode_varint(len(key)) + key
        else:
            payload += bytes([1]) + encode_varint(len(key)) + key
            payload += encode_varint(len(value)) + value
    return payload


class ToTextTests(unittest.TestCase):
    def test_preserves_utf8_text(self) -> None:
        self.assertEqual(_to_text("väl".encode("utf-8")), "väl")

    def test_escapes_control_bytes(self) -> None:
        self.assertIn("\\x00", _to_text(b"\x00"))

    def test_empty_bytes(self) -> None:
        self.assertEqual(_to_text(b""), "")

    def test_utf16le_decoded(self) -> None:
        # b"h\x00i\x00" is UTF-16LE "hi" — consistent alternating-null pattern
        self.assertEqual(_to_text("hi".encode("utf-16-le")), "hi")

    def test_utf16be_decoded(self) -> None:
        self.assertEqual(_to_text("hi".encode("utf-16-be")), "hi")

    def test_binary_with_scattered_nulls_not_decoded_as_utf16(self) -> None:
        # Binary key with some null bytes but no consistent alternating pattern:
        # was previously misidentified as UTF-16LE, producing garbage kanji.
        raw = bytes([0x0b, 0x00, 0x00, 0xc8, 0x12, 0x00, 0x70, 0x00])
        result = _to_text(raw)
        # Must not contain multi-byte Unicode (kanji etc.); only \xNN escapes or ASCII
        self.assertFalse(any(ord(c) > 127 for c in result),
                         f"Got non-ASCII in result: {result!r}")

    def test_binary_starting_with_control_char_not_decoded_as_utf8(self) -> None:
        # Chromium IndexedDB keys start with a type byte (0x0b VT or 0x0c FF).
        # Those bytes form valid UTF-8 but are non-whitespace control chars → binary.
        # Previously decoded as Latin Extended / Cyrillic garbage (e.g. "āЂĭ19:...").
        raw = bytes([0x0c, 0xc4, 0x81, 0xd0, 0x82, 0x31, 0x39, 0x3a])  # \x0c + valid UTF-8
        result = _to_text(raw)
        self.assertFalse(any(ord(c) > 127 for c in result),
                         f"Got non-ASCII in result: {result!r}")
        self.assertIn("\\x0c", result)


class DumpDirectoryTests(unittest.TestCase):
    def _write_db(
        self,
        tmp: str,
        sst_data: bytes,
        file_num: int = 3,
        log_data: bytes | None = None,
        log_num: int = 0,
    ) -> Path:
        base = Path(tmp)
        ldb_path = base / f"{file_num:06d}.ldb"
        ldb_path.write_bytes(sst_data)
        edits = [make_version_edit_new_file(0, file_num, len(sst_data), b"a", b"z")]
        if log_num:
            edits.append(make_version_edit_log_number(log_num))
        manifest = make_manifest(edits)
        (base / "CURRENT").write_text("MANIFEST-000001\n", encoding="utf-8")
        (base / "MANIFEST-000001").write_bytes(manifest)
        if log_data is not None and log_num:
            (base / f"{log_num:06d}.log").write_bytes(log_data)
        return base

    def test_reads_single_sst(self) -> None:
        sst = make_sst([(b"hello", b"world", 1, False)])
        with tempfile.TemporaryDirectory() as tmp:
            base = self._write_db(tmp, sst)
            result = dump_directory(base)
        self.assertEqual(result, {"hello": "world"})

    def test_deletion_excluded_from_output(self) -> None:
        sst = make_sst([(b"gone", b"", 1, True)])
        with tempfile.TemporaryDirectory() as tmp:
            base = self._write_db(tmp, sst)
            result = dump_directory(base)
        self.assertNotIn("gone", result)

    def test_wal_entries_included(self) -> None:
        sst = make_sst([(b"key", b"old", 1, False)])
        batch = _make_write_batch(10, [(b"key", b"new")])
        wal = make_log_record(batch)
        with tempfile.TemporaryDirectory() as tmp:
            base = self._write_db(tmp, sst, log_data=wal, log_num=9)
            result = dump_directory(base)
        self.assertEqual(result["key"], "new")

    def test_fallback_when_no_manifest(self) -> None:
        sst = make_sst([(b"fb", b"val", 1, False)])
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "000001.ldb").write_bytes(sst)
            with warnings.catch_warnings(record=True):
                warnings.simplefilter("always")
                result = dump_directory(tmp)
        self.assertIn("fb", result)

    def test_fallback_includes_wal_entries(self) -> None:
        """Fallback path (no MANIFEST) must also scan .log files so unflushed WAL
        entries are not silently dropped in the corruption scenario."""
        sst = make_sst([(b"sst_key", b"sst_val", 1, False)])
        batch = _make_write_batch(10, [(b"wal_key", b"wal_val")])
        wal = make_log_record(batch)
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "000001.ldb").write_bytes(sst)
            (Path(tmp) / "000002.log").write_bytes(wal)
            with warnings.catch_warnings(record=True):
                warnings.simplefilter("always")
                result = dump_directory(tmp)
        self.assertIn("sst_key", result)
        self.assertIn("wal_key", result)
        self.assertEqual(result["wal_key"], "wal_val")
