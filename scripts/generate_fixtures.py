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
    path = _make("wal_unflushed")
    db = plyvel.DB(str(path), create_if_missing=True)
    db.put(b"wal_key", b"wal_value")
    db.close()


if __name__ == "__main__":
    FIXTURES.mkdir(parents=True, exist_ok=True)
    generate_single_sst()
    generate_with_deletions()
    generate_wal_unflushed()
    print(f"Fixtures written to {FIXTURES}")
