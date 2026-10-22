# ChemSPC Flask transfer workflow

This is a drop-in source update for the existing `chemlibrary/chemspc` checkout. Copy/overlay these files into the repository root, keeping the existing `LICENSE` and `chemspc.db` in place:

- Replace `main.py`, `db.py`, `gen2.py`, `pokemon.py`, `requirements.txt`, and `pyproject.toml`.
- Add `templates/`, `static/`, and `tests/` from this package.

## Run locally

Use Python 3.10+ and install the dependencies:

```bash
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
python main.py
```

Open http://127.0.0.1:5000. The server binds to localhost by default because uploaded save files should not be exposed to other machines. Set `CHEMSPC_DATABASE` to select a database path, `CHEMSPC_SECRET_KEY` to set a stable Flask session secret, and optionally `CHEMSPC_HOST` / `CHEMSPC_PORT` to override the bind address and port.

## Transfer behavior

1. Upload a raw **32,768-byte English Pokémon Gold or Silver** save.
2. Select any save Pokémon to import and any compatible active database Pokémon to export.
3. Press **Finalize transfer** to apply the database changes and create a modified `.sav` download.

Uploads and generated files are stored under the local `instance/` directory; do not commit that directory. The original uploaded save is never overwritten. Selected imports are inserted into `pokemon` and removed from the generated save. Selected exports are removed from `pokemon`, inserted into `inactive_pokemon` with the same UID, and added to the generated save. Records with usable stored party stats use an open party slot; records imported from boxes have no calculated party stats, so they are placed in a storage box instead. A transaction protects the database changes; if the database transaction fails, the generated output is removed.

Exports are limited to Generation II records with supported species IDs (1–251), held-item IDs (0–249), move IDs (0–251, with 0 representing an empty slot), field widths, and English Gen II names. This is a data-format/range check, **not a species-specific legal learnset check**. The old parser's Crystal checksum flag is no longer treated as Crystal support: Crystal has different save offsets and is rejected rather than written using the wrong layout.

## Tests

```bash
python -m unittest discover -s tests -v
```

Tests use temporary databases and synthetic save files; they do not touch your existing `chemspc.db` or real saves.
