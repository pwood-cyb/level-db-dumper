# level-db-dumper

A LevelDB dumper written in Python.

## Usage

```bash
level-db-dumper /path/to/db --format json --output dump.json
```

Supported output formats: `json`, `xml`, `yaml`, `toml`.

Use `-` to write to stdout:

```bash
level-db-dumper /path/to/db --format yaml --output -
```

## Run as a uv tool

After install, run it as:

```bash
uv tool run level-db-dumper /path/to/db --format toml --output dump.toml
```

## Future work

- **Streaming output** — replace the in-memory `dict` accumulation with an iterator-based pipeline so that multi-GB databases can be dumped without loading all key/value pairs into memory at once.
