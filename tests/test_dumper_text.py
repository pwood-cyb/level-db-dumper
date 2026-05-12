import unittest

from level_db_dumper.dumper import _to_text


class DumperTextConversionTests(unittest.TestCase):
    def test_preserves_utf8_text(self) -> None:
        self.assertEqual(_to_text("väl".encode("utf-8")), "väl")

    def test_decodes_utf16le_when_likely(self) -> None:
        self.assertEqual(_to_text("folders".encode("utf-16-le")), "folders")

    def test_escapes_binary_controls(self) -> None:
        self.assertEqual(_to_text(b"\x00\n\x00\x00\x03"), "\\x00\\n\\x00\\x00\\x03")

    def test_utf8_with_many_controls_falls_back_to_binary_escape(self) -> None:
        self.assertEqual(_to_text(b"\x01ok\x02"), "\\x01ok\\x02")
