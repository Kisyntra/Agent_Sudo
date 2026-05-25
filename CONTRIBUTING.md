# Contributing

## Run Tests

```bash
python3 -m unittest discover -s tests
```

Run the personal-data scanner before opening a pull request:

```bash
python3 scripts/check_no_personal_data.py
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
