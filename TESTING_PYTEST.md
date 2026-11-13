# ChemsPC pytest suite

The suite covers the current Flask application, SQLite persistence, native save
handlers, and generation-aware display labels. Synthetic fixtures and temporary
databases keep tests independent of your collection and game saves.

## Install and run

From the repository root:

```bash
python -m pip install -r requirements-dev.txt
PYTHONPATH=..:. python -m pytest
```

Run a focused group with:

```bash
python -m pytest tests/test_main.py -q
python -m pytest tests/test_db.py -q
python -m pytest tests/test_generation_handlers.py -q
```

## Workflow coverage

`test_main.py` exercises Flask's test client with real sessions, CSRF validation,
selection validation, and a temporary SQLite database. Only native parsing and
writing are replaced at the save-format boundary. Every supported title is
covered for upload normalization and selective import/export finalization.
Failure tests verify rollback, output cleanup, and retention of the staged source.
Result and download tests verify session ownership.

`test_db.py` uses the current `insert_pokemon(connection, pokemon)` API with
caller-owned transactions. It checks commit/rollback behavior, including multiple
imports in one transaction, rather than the removed CLI batch-insert API.

`test_generation_handlers.py` tests parser boundaries, registry routing, and
Generation II checksum-aware output. Other format regression tests exercise
native record parsing/writing directly.

## Optional real-save fixtures

Most tests require no external files. The real-save checks are skipped unless
`CHEMSPC_FIRERED_FIXTURE` or `CHEMSPC_PLATINUM_FIXTURE` points to the expected
fixture. See the README and the corresponding test modules for fixture details.
These skips do not indicate test failures. Synthetic checks do not replace
validation of generated saves with known-good backups and an emulator.
