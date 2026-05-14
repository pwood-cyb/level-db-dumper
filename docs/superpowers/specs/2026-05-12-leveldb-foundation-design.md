# LevelDB Dumper — Solid Foundation Design

**Date:** 2026-05-12
**Branch:** copilot/build-leveldb-dumper
**Status:** Approved

## Problem

The current implementation reads `.ldb` SST files directly but has several correctness gaps:

- Cross-file merge uses "first write wins" instead of sequence-number precedence
- MANIFEST is not read, so garbage-collected or obsolete files may be included
- WAL `.log` files (unflushed writes) are ignored entirely
- No CRC32c block validation
- No integration tests against real LevelDB binary fixtures

## Goal

Produce correct output for any valid LevelDB database directory, and prove correctness via integration tests backed by externally-generated binary fixtures.

## Non-Goals

- Streaming / memory-efficient output (noted as future work in README)
- Runtime dependency on native LevelDB bindings
- Supporting non-standard LevelDB forks with incompatible formats

## Architecture

Approach B: layered internal package. The `ldb/` sub-package owns all binary parsing. `reader.py` (replacing `dumper.py`) is a thin coordinator. Everything above `ldb/` — `formats.py`, `cli.py`, `__init__.py` — is unchanged except import paths.

```
level_db_dumper/
  ldb/
    __init__.py     # exports read_database for internal use
    log.py          # log-record reader shared by WAL + MANIFEST
    sst.py          # SST (.ldb) block/entry reader
    manifest.py     # MANIFEST parser → live file set + WAL file number
    merge.py        # sequence-number-aware merge across all sources
  __init__.py       # re-exports dump_directory from reader.py
  reader.py         # replaces dumper.py; coordinates ldb/ → dict[str, str]
  formats.py        # unchanged
  cli.py            # unchanged (import path updated)
```

### Data flow

```
CURRENT → MANIFEST → manifest.py → live file list + log_number
                                         │
              WAL .log ──→ log.py ───────┤
              .ldb files → sst.py ───────┴──→ merge.py → reader.py → formats.py
```

The public API (`dump_directory(directory)`) and CLI are unchanged.

## Component Specifications

### `ldb/log.py`

Reads LevelDB's shared log format, used by both WAL files and the MANIFEST.

**Format:** File is a sequence of 32 KB blocks. Each record has a 7-byte header: `crc32c (u32 LE) | length (u16 LE) | type (u8)`. Type values: `FULL=1`, `FIRST=2`, `MIDDLE=3`, `LAST=4`. Records spanning multiple blocks are reassembled from FIRST/MIDDLE/LAST fragments.

**Interface:**
```python
def read_records(data: bytes) -> Iterator[bytes]
```

Validates CRC32c per record. Corrupt or truncated records are skipped with a `warnings.warn` (WAL files can be partially written at crash time — expected, not fatal).

### `ldb/sst.py`

Reads SST (`.ldb`) files. Extracts all key/value entries including deletions. Largely migrated from the existing `dumper.py` parsing logic, with CRC32c validation added and the internal key suffix correctly decoded.

**Interface:**
```python
def read_entries(data: bytes) -> Iterator[tuple[bytes, bytes, int, bool]]
#                                          user_key, value, seq_num, is_deletion
```

Internally: parse footer (48 bytes, magic `0xdb4775248b80fb57`) → read index block → iterate data blocks → decode delta-compressed entries → strip 8-byte internal key suffix extracting `seq_num = tag >> 8` and `value_type = tag & 0xFF`. Yields entries for both `value_type=1` (put) and `value_type=0` (deletion tombstone, `is_deletion=True`).

CRC32c validation is performed in `_read_block`. Blocks failing validation are skipped with a warning.

### `ldb/manifest.py`

Parses the MANIFEST to determine which `.ldb` files are live and which WAL file holds unflushed data.

**Format:** MANIFEST is a log file (read via `log.py`). Each record payload is a `VersionEdit`: a sequence of tag-prefixed varint/string fields.

Relevant tags:

| Tag | Field |
|-----|-------|
| 2 | `LogNumber` — active WAL file number |
| 4 | `NextFileNumber` |
| 6 | `DeletedFile(level, file_number)` |
| 7 | `NewFile(level, file_number, size, smallest_key, largest_key)` |

All `VersionEdit`s are replayed in order (adds and removes) to produce the final live set.

**Interface:**
```python
@dataclass
class FileInfo:
    level: int
    file_number: int
    path: Path

@dataclass
class ManifestInfo:
    live_files: list[FileInfo]   # L0 sorted desc by file_number; L1+ sorted asc by key range
    log_number: int              # WAL file number (0 if none)

def read_manifest(db_path: Path) -> ManifestInfo
```

`CURRENT` file names the active MANIFEST (`MANIFEST-{N}`). If `CURRENT` or MANIFEST is absent, raises `FileNotFoundError` (caller in `reader.py` catches this and falls back).

### `ldb/merge.py`

Merges entries from all sources into a single correct view using sequence-number precedence.

**Interface:**
```python
def merge(
    sources: Iterable[Iterator[tuple[bytes, bytes, int, bool]]]
) -> dict[bytes, bytes]
```

Algorithm:
1. Iterate all sources, maintaining `best: dict[bytes, tuple[bytes, int, bool]]` keyed by `user_key`
2. For each entry, keep it if `seq_num > best[user_key].seq_num` (or key not yet seen)
3. After all sources exhausted, filter out entries where `is_deletion=True`
4. Return `dict[bytes, bytes]`

Correct for L0 overlapping key ranges because sequence numbers are globally monotonic — the highest sequence number is always the most recent write regardless of which file it came from.

### `reader.py`

Thin coordinator replacing `dumper.py`. Public API unchanged.

```python
def dump_directory(directory: str | Path) -> dict[str, str]
```

Flow:
1. `manifest.read_manifest(db_path)` → `ManifestInfo`
2. For each file in `ManifestInfo.live_files`: `sst.read_entries(file_data)`
3. Read WAL: `log.read_records(wal_data)` → decode write-batch payloads → yield `(user_key, value, seq_num, is_deletion)` tuples. Write-batch payload format: `sequence_number (u64 LE) | count (u32 LE)` followed by `count` entries each `value_type (u8) | key_len (varint) | key_data | [value_len (varint) | value_data]` (value absent when `value_type=0`).
4. `merge.merge(all_iterators)` → `dict[bytes, bytes]`
5. `{_to_text(k): _to_text(v) for k, v in merged.items()}`

Fallback: if `read_manifest` raises `FileNotFoundError`, fall back to reading all `.ldb` files in the directory sorted by filename (current behaviour), with a `warnings.warn`.

`_to_text` moves here from `dumper.py` unchanged.

## Testing Strategy

### Unit tests

Each `ldb/` module tested in isolation with synthetic binary data constructed in the test.

- `test_log.py`: full record, fragmented record across blocks, corrupt CRC skipped, truncated block at EOF
- `test_sst.py`: single data block, multi-block file, deletion tombstone yielded, varint edge cases, CRC failure skipped
- `test_manifest.py`: add/remove replay produces correct live set, `CURRENT` lookup, missing CURRENT raises `FileNotFoundError`
- `test_merge.py`: highest seq wins over lower seq, deletion suppresses key, L0 overlap resolved correctly, empty sources

### Integration tests

`tests/fixtures/` contains pre-built binary LevelDB databases committed to the repository. A one-time generation script at `scripts/generate_fixtures.py` uses `plyvel` to write known data and produces the fixture directories.

`plyvel` is listed as an optional `dev` dependency used only for fixture generation, not at runtime.

Fixture scenarios:

| Fixture | What it tests |
|---------|--------------|
| `single_sst/` | Basic read: single SST, no WAL |
| `multi_level/` | L0 overlap: two L0 files with same key at different seq nums |
| `with_deletions/` | Tombstone: key written then deleted, must not appear in output |
| `snappy_compressed/` | Snappy block decompression |
| `wal_unflushed/` | WAL: key written but not yet compacted to SST |

Integration tests call `dump_directory()` on each fixture and assert exact `dict[str, str]` output.

## Migration

- `dumper.py` → `reader.py` (rename + replace internals)
- `__init__.py`: update import `from .dumper` → `from .reader`
- `cli.py`: update import `from .dumper` → `from .reader`
- All existing tests continue to pass without modification
