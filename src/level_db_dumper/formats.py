from __future__ import annotations

import json
from xml.sax.saxutils import escape


def _escape_yaml_toml(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def to_json(data: dict[str, str]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)


def to_xml(data: dict[str, str]) -> str:
    body = "".join(
        f"  <item><key>{escape(key)}</key><value>{escape(value)}</value></item>\n"
        for key, value in sorted(data.items())
    )
    return f"<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<leveldb>\n{body}</leveldb>\n"


def to_yaml(data: dict[str, str]) -> str:
    lines = [f"{_escape_yaml_toml(key)}: {_escape_yaml_toml(value)}" for key, value in sorted(data.items())]
    return "\n".join(lines) + ("\n" if lines else "")


def to_toml(data: dict[str, str]) -> str:
    lines = [f"{_escape_yaml_toml(key)} = {_escape_yaml_toml(value)}" for key, value in sorted(data.items())]
    return "\n".join(lines) + ("\n" if lines else "")


def serialize(data: dict[str, str], output_format: str) -> str:
    formatters = {
        "json": to_json,
        "xml": to_xml,
        "yaml": to_yaml,
        "toml": to_toml,
    }
    return formatters[output_format](data)
