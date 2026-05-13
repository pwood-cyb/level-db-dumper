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
        if tag == 2:  # LogNumber
            edit.log_number, pos = decode_varint(data, pos)
        elif tag == 6:  # DeletedFile: level + file_number
            level, pos = decode_varint(data, pos)
            fnum, pos = decode_varint(data, pos)
            edit.deleted_files.add((level, fnum))
        elif tag == 7:  # NewFile: level + file_num + size + smallest_key + largest_key
            level, pos = decode_varint(data, pos)
            fnum, pos = decode_varint(data, pos)
            size, pos = decode_varint(data, pos)
            klen, pos = decode_varint(data, pos)
            pos += klen  # skip smallest_key bytes
            klen2, pos = decode_varint(data, pos)
            pos += klen2  # skip largest_key bytes
            edit.new_files.append((level, fnum, size))
        elif tag in (3, 4, 9):  # NextFileNumber, LastSequence, PrevLogNumber: single varint
            _, pos = decode_varint(data, pos)
        elif tag == 1:  # Comparator: length-prefixed string
            slen, pos = decode_varint(data, pos)
            pos += slen
        elif tag == 5:  # CompactPointer: varint level + length-prefixed internal key
            _, pos = decode_varint(data, pos)  # skip level
            klen, pos = decode_varint(data, pos)
            pos += klen
        else:
            break  # truly unknown tag — cannot determine payload size
    return edit


def read_manifest(db_path: Path) -> ManifestInfo:
    current_path = db_path / "CURRENT"
    if not current_path.exists():
        raise FileNotFoundError(f"CURRENT not found in {db_path}")
    manifest_name = current_path.read_text(encoding="utf-8").strip()
    manifest_data = (db_path / manifest_name).read_bytes()

    live: dict[tuple[int, int], int] = {}  # (level, fnum) -> size
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
    # L0: descending by file_number (newer files first); L1+: ascending by file_number
    files.sort(key=lambda f: (f.level, -f.file_number if f.level == 0 else f.file_number))

    return ManifestInfo(live_files=files, log_number=log_number)
