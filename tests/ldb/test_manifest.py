import tempfile
import unittest
from pathlib import Path

from level_db_dumper.ldb._varint import encode_varint
from level_db_dumper.ldb.manifest import read_manifest
from tests.ldb.helpers import (
    make_manifest,
    make_version_edit_deleted_file,
    make_version_edit_log_number,
    make_version_edit_new_file,
)


class ManifestParserTests(unittest.TestCase):
    def _write_db(self, tmp: str, manifest_data: bytes, log_number: int = 0) -> Path:
        base = Path(tmp)
        manifest_name = "MANIFEST-000001"
        (base / "CURRENT").write_text(manifest_name + "\n", encoding="utf-8")
        (base / manifest_name).write_bytes(manifest_data)
        return base

    def test_single_file_live(self) -> None:
        edit = make_version_edit_new_file(0, 5, 1024, b"aaa", b"zzz")
        manifest = make_manifest([edit])
        with tempfile.TemporaryDirectory() as tmp:
            base = self._write_db(tmp, manifest)
            info = read_manifest(base)
        self.assertEqual(len(info.live_files), 1)
        self.assertEqual(info.live_files[0].file_number, 5)
        self.assertEqual(info.live_files[0].level, 0)

    def test_add_then_delete_leaves_empty(self) -> None:
        add = make_version_edit_new_file(0, 3, 512, b"a", b"z")
        delete = make_version_edit_deleted_file(0, 3)
        manifest = make_manifest([add, delete])
        with tempfile.TemporaryDirectory() as tmp:
            base = self._write_db(tmp, manifest)
            info = read_manifest(base)
        self.assertEqual(info.live_files, [])

    def test_log_number_extracted(self) -> None:
        edit = make_version_edit_log_number(7)
        manifest = make_manifest([edit])
        with tempfile.TemporaryDirectory() as tmp:
            base = self._write_db(tmp, manifest)
            info = read_manifest(base)
        self.assertEqual(info.log_number, 7)

    def test_missing_current_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):
                read_manifest(Path(tmp))

    def test_snapshot_record_with_leading_comparator_tag_is_parsed(self) -> None:
        """Real MANIFEST snapshot records start with tag 1 (Comparator) followed by tags
        9, 2, 3, 4, and 7.  The old `break` on tag 1 silently dropped LogNumber and
        NewFile entries from the snapshot; verify they are now extracted correctly."""
        comparator = b"leveldb.BytewiseComparator"
        snapshot_edit = (
            encode_varint(1) + encode_varint(len(comparator)) + comparator  # Comparator
            + encode_varint(9) + encode_varint(0)   # PrevLogNumber = 0
            + encode_varint(2) + encode_varint(5)   # LogNumber = 5
            + encode_varint(3) + encode_varint(10)  # NextFileNumber = 10
            + encode_varint(4) + encode_varint(100) # LastSequence = 100
            + make_version_edit_new_file(0, 1, 512, b"a", b"z")
        )
        manifest = make_manifest([snapshot_edit])
        with tempfile.TemporaryDirectory() as tmp:
            base = self._write_db(tmp, manifest)
            info = read_manifest(base)
        self.assertEqual(info.log_number, 5)
        self.assertEqual(len(info.live_files), 1)
        self.assertEqual(info.live_files[0].file_number, 1)

    def test_l0_files_sorted_descending_by_file_number(self) -> None:
        edit1 = make_version_edit_new_file(0, 2, 512, b"a", b"m")
        edit2 = make_version_edit_new_file(0, 5, 512, b"a", b"m")
        manifest = make_manifest([edit1, edit2])
        with tempfile.TemporaryDirectory() as tmp:
            base = self._write_db(tmp, manifest)
            info = read_manifest(base)
        file_numbers = [f.file_number for f in info.live_files]
        self.assertEqual(file_numbers, [5, 2])
