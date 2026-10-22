# chemspc pytest suite

This directory is a pytest replacement for the repository's existing `tests/` folder. It is designed to run without retail game saves or a real database file: tests use temporary files/SQLite databases and mocks for the extraction workflow.

## Install and run

From the repository root:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest
```

Run a focused group with:

```bash
python -m pytest tests/test_main.py -q
python -m pytest tests/test_db.py -q
python -m pytest tests/test_generation_handlers.py -q
```

## Applying this replacement

Back up or rename the old `tests/` directory, then copy this bundle's `tests/` directory and `pytest.ini` into the repository root. Keep `requirements-dev.txt` at the root alongside the existing `requirements.txt`.

## Important integration check

`test_db.py` contains a test that requires `db.add_pokemon_batch` because `main.py` imports and calls that function to commit an extraction atomically. In the public source snapshot inspected while preparing this suite, `db.py` did not expose `add_pokemon_batch`; if that is also true in your checkout, this test is expected to fail until the application/database API is brought back into sync. The main-workflow tests use a temporary import shim only when that helper is absent, so other CLI/workflow assertions can still run and report independently.

These are synthetic regression tests, not a substitute for validating a generated `.new` save with backups, a known-good retail save, and an emulator.
