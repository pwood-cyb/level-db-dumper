from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .reader import dump_directory
from .formats import serialize


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Dump key/value pairs from LevelDB .ldb files")
    parser.add_argument("directory", help="Directory where .ldb files are searched")
    parser.add_argument(
        "-f",
        "--format",
        dest="output_format",
        default="json",
        choices=["json", "xml", "yaml", "toml"],
        help="Output format",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="-",
        help="Output file name or '-' for stdout",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    data = dump_directory(args.directory)
    rendered = serialize(data, args.output_format)

    if args.output == "-":
        if any(ord(char) > 127 for char in rendered):
            print(
                "Warning: stdout output includes non-ASCII characters.",
                file=sys.stderr,
            )
        sys.stdout.write(rendered)
        return 0

    output_path = Path(args.output)
    output_path.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
