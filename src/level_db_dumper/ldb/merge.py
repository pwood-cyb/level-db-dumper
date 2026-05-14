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
