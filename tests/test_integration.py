# tests/test_integration.py
import unittest
from pathlib import Path

from level_db_dumper.reader import dump_directory

FIXTURES = Path(__file__).parent / "fixtures"


@unittest.skipUnless((FIXTURES / "single_sst").exists(), "fixtures not generated — run scripts/generate_fixtures.py on Linux")
class IntegrationTests(unittest.TestCase):
    def test_single_sst_reads_all_keys(self) -> None:
        result = dump_directory(FIXTURES / "single_sst")
        self.assertEqual(result.get("alpha"), "one")
        self.assertEqual(result.get("beta"), "two")
        self.assertEqual(result.get("gamma"), "three")

    def test_deleted_key_absent(self) -> None:
        result = dump_directory(FIXTURES / "with_deletions")
        self.assertEqual(result.get("keep"), "yes")
        self.assertNotIn("remove", result)

    def test_wal_unflushed_key_present(self) -> None:
        result = dump_directory(FIXTURES / "wal_unflushed")
        self.assertIn("wal_key", result)
        self.assertEqual(result["wal_key"], "wal_value")
