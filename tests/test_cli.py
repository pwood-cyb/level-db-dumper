import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from level_db_dumper.cli import main


class CliTests(unittest.TestCase):
    @patch("level_db_dumper.cli.dump_directory", return_value={"k": "väl"})
    def test_stdout_warning_for_non_ascii(self, _mock_dump) -> None:
        stdout_buffer = io.StringIO()
        stderr_buffer = io.StringIO()

        with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
            rc = main([".", "--format", "json", "--output", "-"])

        self.assertEqual(rc, 0)
        self.assertIn("väl", stdout_buffer.getvalue())
        self.assertIn("non-ASCII", stderr_buffer.getvalue())

    @patch("level_db_dumper.cli.dump_directory", return_value={"a": "b"})
    def test_writes_to_file(self, _mock_dump) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            out = f"{tmp_dir}/dump.yaml"
            rc = main([".", "--format", "yaml", "--output", out])
            self.assertEqual(rc, 0)
            with open(out, "r", encoding="utf-8") as handle:
                self.assertEqual(handle.read().strip(), '"a": "b"')
