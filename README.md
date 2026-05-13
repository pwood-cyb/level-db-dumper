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

## Running tests in Docker

Tests run against a specific LevelDB version built from source. Docker and Docker Compose are required.

Run all configured versions:

```bash
docker compose up --build
```

Run a single version:

```bash
docker compose run --rm --build test-leveldb-1.23
```

Run against an arbitrary version:

```bash
docker build --build-arg LEVELDB_VERSION=1.21 -f Dockerfile.test -t ldb-test:1.21 .
docker run --rm ldb-test:1.21
```

Configured versions in `compose.yml`: `1.20`, `1.22`, `1.23`.

To add a new version, add a service entry to `compose.yml` following the existing pattern.

## Future work

- **Streaming output** — replace the in-memory `dict` accumulation with an iterator-based pipeline so that multi-GB databases can be dumped without loading all key/value pairs into memory at once.
