from __future__ import annotations

import struct
import warnings
from pathlib import Path

MAGIC = 0xDB4775248B80FB57


def _decode_varint(data: bytes, offset: int) -> tuple[int, int]:
    result = 0
    shift = 0
    while offset < len(data):
        byte = data[offset]
        offset += 1
        result |= (byte & 0x7F) << shift
        if byte < 0x80:
            return result, offset
        shift += 7
        if shift > 63:
            break
    raise ValueError("invalid varint")


def _to_text(raw: bytes) -> str:
    return raw.decode("utf-8", errors="backslashreplace")


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
            shared, offset = _decode_varint(block, offset)
            non_shared, offset = _decode_varint(block, offset)
            value_len, offset = _decode_varint(block, offset)
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


def _parse_block_handle(raw: bytes) -> tuple[int, int]:
    offset, index = _decode_varint(raw, 0)
    size, _ = _decode_varint(raw, index)
    return offset, size


def _read_block(file_data: bytes, handle: tuple[int, int]) -> bytes | None:
    offset, size = handle
    trailer_start = offset + size
    trailer_end = trailer_start + 5
    if trailer_end > len(file_data):
        return None

    compression_type = file_data[trailer_start]
    block = file_data[offset:offset + size]
    if compression_type == 0:
        return block

    if compression_type == 1:
        try:
            import snappy  # type: ignore
        except Exception:
            warnings.warn(
                "Encountered snappy-compressed LevelDB block but python-snappy is not installed.",
                RuntimeWarning,
                stacklevel=2,
            )
            return None
        try:
            return snappy.decompress(block)
        except Exception:
            return None

    return None


def _parse_footer(file_data: bytes) -> tuple[tuple[int, int], tuple[int, int]] | None:
    if len(file_data) < 48:
        return None

    footer = file_data[-48:]
    magic = struct.unpack_from("<Q", footer, 40)[0]
    if magic != MAGIC:
        return None

    index1 = 0
    meta_offset, index1 = _decode_varint(footer, index1)
    meta_size, index1 = _decode_varint(footer, index1)
    index_offset, index1 = _decode_varint(footer, index1)
    index_size, _ = _decode_varint(footer, index1)

    return (meta_offset, meta_size), (index_offset, index_size)


def _parse_ldb_file(path: Path) -> dict[bytes, bytes]:
    file_data = path.read_bytes()
    footer = _parse_footer(file_data)
    if footer is None:
        return {}

    _, index_handle = footer
    index_block = _read_block(file_data, index_handle)
    if index_block is None:
        return {}

    results: dict[bytes, bytes] = {}

    for _, handle_data in _parse_block_entries(index_block):
        try:
            data_handle = _parse_block_handle(handle_data)
        except ValueError:
            continue

        data_block = _read_block(file_data, data_handle)
        if data_block is None:
            continue

        for internal_key, value in _parse_block_entries(data_block):
            if len(internal_key) < 8:
                continue
            user_key = internal_key[:-8]
            tag = struct.unpack_from("<Q", internal_key, len(internal_key) - 8)[0]
            value_type = tag & 0xFF
            if value_type == 0:
                results.pop(user_key, None)
                continue
            if value_type == 1 and user_key not in results:
                results[user_key] = value

    return results


def dump_directory(directory: str | Path) -> dict[str, str]:
    base = Path(directory)
    pairs: dict[bytes, bytes] = {}

    for ldb_file in sorted(base.rglob("*.ldb")):
        file_pairs = _parse_ldb_file(ldb_file)
        for key, value in file_pairs.items():
            if key not in pairs:
                pairs[key] = value

    return {_to_text(key): _to_text(value) for key, value in sorted(pairs.items())}
