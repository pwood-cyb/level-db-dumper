import unittest

from level_db_dumper.ldb._varint import decode_varint, encode_varint


class VarintTests(unittest.TestCase):
    def test_encode_zero(self) -> None:
        self.assertEqual(encode_varint(0), b"\x00")

    def test_encode_single_byte_max(self) -> None:
        self.assertEqual(encode_varint(127), b"\x7f")

    def test_encode_two_byte_boundary(self) -> None:
        self.assertEqual(encode_varint(128), b"\x80\x01")

    def test_roundtrip_large_value(self) -> None:
        value = 123456789
        encoded = encode_varint(value)
        decoded, _ = decode_varint(encoded, 0)
        self.assertEqual(decoded, value)

    def test_decode_reads_offset_correctly(self) -> None:
        data = encode_varint(300) + encode_varint(42)
        val1, pos = decode_varint(data, 0)
        val2, _ = decode_varint(data, pos)
        self.assertEqual(val1, 300)
        self.assertEqual(val2, 42)

    def test_decode_truncated_raises(self) -> None:
        with self.assertRaises(ValueError):
            decode_varint(b"\x80", 0)  # continuation bit set, no next byte

    def test_encode_negative_raises(self) -> None:
        with self.assertRaises(ValueError):
            encode_varint(-1)
