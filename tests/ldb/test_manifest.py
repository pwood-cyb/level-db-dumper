import tempfile
import unittest
from pathlib import Path

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

    def test_l0_files_sorted_descending_by_file_number(self) -> None:
        edit1 = make_version_edit_new_file(0, 2, 512, b"a", b"m")
        edit2 = make_version_edit_new_file(0, 5, 512, b"a", b"m")
        manifest = make_manifest([edit1, edit2])
        with tempfile.TemporaryDirectory() as tmp:
            base = self._write_db(tmp, manifest)
            info = read_manifest(base)
        file_numbers = [f.file_number for f in info.live_files]
        self.assertEqual(file_numbers, [5, 2])
