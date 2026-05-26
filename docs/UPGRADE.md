# Upgrading agent-sudo

This guide describes how to upgrade `agent-sudo` safely, how to use the automated local upgrade command, and how to verify version consistency after an upgrade.

---

## Safety Guarantees
* **Local State Preservation**: Upgrading `agent-sudo` does **not** touch, modify, or delete any local databases, configuration states, or logs stored under your home configuration folder:
  ```text
  ~/.agent-sudo/
  ```
  Your approval passphrase hash, pending approvals database, active delegation tokens, and tamper-resistant audit logs are fully preserved.

---

## 1. Automated Local Upgrade (`upgrade-local`)

If you have installed `agent-sudo` via a Git clone as an editable development install, you can upgrade the package using the native CLI command:

### Check for available updates
Run the check command to fetch remote tags and compare them against your current version without making changes to the working tree:
```bash
agent-sudo upgrade-local --check
```

### Perform the upgrade
To pull the latest commits and reinstall the package automatically:
```bash
agent-sudo upgrade-local
```

### Options
* `--check`: Checks for upgrades without performing any repository updates.
* `--allow-dirty`: Ignores uncommitted changes in the Git working tree. By default, the upgrade halts if uncommitted changes are detected.

*Note: After upgrading the MCP server backend, you must restart your MCP client (such as Claude Desktop, Cursor, Hermes, or OpenClaw) for the changes to take effect.*

---

## 2. Manual Upgrade

If you are not inside a Git clone, or prefer standard `pip` updates:

### System-wide editable/install upgrade
Pull updates in your Git checkout and run:
```bash
git fetch --tags
git pull
python3 -m pip install -e .
```

### Standard package upgrade via PyPI
If you installed the package via a standard release package:
```bash
python3 -m pip install --upgrade agent-sudo
```

---

## 3. Virtual Environment (venv) Upgrades

If `agent-sudo` is installed inside a Python virtual environment:
1. Activate the environment:
   ```bash
   . /path/to/venv/bin/activate
   ```
2. Verify you are using the correct Python interpreter:
   ```bash
   which agent-sudo
   ```
3. Run the upgrade command:
   ```bash
   agent-sudo upgrade-local
   ```
   *(The command automatically routes installation via the active Python interpreter).*

---

## 4. Troubleshooting: Old Version Still Showing

If you upgraded but the CLI version (e.g. `agent-sudo --version`) or MCP initialization reports the old version:
1. **Multiple Python Environments**: Check if you have multiple copies installed globally and in venvs:
   ```bash
   which -a agent-sudo
   ```
   Ensure you run the pip install in the exact environment you intend to use.
2. **Pip Cache**: Force reinstall without caching:
   ```bash
   python3 -m pip install --no-cache-dir -e .
   ```
3. **Forgotten Restart**: Ensure the background MCP server process (e.g., Claude Desktop background runner) is completely terminated and restarted.
