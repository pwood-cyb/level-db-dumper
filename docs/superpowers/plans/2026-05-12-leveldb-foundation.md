# LevelDB Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the incorrect `dumper.py` extraction logic with a layered `ldb/` package that reads MANIFEST, WAL, and SST files correctly using sequence-number precedence.

**Architecture:** A `ldb/` sub-package provides four focused modules (`log`, `sst`, `manifest`, `merge`) plus two shared utilities (`_crc32c`, `_varint`). A new `reader.py` replaces `dumper.py` as a thin coordinator. The public API and CLI are unchanged.

**Tech Stack:** Python 3.10+, stdlib only (`struct`, `dataclasses`, `warnings`, `pathlib`). `pytest` for tests. `plyvel` as a Linux-only dev dependency for generating committed binary test fixtures.

**Spec:** `docs/superpowers/specs/2026-05-12-leveldb-foundation-design.md`

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `src/level_db_dumper/ldb/__init__.py` | Package marker (empty) |
| Create | `src/level_db_dumper/ldb/_crc32c.py` | CRC32C + masked CRC used by log and sst |
| Create | `src/level_db_dumper/ldb/_varint.py` | Varint encode/decode shared across ldb modules |
| Create | `src/level_db_dumper/ldb/log.py` | Log-record reader (WAL + MANIFEST) |
| Create | `src/level_db_dumper/ldb/sst.py` | SST entry reader (migrated + corrected from dumper.py) |
| Create | `src/level_db_dumper/ldb/manifest.py` | MANIFEST parser → live file set + WAL file number |
| Create | `src/level_db_dumper/ldb/merge.py` | Sequence-number merge across sources |
| Create | `src/level_db_dumper/reader.py` | WAL decoder + coordinator (replaces dumper.py) |
| Create | `tests/ldb/__init__.py` | Package marker (empty) |
| Create | `tests/ldb/helpers.py` | Binary builders for synthetic test data |
| Create | `tests/ldb/test_crc32c.py` | CRC32C unit tests |
| Create | `tests/ldb/test_log.py` | Log-record reader unit tests |
| Create | `tests/ldb/test_sst.py` | SST entry reader unit tests |
| Create | `tests/ldb/test_manifest.py` | MANIFEST parser unit tests |
| Create | `tests/ldb/test_merge.py` | Merge unit tests |
| Create | `tests/test_reader.py` | reader.py unit tests (replaces test_dumper_text.py) |
| Create | `scripts/generate_fixtures.py` | One-time fixture generator using plyvel (Linux/WSL) |
| Create | `tests/fixtures/` | Pre-committed binary LevelDB databases |
| Create | `tests/test_integration.py` | Integration tests against committed fixtures |
| Modify | `src/level_db_dumper/__init__.py` | Update import: `.dumper` → `.reader` |
| Modify | `src/level_db_dumper/cli.py` | Update import: `.dumper` → `.reader` |
| Delete | `src/level_db_dumper/dumper.py` | Replaced by reader.py + ldb/ |
| Delete | `tests/test_dumper_text.py` | Superseded by tests/test_reader.py |

---

## Task 1: ldb/ skeleton — `_crc32c.py` and `_varint.py`

**Files:**
- Create: `src/level_db_dumper/ldb/__init__.py`
- Create: `src/level_db_dumper/ldb/_crc32c.py`
- Create: `src/level_db_dumper/ldb/_varint.py`
- Create: `tests/ldb/__init__.py`
- Create: `tests/ldb/test_crc32c.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/ldb/test_crc32c.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/ldb/test_crc32c.py -v
```
Expected: `ImportError` or `ModuleNotFoundError`

- [ ] **Step 3: Create package markers**

```python
# src/level_db_dumper/ldb/__init__.py
```
```python
# tests/ldb/__init__.py
```

- [ ] **Step 4: Implement `_crc32c.py`**

```python
# src/level_db_dumper/ldb/_crc32c.py
from __future__ import annotations


def _build_table() -> list[int]:
    table = []
    for i in range(256):
        crc = i
        for _ in range(8):
            crc = (crc >> 1) ^ 0x82F63B78 if crc & 1 else crc >> 1
        table.append(crc)
    return table


_TABLE = _build_table()


def crc32c(data: bytes) -> int:
    crc = 0xFFFFFFFF
    for byte in data:
        crc = (crc >> 8) ^ _TABLE[(crc ^ byte) & 0xFF]
    return crc ^ 0xFFFFFFFF


def masked_crc32c(data: bytes) -> int:
    crc = crc32c(data)
    rotated = ((crc >> 15) | (crc << 17)) & 0xFFFFFFFF
    return (rotated + 0xa282ead8) & 0xFFFFFFFF
```

- [ ] **Step 5: Implement `_varint.py`**

```python
# src/level_db_dumper/ldb/_varint.py
from __future__ import annotations


def decode_varint(data: bytes, offset: int) -> tuple[int, int]:
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


def encode_varint(value: int) -> bytes:
    parts = []
    while value > 0x7F:
        parts.append((value & 0x7F) | 0x80)
        value >>= 7
    parts.append(value)
    return bytes(parts)
```

- [ ] **Step 6: Run tests to verify they pass**

```
pytest tests/ldb/test_crc32c.py -v
```
Expected: 4 PASSED

- [ ] **Step 7: Commit**

```
git add src/level_db_dumper/ldb/ tests/ldb/
git commit -m "feat: add ldb/ package skeleton with CRC32C and varint utilities"
```

---

## Task 2: `ldb/log.py` — log-record reader

**Files:**
- Create: `src/level_db_dumper/ldb/log.py`
- Create: `tests/ldb/test_log.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/ldb/test_log.py
import struct
import unittest
import warnings

from level_db_dumper.ldb._crc32c import masked_crc32c
from level_db_dumper.ldb.log import read_records

_TYPE_FULL = 1
_TYPE_FIRST = 2
_TYPE_LAST = 4


def _make_record(payload: bytes, record_type: int = _TYPE_FULL) -> bytes:
    crc = masked_crc32c(bytes([record_type]) + payload)
    return struct.pack("<IHB", crc, len(payload), record_type) + payload


class LogRecordReaderTests(unittest.TestCase):
    def test_full_record_yields_payload(self) -> None:
        data = _make_record(b"hello world")
        self.assertEqual(list(read_records(data)), [b"hello world"])

    def test_fragmented_record_reassembled(self) -> None:
        data = _make_record(b"hel", _TYPE_FIRST) + _make_record(b"lo", _TYPE_LAST)
        self.assertEqual(list(read_records(data)), [b"hello"])

    def test_bad_crc_skipped_with_warning(self) -> None:
        record = _make_record(b"good")
        # Corrupt the CRC (first 4 bytes)
        bad = b"\x00\x00\x00\x00" + record[4:]
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = list(read_records(bad))
        self.assertEqual(result, [])
        self.assertTrue(any("CRC" in str(w.message) for w in caught))

    def test_truncated_data_yields_nothing(self) -> None:
        # Only 3 bytes — not enough for a 7-byte header
        self.assertEqual(list(read_records(b"\x01\x02\x03")), [])

    def test_multiple_records(self) -> None:
        data = _make_record(b"first") + _make_record(b"second")
        self.assertEqual(list(read_records(data)), [b"first", b"second"])

    def test_block_padding_skipped(self) -> None:
        # Place a record, pad to near block boundary, place another record
        record = _make_record(b"after padding")
        block_size = 32768
        # Position the second record at exactly the start of block 1
        padding = b"\x00" * (block_size - len(_make_record(b"before")))
        data = _make_record(b"before") + padding + record
        result = list(read_records(data))
        self.assertIn(b"before", result)
        self.assertIn(b"after padding", result)
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/ldb/test_log.py -v
```
Expected: `ImportError`

- [ ] **Step 3: Implement `log.py`**

```python
# src/level_db_dumper/ldb/log.py
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
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/ldb/test_log.py -v
```
Expected: 6 PASSED

- [ ] **Step 5: Commit**

```
git add src/level_db_dumper/ldb/log.py tests/ldb/test_log.py
git commit -m "feat: add ldb/log.py record reader for WAL and MANIFEST files"
```

---

## Task 3: `ldb/sst.py` — SST entry reader + test helpers

**Files:**
- Create: `tests/ldb/helpers.py`
- Create: `src/level_db_dumper/ldb/sst.py`
- Create: `tests/ldb/test_sst.py`

- [ ] **Step 1: Create `tests/ldb/helpers.py`**

This module builds valid synthetic LevelDB binary structures used across unit tests.

```python
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
```

- [ ] **Step 2: Write the failing SST tests**

```python
# tests/ldb/test_sst.py
import unittest
import warnings

from level_db_dumper.ldb.sst import read_entries
from tests.ldb.helpers import make_sst


class SSTEntryReaderTests(unittest.TestCase):
    def test_single_put_entry(self) -> None:
        data = make_sst([(b"key", b"value", 1, False)])
        entries = list(read_entries(data))
        self.assertEqual(len(entries), 1)
        user_key, value, seq_num, is_deletion = entries[0]
        self.assertEqual(user_key, b"key")
        self.assertEqual(value, b"value")
        self.assertEqual(seq_num, 1)
        self.assertFalse(is_deletion)

    def test_deletion_tombstone_yielded(self) -> None:
        data = make_sst([(b"key", b"", 5, True)])
        entries = list(read_entries(data))
        self.assertEqual(len(entries), 1)
        user_key, value, seq_num, is_deletion = entries[0]
        self.assertEqual(user_key, b"key")
        self.assertEqual(seq_num, 5)
        self.assertTrue(is_deletion)

    def test_multiple_entries_in_order(self) -> None:
        pairs = [(b"aaa", b"1", 1, False), (b"bbb", b"2", 2, False), (b"ccc", b"3", 3, False)]
        data = make_sst(pairs)
        entries = list(read_entries(data))
        self.assertEqual(len(entries), 3)
        keys = [e[0] for e in entries]
        self.assertEqual(keys, [b"aaa", b"bbb", b"ccc"])

    def test_invalid_footer_returns_empty(self) -> None:
        self.assertEqual(list(read_entries(b"\x00" * 100)), [])

    def test_sequence_numbers_preserved(self) -> None:
        data = make_sst([(b"k", b"v", 42, False)])
        entries = list(read_entries(data))
        self.assertEqual(entries[0][2], 42)
```

- [ ] **Step 3: Run tests to verify they fail**

```
pytest tests/ldb/test_sst.py -v
```
Expected: `ImportError`

- [ ] **Step 4: Implement `sst.py`**

Migrate the parsing logic from `dumper.py`, change the interface to yield `(user_key, value, seq_num, is_deletion)` tuples, and add CRC32C validation.

```python
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
            return None
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
```

- [ ] **Step 5: Run tests to verify they pass**

```
pytest tests/ldb/test_sst.py -v
```
Expected: 5 PASSED

- [ ] **Step 6: Commit**

```
git add src/level_db_dumper/ldb/sst.py tests/ldb/helpers.py tests/ldb/test_sst.py
git commit -m "feat: add ldb/sst.py entry reader and test helpers"
```

---

## Task 4: `ldb/manifest.py` — MANIFEST parser

**Files:**
- Create: `src/level_db_dumper/ldb/manifest.py`
- Create: `tests/ldb/test_manifest.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/ldb/test_manifest.py
import tempfile
import unittest
from pathlib import Path

from level_db_dumper.ldb.manifest import read_manifest
from tests.ldb.helpers import (
    make_manifest,
    make_version_edit_deleted_file,
    make_version_edit_log_number,
    make_version_edit_new_file,
)


class ManifestParserTests(unittest.TestCase):
    def _write_db(self, tmp: str, manifest_data: bytes, log_number: int = 0) -> Path:
        base = Path(tmp)
        manifest_name = "MANIFEST-000001"
        (base / "CURRENT").write_text(manifest_name + "\n", encoding="utf-8")
        (base / manifest_name).write_bytes(manifest_data)
        return base

    def test_single_file_live(self) -> None:
        edit = make_version_edit_new_file(0, 5, 1024, b"aaa", b"zzz")
        manifest = make_manifest([edit])
        with tempfile.TemporaryDirectory() as tmp:
            base = self._write_db(tmp, manifest)
            info = read_manifest(base)
        self.assertEqual(len(info.live_files), 1)
        self.assertEqual(info.live_files[0].file_number, 5)
        self.assertEqual(info.live_files[0].level, 0)

    def test_add_then_delete_leaves_empty(self) -> None:
        add = make_version_edit_new_file(0, 3, 512, b"a", b"z")
        delete = make_version_edit_deleted_file(0, 3)
        manifest = make_manifest([add, delete])
        with tempfile.TemporaryDirectory() as tmp:
            base = self._write_db(tmp, manifest)
            info = read_manifest(base)
        self.assertEqual(info.live_files, [])

    def test_log_number_extracted(self) -> None:
        edit = make_version_edit_log_number(7)
        manifest = make_manifest([edit])
        with tempfile.TemporaryDirectory() as tmp:
            base = self._write_db(tmp, manifest)
            info = read_manifest(base)
        self.assertEqual(info.log_number, 7)

    def test_missing_current_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):
                read_manifest(Path(tmp))

    def test_l0_files_sorted_descending_by_file_number(self) -> None:
        edit1 = make_version_edit_new_file(0, 2, 512, b"a", b"m")
        edit2 = make_version_edit_new_file(0, 5, 512, b"a", b"m")
        manifest = make_manifest([edit1, edit2])
        with tempfile.TemporaryDirectory() as tmp:
            base = self._write_db(tmp, manifest)
            info = read_manifest(base)
        file_numbers = [f.file_number for f in info.live_files]
        self.assertEqual(file_numbers, [5, 2])
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/ldb/test_manifest.py -v
```
Expected: `ImportError`

- [ ] **Step 3: Implement `manifest.py`**

```python
# src/level_db_dumper/ldb/manifest.py
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ._varint import decode_varint
from .log import read_records


@dataclass
class FileInfo:
    level: int
    file_number: int
    path: Path


@dataclass
class ManifestInfo:
    live_files: list[FileInfo]
    log_number: int


@dataclass
class _VersionEdit:
    log_number: int | None = None
    new_files: list[tuple[int, int, int]] = field(default_factory=list)
    deleted_files: set[tuple[int, int]] = field(default_factory=set)


def _parse_version_edit(data: bytes) -> _VersionEdit:
    edit = _VersionEdit()
    pos = 0
    while pos < len(data):
        tag, pos = decode_varint(data, pos)
        if tag == 2:
            edit.log_number, pos = decode_varint(data, pos)
        elif tag == 6:
            level, pos = decode_varint(data, pos)
            fnum, pos = decode_varint(data, pos)
            edit.deleted_files.add((level, fnum))
        elif tag == 7:
            level, pos = decode_varint(data, pos)
            fnum, pos = decode_varint(data, pos)
            size, pos = decode_varint(data, pos)
            klen, pos = decode_varint(data, pos)
            pos += klen
            klen2, pos = decode_varint(data, pos)
            pos += klen2
            edit.new_files.append((level, fnum, size))
        else:
            break
    return edit


def read_manifest(db_path: Path) -> ManifestInfo:
    current_path = db_path / "CURRENT"
    if not current_path.exists():
        raise FileNotFoundError(f"CURRENT not found in {db_path}")
    manifest_name = current_path.read_text(encoding="utf-8").strip()
    manifest_data = (db_path / manifest_name).read_bytes()

    live: dict[tuple[int, int], int] = {}
    log_number = 0

    for record in read_records(manifest_data):
        try:
            edit = _parse_version_edit(record)
        except (ValueError, IndexError):
            continue
        if edit.log_number is not None:
            log_number = edit.log_number
        for level, fnum, size in edit.new_files:
            live[(level, fnum)] = size
        for key in edit.deleted_files:
            live.pop(key, None)

    files = [
        FileInfo(level=level, file_number=fnum, path=db_path / f"{fnum:06d}.ldb")
        for (level, fnum) in live
    ]
    files.sort(key=lambda f: (f.level, -f.file_number if f.level == 0 else f.file_number))

    return ManifestInfo(live_files=files, log_number=log_number)
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/ldb/test_manifest.py -v
```
Expected: 5 PASSED

- [ ] **Step 5: Commit**

```
git add src/level_db_dumper/ldb/manifest.py tests/ldb/test_manifest.py
git commit -m "feat: add ldb/manifest.py MANIFEST parser"
```

---

## Task 5: `ldb/merge.py` — sequence-number merge

**Files:**
- Create: `src/level_db_dumper/ldb/merge.py`
- Create: `tests/ldb/test_merge.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/ldb/test_merge.py
import unittest

from level_db_dumper.ldb.merge import merge


def _source(*entries: tuple[bytes, bytes, int, bool]):
    return iter(entries)


class MergeTests(unittest.TestCase):
    def test_single_source_single_key(self) -> None:
        result = merge([_source((b"k", b"v", 1, False))])
        self.assertEqual(result, {b"k": b"v"})

    def test_higher_seq_num_wins(self) -> None:
        s1 = _source((b"k", b"old", 1, False))
        s2 = _source((b"k", b"new", 5, False))
        result = merge([s1, s2])
        self.assertEqual(result[b"k"], b"new")

    def test_deletion_suppresses_key(self) -> None:
        s1 = _source((b"k", b"v", 1, False))
        s2 = _source((b"k", b"", 2, True))
        result = merge([s1, s2])
        self.assertNotIn(b"k", result)

    def test_lower_seq_deletion_does_not_suppress_newer_put(self) -> None:
        s1 = _source((b"k", b"", 1, True))
        s2 = _source((b"k", b"v", 5, False))
        result = merge([s1, s2])
        self.assertEqual(result[b"k"], b"v")

    def test_empty_sources(self) -> None:
        self.assertEqual(merge([]), {})

    def test_multiple_keys_independent(self) -> None:
        s1 = _source((b"a", b"1", 1, False), (b"b", b"2", 1, False))
        result = merge([s1])
        self.assertEqual(result, {b"a": b"1", b"b": b"2"})
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/ldb/test_merge.py -v
```
Expected: `ImportError`

- [ ] **Step 3: Implement `merge.py`**

```python
# src/level_db_dumper/ldb/merge.py
from __future__ import annotations

from collections.abc import Iterable, Iterator


def merge(
    sources: Iterable[Iterator[tuple[bytes, bytes, int, bool]]],
) -> dict[bytes, bytes]:
    best: dict[bytes, tuple[bytes, int, bool]] = {}
    for source in sources:
        for user_key, value, seq_num, is_deletion in source:
            current = best.get(user_key)
            if current is None or seq_num > current[1]:
                best[user_key] = (value, seq_num, is_deletion)
    return {k: v for k, (v, _, is_del) in best.items() if not is_del}
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/ldb/test_merge.py -v
```
Expected: 6 PASSED

- [ ] **Step 5: Commit**

```
git add src/level_db_dumper/ldb/merge.py tests/ldb/test_merge.py
git commit -m "feat: add ldb/merge.py sequence-number-aware merge"
```

---

## Task 6: `reader.py` — WAL decoder and coordinator

**Files:**
- Create: `src/level_db_dumper/reader.py`
- Create: `tests/test_reader.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_reader.py
import tempfile
import unittest
from pathlib import Path

from level_db_dumper.reader import _to_text, dump_directory
from tests.ldb.helpers import (
    make_log_record,
    make_manifest,
    make_sst,
    make_version_edit_log_number,
    make_version_edit_new_file,
)
import struct
from level_db_dumper.ldb._varint import encode_varint
from level_db_dumper.ldb._crc32c import masked_crc32c


def _make_write_batch(seq_num: int, entries: list[tuple[bytes, bytes | None]]) -> bytes:
    """Build a WriteBatch payload: seq(8) + count(4) + entries."""
    payload = struct.pack("<QI", seq_num, len(entries))
    for key, value in entries:
        if value is None:
            payload += bytes([0]) + encode_varint(len(key)) + key
        else:
            payload += bytes([1]) + encode_varint(len(key)) + key
            payload += encode_varint(len(value)) + value
    return payload


class ToTextTests(unittest.TestCase):
    def test_preserves_utf8_text(self) -> None:
        self.assertEqual(_to_text("väl".encode("utf-8")), "väl")

    def test_escapes_control_bytes(self) -> None:
        self.assertIn("\\x00", _to_text(b"\x00"))

    def test_empty_bytes(self) -> None:
        self.assertEqual(_to_text(b""), "")


class DumpDirectoryTests(unittest.TestCase):
    def _write_db(
        self, tmp: str, sst_data: bytes, file_num: int = 3, log_data: bytes | None = None, log_num: int = 0
    ) -> Path:
        base = Path(tmp)
        ldb_path = base / f"{file_num:06d}.ldb"
        ldb_path.write_bytes(sst_data)
        edits = [make_version_edit_new_file(0, file_num, len(sst_data), b"a", b"z")]
        if log_num:
            edits.append(make_version_edit_log_number(log_num))
        manifest = make_manifest(edits)
        (base / "CURRENT").write_text("MANIFEST-000001\n", encoding="utf-8")
        (base / "MANIFEST-000001").write_bytes(manifest)
        if log_data is not None and log_num:
            (base / f"{log_num:06d}.log").write_bytes(log_data)
        return base

    def test_reads_single_sst(self) -> None:
        sst = make_sst([(b"hello", b"world", 1, False)])
        with tempfile.TemporaryDirectory() as tmp:
            base = self._write_db(tmp, sst)
            result = dump_directory(base)
        self.assertEqual(result, {"hello": "world"})

    def test_deletion_excluded_from_output(self) -> None:
        sst = make_sst([(b"gone", b"", 1, True)])
        with tempfile.TemporaryDirectory() as tmp:
            base = self._write_db(tmp, sst)
            result = dump_directory(base)
        self.assertNotIn("gone", result)

    def test_wal_entries_included(self) -> None:
        # SST has old value, WAL has newer value for same key
        sst = make_sst([(b"key", b"old", 1, False)])
        batch = _make_write_batch(10, [(b"key", b"new")])
        wal = make_log_record(batch)
        with tempfile.TemporaryDirectory() as tmp:
            base = self._write_db(tmp, sst, log_data=wal, log_num=9)
            result = dump_directory(base)
        self.assertEqual(result["key"], "new")

    def test_fallback_when_no_manifest(self) -> None:
        sst = make_sst([(b"fb", b"val", 1, False)])
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "000001.ldb").write_bytes(sst)
            import warnings
            with warnings.catch_warnings(record=True):
                warnings.simplefilter("always")
                result = dump_directory(tmp)
        self.assertIn("fb", result)
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_reader.py -v
```
Expected: `ImportError`

- [ ] **Step 3: Implement `reader.py`**

Copy `_escape_controls`, `_escape_binary`, `_is_mostly_printable`, and `_to_text` verbatim from `dumper.py`. Then add the WAL decoder and coordinator below them.

```python
# src/level_db_dumper/reader.py
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


def _escape_controls(text: str) -> str:
    escaped = []
    for char in text:
        cp = ord(char)
        if cp == 10:
            escaped.append("\\n")
        elif cp == 13:
            escaped.append("\\r")
        elif cp == 9:
            escaped.append("\\t")
        elif cp < 32 or cp == 127:
            escaped.append(f"\\x{cp:02x}")
        else:
            escaped.append(char)
    return "".join(escaped)


def _escape_binary(raw: bytes) -> str:
    escaped = []
    for byte in raw:
        if byte == 10:
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


def _is_mostly_printable(text: str) -> bool:
    if not text:
        return True
    printable = sum(1 for c in text if ord(c) >= 32 and ord(c) != 127)
    return printable / len(text) >= 0.8


def _to_text(raw: bytes) -> str:
    if not raw:
        return ""
    if len(raw) % 2 == 0 and len(raw) >= 4:
        try:
            utf16_text = raw.decode("utf-16-le")
            if _is_mostly_printable(utf16_text):
                return _escape_controls(utf16_text)
        except UnicodeDecodeError:
            pass
    try:
        utf8_text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return _escape_binary(raw)
    if _is_mostly_printable(utf8_text):
        return _escape_controls(utf8_text)
    return _escape_binary(raw)


def _decode_write_batch(record: bytes) -> Iterator[tuple[bytes, bytes, int, bool]]:
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
            if value_type == 1:
                val_len, pos = decode_varint(record, pos)
                value = record[pos : pos + val_len]
                pos += val_len
                yield key, value, seq_num, False
            elif value_type == 0:
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
                sources.append(
                    entry
                    for record in read_records(wal_data)
                    for entry in _decode_write_batch(record)
                )
    else:
        for ldb_file in sorted(base.rglob("*.ldb")):
            sources.append(read_sst_entries(ldb_file.read_bytes()))

    merged = merge(sources)
    return {_to_text(k): _to_text(v) for k, v in merged.items()}
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_reader.py -v
```
Expected: 7 PASSED

- [ ] **Step 5: Commit**

```
git add src/level_db_dumper/reader.py tests/test_reader.py
git commit -m "feat: add reader.py coordinator with WAL decode and MANIFEST-driven extraction"
```

---

## Task 7: Fixture generation and integration tests

**Files:**
- Create: `scripts/generate_fixtures.py`
- Create: `tests/fixtures/` (committed binary directories — run script first)
- Create: `tests/test_integration.py`

> **Note:** `generate_fixtures.py` requires `plyvel`, which is available on Linux only. Run it on Linux or via WSL, then commit the resulting `tests/fixtures/` directories. Once committed, `test_integration.py` runs on all platforms without plyvel.

- [ ] **Step 1: Create `scripts/generate_fixtures.py`**

```python
#!/usr/bin/env python3
"""
Generate binary LevelDB test fixtures using plyvel.

Requirements: pip install plyvel  (Linux only)
Run from repo root: python scripts/generate_fixtures.py

Writes to tests/fixtures/ — commit the results.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import plyvel  # type: ignore

FIXTURES = Path(__file__).parent.parent / "tests" / "fixtures"


def _make(name: str) -> Path:
    path = FIXTURES / name
    shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True)
    return path


def generate_single_sst() -> None:
    path = _make("single_sst")
    db = plyvel.DB(str(path), create_if_missing=True)
    db.put(b"alpha", b"one")
    db.put(b"beta", b"two")
    db.put(b"gamma", b"three")
    db.close()


def generate_with_deletions() -> None:
    path = _make("with_deletions")
    db = plyvel.DB(str(path), create_if_missing=True)
    db.put(b"keep", b"yes")
    db.put(b"remove", b"temp")
    db.delete(b"remove")
    db.close()


def generate_wal_unflushed() -> None:
    """Write data that remains in the WAL (not compacted to SST)."""
    path = _make("wal_unflushed")
    # open with sync=False so writes go to WAL without immediate flush to SST
    db = plyvel.DB(str(path), create_if_missing=True)
    db.put(b"wal_key", b"wal_value")
    # Close without explicit compaction — data may remain in WAL
    db.close()


if __name__ == "__main__":
    FIXTURES.mkdir(parents=True, exist_ok=True)
    generate_single_sst()
    generate_with_deletions()
    generate_wal_unflushed()
    print(f"Fixtures written to {FIXTURES}")
```

- [ ] **Step 2: Run `generate_fixtures.py` on Linux or WSL**

```bash
pip install plyvel
python scripts/generate_fixtures.py
```

Expected output:
```
Fixtures written to tests/fixtures/
```

Verify the directories were created:
```bash
ls tests/fixtures/
# single_sst/  with_deletions/  wal_unflushed/
```

- [ ] **Step 3: Write `tests/test_integration.py`**

```python
# tests/test_integration.py
import unittest
from pathlib import Path

from level_db_dumper.reader import dump_directory

FIXTURES = Path(__file__).parent / "fixtures"


@unittest.skipUnless((FIXTURES / "single_sst").exists(), "fixtures not generated")
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
```

- [ ] **Step 4: Run integration tests**

```
pytest tests/test_integration.py -v
```

If fixtures exist: Expected: 3 PASSED.
If fixtures don't exist yet (no plyvel): Expected: 3 SKIPPED (this is correct — tests skip gracefully).

- [ ] **Step 5: Commit**

```
git add scripts/generate_fixtures.py tests/test_integration.py tests/fixtures/
git commit -m "test: add fixture generation script and integration tests"
```

---

## Task 8: Migration — update imports, remove old files

**Files:**
- Modify: `src/level_db_dumper/__init__.py`
- Modify: `src/level_db_dumper/cli.py`
- Delete: `src/level_db_dumper/dumper.py`
- Delete: `tests/test_dumper_text.py`

- [ ] **Step 1: Update `__init__.py`**

Open `src/level_db_dumper/__init__.py`. Change:
```python
from .dumper import dump_directory
```
to:
```python
from .reader import dump_directory
```

- [ ] **Step 2: Update `cli.py`**

Open `src/level_db_dumper/cli.py`. Change:
```python
from .dumper import dump_directory
```
to:
```python
from .reader import dump_directory
```

- [ ] **Step 3: Run the full test suite to confirm nothing is broken**

```
pytest -v
```

Expected: all existing tests (`test_cli.py`, `test_formats.py`) PASS alongside all new tests. `test_dumper_text.py` will fail because `_to_text` is now in `reader.py` — that's expected; we'll delete it in the next step.

- [ ] **Step 4: Delete superseded files**

```
git rm src/level_db_dumper/dumper.py
git rm tests/test_dumper_text.py
```

- [ ] **Step 5: Run the full test suite again**

```
pytest -v
```

Expected: all tests PASS, no failures.

- [ ] **Step 6: Final commit**

```
git add src/level_db_dumper/__init__.py src/level_db_dumper/cli.py
git commit -m "feat: complete ldb/ foundation — replace dumper.py with correct MANIFEST+WAL+merge pipeline"
```

---

## Self-review checklist

- [x] `log.py` — log record reader: Task 2
- [x] `sst.py` — SST entry reader with CRC32C: Task 3
- [x] `manifest.py` — MANIFEST parser, CURRENT lookup, FileNotFoundError: Task 4
- [x] `merge.py` — highest seq wins, deletion suppresses: Task 5
- [x] `reader.py` — WAL decoder, coordinator, fallback path: Task 6
- [x] `_crc32c.py` and `_varint.py` shared utilities: Task 1
- [x] Integration tests with committed fixtures: Task 7
- [x] Migration: imports updated, dumper.py deleted: Task 8
- [x] `_to_text` and helpers moved to `reader.py`, tested in `test_reader.py`: Task 6
- [x] Fallback path (no MANIFEST) emits warning and scans .ldb files: Task 6 `test_fallback_when_no_manifest`
