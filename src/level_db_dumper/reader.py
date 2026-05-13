from __future__ import annotations

import struct
import warnings
from collections.abc import Iterator
from pathlib import Path

from .ldb._varint import decode_varint
from .ldb.log import read_records
from .ldb.manifest import read_manifest
from .ldb.merge import merge
from .ldb.sst import read_entries as read_sst_entries

PRINTABLE_RATIO_THRESHOLD = 0.7
UTF16_NULL_RATIO_THRESHOLD = 0.2


def _escape_controls(text: str) -> str:
    escaped: list[str] = []
    for char in text:
        code = ord(char)
        if char == "\\":
            escaped.append("\\\\")
        elif char == "\n":
            escaped.append("\\n")
        elif char == "\r":
            escaped.append("\\r")
        elif char == "\t":
            escaped.append("\\t")
        elif 0 <= code < 32 or code == 127:
            escaped.append(f"\\x{code:02x}")
        else:
            escaped.append(char)
    return "".join(escaped)


def _is_mostly_printable(text: str) -> bool:
    if not text:
        return True
    printable_count = 0
    for char in text:
        code = ord(char)
        if char in {"\n", "\r", "\t"} or (code >= 32 and code != 127):
            printable_count += 1
    return printable_count / len(text) >= PRINTABLE_RATIO_THRESHOLD


def _escape_binary(raw: bytes) -> str:
    escaped: list[str] = []
    for byte in raw:
        if byte == 92:
            escaped.append("\\\\")
        elif byte == 10:
            escaped.append("\\n")
        elif byte == 13:
            escaped.append("\\r")
        elif byte == 9:
            escaped.append("\\t")
        elif 32 <= byte < 127:
            escaped.append(chr(byte))
        else:
            escaped.append(f"\\x{byte:02x}")
    return "".join(escaped)


def _to_text(raw: bytes) -> str:
    if not raw:
        return ""

    null_ratio = raw.count(0) / len(raw)
    if len(raw) % 2 == 0 and null_ratio >= UTF16_NULL_RATIO_THRESHOLD:
        for encoding in ("utf-16-le", "utf-16-be"):
            try:
                utf16_text = raw.decode(encoding)
            except UnicodeDecodeError:
                continue
            if _is_mostly_printable(utf16_text):
                return _escape_controls(utf16_text)

    try:
        utf8_text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return _escape_binary(raw)

    if _is_mostly_printable(utf8_text):
        return _escape_controls(utf8_text)
    return _escape_binary(raw)


def _decode_write_batch(record: bytes) -> Iterator[tuple[bytes, bytes, int, bool]]:
    """Decode a WriteBatch payload: seq(8 LE) + count(4 LE) + entries."""
    if len(record) < 12:
        return
    seq_num = struct.unpack_from("<Q", record, 0)[0]
    count = struct.unpack_from("<I", record, 8)[0]
    pos = 12
    for _ in range(count):
        if pos >= len(record):
            break
        value_type = record[pos]
        pos += 1
        try:
            key_len, pos = decode_varint(record, pos)
            key = record[pos : pos + key_len]
            pos += key_len
            if value_type == 1:  # PUT
                val_len, pos = decode_varint(record, pos)
                value = record[pos : pos + val_len]
                pos += val_len
                yield key, value, seq_num, False
            elif value_type == 0:  # DELETE
                yield key, b"", seq_num, True
        except ValueError:
            break


def dump_directory(directory: str | Path) -> dict[str, str]:
    base = Path(directory)
    sources = []

    try:
        manifest_info = read_manifest(base)
    except FileNotFoundError:
        warnings.warn(
            f"No MANIFEST/CURRENT found in {base}, falling back to scanning all .ldb files",
            RuntimeWarning,
            stacklevel=2,
        )
        manifest_info = None

    if manifest_info is not None:
        for file_info in manifest_info.live_files:
            if file_info.path.exists():
                sources.append(read_sst_entries(file_info.path.read_bytes()))
        if manifest_info.log_number > 0:
            wal_path = base / f"{manifest_info.log_number:06d}.log"
            if wal_path.exists():
                wal_data = wal_path.read_bytes()
                sources.append([
                    entry
                    for record in read_records(wal_data)
                    for entry in _decode_write_batch(record)
                ])
    else:
        for ldb_file in sorted(base.rglob("*.ldb")):
            sources.append(read_sst_entries(ldb_file.read_bytes()))
        for log_file in sorted(base.rglob("*.log")):
            log_data = log_file.read_bytes()
            sources.append([
                entry
                for record in read_records(log_data)
                for entry in _decode_write_batch(record)
            ])

    merged = merge(sources)
    return {_to_text(k): _to_text(v) for k, v in merged.items()}
