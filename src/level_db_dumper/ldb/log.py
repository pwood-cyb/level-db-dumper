from __future__ import annotations

import struct
import warnings
from collections.abc import Iterator

from ._crc32c import masked_crc32c

_BLOCK_SIZE = 32768
_HEADER_SIZE = 7  # checksum(4) + length(2) + type(1)

_TYPE_FULL = 1
_TYPE_FIRST = 2
_TYPE_MIDDLE = 3
_TYPE_LAST = 4


def read_records(data: bytes) -> Iterator[bytes]:
    pos = 0
    fragment = bytearray()
    in_fragment = False

    while pos + _HEADER_SIZE <= len(data):
        block_remaining = _BLOCK_SIZE - (pos % _BLOCK_SIZE)
        if block_remaining < _HEADER_SIZE:
            pos += block_remaining
            continue

        stored_crc, length, record_type = struct.unpack_from("<IHB", data, pos)
        pos += _HEADER_SIZE

        if pos + length > len(data):
            break

        payload = data[pos : pos + length]
        pos += length

        actual_crc = masked_crc32c(bytes([record_type]) + payload)
        if actual_crc != stored_crc:
            warnings.warn(
                f"CRC mismatch in log record at offset {pos - length - _HEADER_SIZE}, skipping",
                RuntimeWarning,
                stacklevel=2,
            )
            in_fragment = False
            fragment = bytearray()
            continue

        if record_type == _TYPE_FULL:
            in_fragment = False
            fragment = bytearray()
            yield bytes(payload)
        elif record_type == _TYPE_FIRST:
            fragment = bytearray(payload)
            in_fragment = True
        elif record_type == _TYPE_MIDDLE and in_fragment:
            fragment.extend(payload)
        elif record_type == _TYPE_LAST and in_fragment:
            fragment.extend(payload)
            yield bytes(fragment)
            fragment = bytearray()
            in_fragment = False
