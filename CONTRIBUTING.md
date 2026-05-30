# Contributing

## Development Setup

Install the project in editable mode so local changes are picked up immediately.
The `dev` extra adds the tooling used below (`pytest`, `ruff`):

```bash
python3 -m pip install -e ".[dev]"
```

## Run Tests

Run the test suite with either runner; both collect only the project tests under `tests/`:

```bash
pytest
```

```bash
python3 -m unittest discover -s tests
```

Run the personal-data scanner before opening a pull request:

```bash
python3 scripts/check_no_personal_data.py
```

## Lint

CI enforces formatting and linting with `ruff`. Run the same checks locally before opening a pull request:

```bash
ruff format --check .
ruff check .
```

To apply fixes automatically:

```bash
ruff format .
ruff check --fix .
```

## Run the MCP Server Locally

Start the stdio MCP server from a source checkout (after the editable install above):

```bash
agent-sudo-mcp
```

Or run it directly as a module without installing the console script:

```bash
python3 -m agent_sudo.mcp_server
```

## Test and Example Data

Do not add personal data to tests, examples, docs, or config files.
Use fake fixtures only.

Allowed placeholder patterns include:

- `user`
- `username`
- `/home/user/example`
- `~/example`
- `agent-a`
- `agent-b`
- `recipient@example.invalid`

Avoid real names, real emails, real employer names, real home directories, real auth paths, and real local project names.

## Local Files

Do not commit personal policy files, auth files, audit logs, local config, delegation state, or generated runtime data.
These belong under local ignored paths such as `.agent-sudo/` or `~/.agent-sudo/`.
