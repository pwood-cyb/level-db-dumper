# tests/ldb/helpers.py
"""Binary builders for synthetic LevelDB test data."""
from __future__ import annotations

import struct

from level_db_dumper.ldb._crc32c import masked_crc32c
from level_db_dumper.ldb._varint import encode_varint


def make_block(entries: list[tuple[bytes, bytes]]) -> bytes:
    """Build block content (without trailer) from (key, value) pairs."""
    content = bytearray()
    prev_key = b""
    for key, value in entries:
        shared = 0
        while shared < len(prev_key) and shared < len(key) and prev_key[shared] == key[shared]:
            shared += 1
        non_shared = len(key) - shared
        content += encode_varint(shared)
        content += encode_varint(non_shared)
        content += encode_varint(len(value))
        content += key[shared:]
        content += value
        prev_key = key
    # Restart array: single restart at offset 0
    content += struct.pack("<I", 0)
    content += struct.pack("<I", 1)  # num_restarts = 1
    return bytes(content)


def make_block_with_trailer(entries: list[tuple[bytes, bytes]]) -> bytes:
    content = make_block(entries)
    crc = masked_crc32c(content + b"\x00")
    return content + b"\x00" + struct.pack("<I", crc)


def make_sst(pairs: list[tuple[bytes, bytes, int, bool]]) -> bytes:
    """Build a minimal valid SST file.

    pairs: list of (user_key, value, seq_num, is_deletion)
    """
    entries = []
    for user_key, value, seq_num, is_deletion in pairs:
        vtype = 0 if is_deletion else 1
        ikey = user_key + struct.pack("<Q", (seq_num << 8) | vtype)
        entries.append((ikey, b"" if is_deletion else value))

    data_content = make_block(entries)
    data_size = len(data_content)
    data_crc = masked_crc32c(data_content + b"\x00")
    data_block = data_content + b"\x00" + struct.pack("<I", data_crc)

    # Index block: one entry — key = last internal key, value = block handle
    index_key = entries[-1][0]
    index_value = encode_varint(0) + encode_varint(data_size)
    index_offset = len(data_block)
    index_content = make_block([(index_key, index_value)])
    index_size = len(index_content)
    index_crc = masked_crc32c(index_content + b"\x00")
    index_block = index_content + b"\x00" + struct.pack("<I", index_crc)

    # Footer: meta_handle(0,0) + index_handle(index_offset, index_size) + padding + magic
    meta_handle = encode_varint(0) + encode_varint(0)
    idx_handle = encode_varint(index_offset) + encode_varint(index_size)
    footer_data = meta_handle + idx_handle
    padding = b"\x00" * (40 - len(footer_data))
    magic = struct.pack("<Q", 0xDB4775248B80FB57)
    footer = footer_data + padding + magic

    return data_block + index_block + footer


def make_log_record(payload: bytes, record_type: int = 1) -> bytes:
    """Build a single log record (FULL by default)."""
    crc = masked_crc32c(bytes([record_type]) + payload)
    return struct.pack("<IHB", crc, len(payload), record_type) + payload


def make_version_edit_new_file(
    level: int, file_num: int, size: int, smallest_key: bytes, largest_key: bytes
) -> bytes:
    """Encode a VersionEdit NewFile(7) field."""
    data = bytearray()
    data += encode_varint(7)
    data += encode_varint(level)
    data += encode_varint(file_num)
    data += encode_varint(size)
    data += encode_varint(len(smallest_key)) + smallest_key
    data += encode_varint(len(largest_key)) + largest_key
    return bytes(data)


def make_version_edit_deleted_file(level: int, file_num: int) -> bytes:
    """Encode a VersionEdit DeletedFile(6) field."""
    return encode_varint(6) + encode_varint(level) + encode_varint(file_num)


def make_version_edit_log_number(log_num: int) -> bytes:
    """Encode a VersionEdit LogNumber(2) field."""
    return encode_varint(2) + encode_varint(log_num)


def make_manifest(edits: list[bytes]) -> bytes:
    """Wrap a list of raw VersionEdit payloads in log records."""
    result = bytearray()
    for edit in edits:
        result += make_log_record(edit)
    return bytes(result)
