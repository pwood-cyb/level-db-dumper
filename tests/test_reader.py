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
