# Generation VI integration notes

`gen6.py` adds `Gen6_Save` for Pokémon X, Y, Omega Ruby, and Alpha Sapphire and is integrated into `main.py` and the existing SQLite extraction transaction. The Gen VI metadata already fits the shared nullable database schema, so no new schema migration is required for this change.

## CLI examples

```bash
python main.py pokemon-x.main --game x
python main.py pokemon-y.main --game y
python main.py pokemon-omega-ruby.main --game omegaruby
python main.py pokemon-alpha-sapphire.main --game alphasapphire
```

## Input format limitations

This handler expects a decrypted PKHeX-compatible Gen VI `main` save buffer: `0x65600` bytes for X/Y and `0x76000` bytes for Omega Ruby/Alpha Sapphire. It validates the `FEEB` footer marker and metadata entries/checksums for the party and PC-box blocks. It does not parse or repackage the encrypted outer 3DS DISA/IVFC container. Export the decrypted `main` with a compatible save manager and import the resulting `.new` data back through that manager.

It parses Pokémon identity, moves, EVs/IVs, party stats, names, origin, and encounter metadata. Original encrypted PK6 records are retained verbatim when they remain in their initial party or box positions. The extraction writer clears Pokémon from party and boxes, updates their associated block checksums, and leaves other save bytes alone. It does not synthesize Pokémon records, support moved/edited Pokémon records, or modify arbitrary PK6 fields.

## Validation

Run `python -m unittest discover -s tests -v`. Generation VI tests use synthetic decrypted save buffers and test game profiles, PK6 decryption/checksums, party and box reading, record preservation, output clearing, and SQLite failure safety. They do not replace validation with a known-good retail save and emulator. Keep backups and validate any `.new` output before importing it into a real save.
