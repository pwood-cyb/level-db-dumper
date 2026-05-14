# src/level_db_dumper/ldb/sst.py
from __future__ import annotations

import struct
import warnings
from collections.abc import Iterator

from ._crc32c import masked_crc32c
from ._varint import decode_varint

_MAGIC = 0xDB4775248B80FB57


def _read_block(file_data: bytes, offset: int, size: int) -> bytes | None:
    trailer_start = offset + size
    trailer_end = trailer_start + 5
    if trailer_end > len(file_data):
        return None

    compression_type = file_data[trailer_start]
    block_content = file_data[offset : offset + size]

    stored_crc = struct.unpack_from("<I", file_data, trailer_start + 1)[0]
    actual_crc = masked_crc32c(block_content + bytes([compression_type]))
    if actual_crc != stored_crc:
        warnings.warn(
            f"CRC mismatch in SST block at offset {offset}, skipping",
            RuntimeWarning,
            stacklevel=3,
        )
        return None

    if compression_type == 0:
        return block_content
    if compression_type == 1:
        try:
            import snappy  # type: ignore
        except Exception:
            warnings.warn(
                "Snappy-compressed SST block but python-snappy is not installed."
                " Install it with: pip install python-snappy",
                RuntimeWarning,
                stacklevel=3,
            )
            return None
        try:
            return snappy.decompress(block_content)
        except Exception:
            warnings.warn(
                f"Failed to decompress snappy block at offset {offset}",
                RuntimeWarning,
                stacklevel=3,
            )
            return None
    warnings.warn(
        f"Unknown compression type {compression_type} in SST block at offset {offset}, skipping",
        RuntimeWarning,
        stacklevel=3,
    )
    return None


def _parse_block_entries(block: bytes) -> list[tuple[bytes, bytes]]:
    if len(block) < 4:
        return []
    num_restarts = struct.unpack_from("<I", block, len(block) - 4)[0]
    restarts_size = num_restarts * 4
    restart_offset = len(block) - 4 - restarts_size
    if restart_offset < 0:
        return []

    entries: list[tuple[bytes, bytes]] = []
    offset = 0
    prev_key = b""
    while offset < restart_offset:
        try:
            shared, offset = decode_varint(block, offset)
            non_shared, offset = decode_varint(block, offset)
            value_len, offset = decode_varint(block, offset)
        except ValueError:
            break

        if shared > len(prev_key):
            break
        end_key = offset + non_shared
        end_val = end_key + value_len
        if end_val > restart_offset:
            break

        key = prev_key[:shared] + block[offset:end_key]
        value = block[end_key:end_val]
        entries.append((key, value))
        prev_key = key
        offset = end_val

    return entries


def read_entries(file_data: bytes) -> Iterator[tuple[bytes, bytes, int, bool]]:
    """Yield (user_key, value, seq_num, is_deletion) for every entry in the SST file."""
    if len(file_data) < 48:
        return

    footer = file_data[-48:]
    magic = struct.unpack_from("<Q", footer, 40)[0]
    if magic != _MAGIC:
        return

    try:
        idx = 0
        _meta_offset, idx = decode_varint(footer, idx)
        _meta_size, idx = decode_varint(footer, idx)
        index_offset, idx = decode_varint(footer, idx)
        index_size, _ = decode_varint(footer, idx)
    except ValueError:
        return

    index_block = _read_block(file_data, index_offset, index_size)
    if index_block is None:
        return

    for _, handle_data in _parse_block_entries(index_block):
        try:
            data_offset, tmp = decode_varint(handle_data, 0)
            data_size, _ = decode_varint(handle_data, tmp)
        except ValueError:
            continue

        data_block = _read_block(file_data, data_offset, data_size)
        if data_block is None:
            continue

        for internal_key, value in _parse_block_entries(data_block):
            if len(internal_key) < 8:
                continue
            user_key = internal_key[:-8]
            tag = struct.unpack_from("<Q", internal_key, len(internal_key) - 8)[0]
            seq_num = tag >> 8
            value_type = tag & 0xFF
            if value_type == 0:
                yield user_key, b"", seq_num, True
            elif value_type == 1:
                yield user_key, value, seq_num, False
