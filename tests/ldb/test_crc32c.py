import unittest
from level_db_dumper.ldb._crc32c import crc32c, masked_crc32c


class CRC32CTests(unittest.TestCase):
    def test_empty(self) -> None:
        self.assertEqual(crc32c(b""), 0x00000000)

    def test_known_vector(self) -> None:
        # CRC32C of b"123456789" = 0xE3069283
        self.assertEqual(crc32c(b"123456789"), 0xE3069283)

    def test_masked_differs_from_raw(self) -> None:
        raw = crc32c(b"hello")
        self.assertNotEqual(masked_crc32c(b"hello"), raw)

    def test_masked_is_uint32(self) -> None:
        self.assertLessEqual(masked_crc32c(b"x" * 1000), 0xFFFFFFFF)
