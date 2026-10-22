# ChemSPC

ChemSPC is a local web-based Pokémon storage manager for supported English Pokémon save formats from **Generations I–VII**. It provides a shared SQLite collection where you can selectively import Pokémon from a game save and export compatible Pokémon back into a save of the same generation.

ChemSPC is intended for personal, local use. It is not a save editor for arbitrary changes, a cross-generation converter, or a complete Pokémon legality checker.

## Features

- A Flask website for reviewing Pokémon in a save file and in the active database.
- Selective imports from the source save's party and PC boxes.
- Selective exports from the database into an available PC box slot in the selected save.
- An explicit **Finalize** step. Selections are staged until finalization.
- Separate active (`pokemon`) and inactive (`inactive_pokemon`) database tables. An exported Pokémon is moved from the active table to the inactive table, retaining its database UID and stored record data.
- Generation-specific save readers and writers for supported Generations I–VII formats.
- Upload normalization: trailing bytes after the expected raw save length are trimmed from the server-side staged upload. Files that are too short are rejected rather than padded.
- Retention of generation-native Pokémon record data in SQLite where the format requires the original record for safe export.
- Checksum-aware save output using the corresponding generation handler.

## Requirements

- Python **3.10 or newer**.
- Dependencies from `requirements.txt` (currently Flask 3.x).
- A supported raw save file. ROM files are not accepted.

## Installation and start-up

Run these commands from the repository root.

### Linux / macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python main.py
```

### Windows PowerShell

```powershell
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

Open <http://127.0.0.1:5000> in your browser. `main.py` now starts the Flask website; the previous command-line extraction workflow is not the primary interface.

The app listens on `127.0.0.1` by default. You may set `CHEMSPC_PORT` to change the port. `CHEMSPC_HOST` can change the bind address, but do not expose ChemSPC to an untrusted network: the app is designed for local use and does not implement user accounts or authentication. `CHEMSPC_SECRET_KEY` can be set to provide a stable Flask session secret.

## Using the website

1. **Choose the exact game/version.** The website uses this choice to select the right parser and expected save size; it does not auto-detect the title.
2. **Upload the save file.** The upload is staged on the server. If it is larger than the size expected for the selected game, trailing bytes are removed from the staged copy before parsing. The website reports how many bytes were removed. A shorter-than-required file is rejected.
3. **Select Pokémon to import.** Pokémon in the source save's party and PC boxes are listed individually. Select the records to add to the active database.
4. **Select Pokémon to export.** Active database entries are checked for generation compatibility and the data required to write them to the selected format. Exports are placed into PC storage, not directly into the party.
5. **Review and finalize.** Finalization writes a separate output save and applies the selected database changes in a SQLite transaction. The page provides a link to download the generated save.

Canceling the workflow abandons the staged selection without importing or exporting any Pokémon. Until finalization succeeds, the database is not changed by the selections. The uploaded local file on your computer is never modified; the generated save is a separate download.

### What finalization changes

- Each selected import is inserted into the active `pokemon` table and removed from the generated save's party/boxes.
- Each selected export is added to a compatible, vacant PC storage slot in the generated save and moved from `pokemon` to `inactive_pokemon` in the database.
- Pokémon that are not selected remain in the generated save.
- If validation or the database transaction fails, the application reports an error and rolls back the database transaction rather than committing a partial transfer.

Make a separate backup of your original save and database before use. Always test a generated save in an emulator or other appropriate environment before treating it as your primary save.

## Supported games and save formats

The handlers support the following titles and expected raw file sizes. Sizes are exact byte counts after upload normalization.

| Generation | Game/version | Selection | Required size | Required input format |
|---|---|---|---:|---|
| I | Pokémon Red | `red` | 32 KiB (`0x8000`) | English SRAM save |
| I | Pokémon Blue | `blue` | 32 KiB (`0x8000`) | English SRAM save |
| I | Pokémon Yellow | `yellow` | 32 KiB (`0x8000`) | English SRAM save |
| II | Pokémon Gold | `gold-silver` | 32 KiB (`0x8000`) | English Gold/Silver layout |
| II | Pokémon Silver | `gold-silver` | 32 KiB (`0x8000`) | English Gold/Silver layout |
| II | Pokémon Crystal | `crystal` | 32 KiB (`0x8000`) | English Crystal layout |
| III | Pokémon Ruby | `ruby` | 128 KiB (`0x20000`) | Raw save |
| III | Pokémon Sapphire | `sapphire` | 128 KiB (`0x20000`) | Raw save |
| III | Pokémon Emerald | `emerald` | 128 KiB (`0x20000`) | Raw save |
| III | Pokémon FireRed | `firered` | 128 KiB (`0x20000`) | Raw save |
| III | Pokémon LeafGreen | `leafgreen` | 128 KiB (`0x20000`) | Raw save |
| IV | Pokémon Diamond | `diamond` | 512 KiB (`0x80000`) | Unheadered raw save |
| IV | Pokémon Pearl | `pearl` | 512 KiB (`0x80000`) | Unheadered raw save |
| IV | Pokémon Platinum | `platinum` | 512 KiB (`0x80000`) | Unheadered raw save |
| IV | Pokémon HeartGold | `heartgold` | 512 KiB (`0x80000`) | Unheadered raw save |
| IV | Pokémon SoulSilver | `soulsilver` | 512 KiB (`0x80000`) | Unheadered raw save |
| V | Pokémon Black | `black` | 512 KiB (`0x80000`) | Unheadered raw save |
| V | Pokémon White | `white` | 512 KiB (`0x80000`) | Unheadered raw save |
| V | Pokémon Black 2 | `black2` | 512 KiB (`0x80000`) | Unheadered raw save |
| V | Pokémon White 2 | `white2` | 512 KiB (`0x80000`) | Unheadered raw save |
| VI | Pokémon X | `x` | `0x65600` bytes | Decrypted PKHeX-compatible 3DS `main` save |
| VI | Pokémon Y | `y` | `0x65600` bytes | Decrypted PKHeX-compatible 3DS `main` save |
| VI | Pokémon Omega Ruby | `omegaruby` | `0x76000` bytes | Decrypted PKHeX-compatible 3DS `main` save |
| VI | Pokémon Alpha Sapphire | `alphasapphire` | `0x76000` bytes | Decrypted PKHeX-compatible 3DS `main` save |
| VII | Pokémon Sun | `sun` | `0x6BE00` bytes | Decrypted PKHeX-compatible 3DS `main` save |
| VII | Pokémon Moon | `moon` | `0x6BE00` bytes | Decrypted PKHeX-compatible 3DS `main` save |
| VII | Pokémon Ultra Sun | `ultrasun` | `0x6CC00` bytes | Decrypted PKHeX-compatible 3DS `main` save |
| VII | Pokémon Ultra Moon | `ultramoon` | `0x6CC00` bytes | Decrypted PKHeX-compatible 3DS `main` save |

Generations VI and VII require the decrypted `main` save data, not the encrypted outer 3DS save container. Use a compatible save manager to export the decrypted file and to put a verified output back into your save container. Pokémon: Let's Go, Pikachu! and Pokémon: Let's Go, Eevee! are not supported.

### How trailing-byte trimming works

The selected title determines the expected raw file size. If an upload is larger, ChemSPC truncates the server-side staged copy to that length before passing it to the parser. This is intended for emulator-added trailing data or oversized dumps where the supported save begins at byte zero. ChemSPC does not search for a save embedded at an offset, repair a truncated save, or turn an encrypted save container into a decrypted save. Selecting the wrong game can cause validation to fail; do not use trimming as a way to convert between save formats.

## Export compatibility and limitations

- **Cross-generation conversion is not implemented.** An exported Pokémon must match the generation of the target save.
- Pokémon are exported into PC storage only. ChemSPC does not calculate or invent party stats for a boxed record.
- The app validates supported species, move, and held-item ID ranges and required native record data. This is a format-compatibility check, **not** a complete legality analysis. Species-specific learnsets, every title-specific item restriction, encounter legality, and all other competitive/legal constraints are not exhaustively checked.
- Generation I uses an internal species index that differs from the National Pokédex number. Its `held_item`-like field is actually the catch-rate byte, not a held item.
- Generation II records can be written from the shared stored fields after range and text checks. Other generations generally require retained native binary Pokémon record data to preserve the format safely.
- Existing database rows created before native record payloads were saved may not be exportable to Generations I or III–VII. Re-import those Pokémon from a supported save using the current version to capture their native record payload. Cross-generation conversions remain unavailable even when a row has a native payload.
- Pokémon format details differ by generation. Fields that do not exist in a given generation may be empty, and some shared database fields have generation-specific meanings.

Do not treat a save as proven safe just because it passes validation. Back up the source file, retain your existing save until the generated one has been tested, and report malformed saves rather than trying to force them through the parser.

## Database

ChemSPC uses SQLite; no external database server is required. By default the database is `chemspc.db` alongside `db.py`. Set `CHEMSPC_DATABASE` to use a different path.

- `pokemon` contains active Pokémon available for export.
- `inactive_pokemon` is a history table for exported Pokémon. The row's UID and retained record payload are preserved when it is moved.
- `record_payload` stores generation-specific Pokémon metadata and native record bytes in JSON/base64 form so data can survive a database round trip without Python pickle.

The app initializes the tables at startup and adds the `record_payload` column to existing active/inactive tables if it is missing. Back up your database before upgrading. Older records without retained native data remain in the database, but they may fail export compatibility checks for formats that need an original binary record.

Staged uploads and generated output files are stored under Flask's `instance/` directory, in `instance/staging/` and `instance/exports/`. Keep this directory private and remove stale files when they are no longer needed; generated exports are not your only backup.

## Tests

Run the test suite from the repository root after installing requirements:

```bash
python -m unittest discover -s tests -v
```

The tests include generation-specific save parsing/writing, checksums and record layouts, database behavior, the Flask transfer workflow, and upload normalization across supported game sizes. Synthetic fixtures provide regression coverage but do not replace validation against known-good real save files and an emulator.

## Project layout

| Path | Purpose |
|---|---|
| `main.py` | Flask app, upload/review/finalize/download routes, and compatibility checks |
| `save_formats.py` | Game registry, expected save sizes, upload trimming, and shared native-handler adapters |
| `gen1.py`–`gen7.py` | Existing generation-specific save readers and writers; keep these files when applying an update |
| `gen2.py` | Generation II Gold/Silver and Crystal save support and record serialization |
| `pokemon.py` | Shared Pokémon data model |
| `db.py` | SQLite persistence, native-record payload storage, and active/inactive table operations |
| `templates/` | Flask HTML templates |
| `static/` | CSS and other static browser assets |
| `tests/` | Unit and workflow tests |
| `requirements.txt` | Runtime dependencies |
| `pyproject.toml` | Package metadata and test configuration |

## License

ChemSPC is distributed under the license in [`LICENSE`](LICENSE) (GPL-3.0-or-later).
