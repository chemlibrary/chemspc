# chemspc Generation II–IV integration notes

## Project support

- Generation II: Gold/Silver and Crystal save handlers, including game-specific party/box structures and checksums.
- Generation III: Ruby, Sapphire, Emerald, FireRed, and LeafGreen save handling through `Gen3_Save`.
- Generation IV: Diamond, Pearl, Platinum, HeartGold, and SoulSilver save handling through `Gen4_Save`.
- `main.py` dispatches the selected game to the corresponding handler and runs the common extraction-to-SQLite process.

## Extraction workflow

1. Parse Pokémon from the party and PC storage.
2. Insert the extracted Pokémon batch into SQLite in one transaction.
3. Clear the party and PC records in the in-memory save only after that insertion commits.
4. Write `<input-file>.new`; never overwrite the original save.

If the database insertion fails, the workflow exits before writing a Pokémon-free save.

## Database

Existing `pokemon` and `inactive_pokemon` SQLite tables are migrated automatically with nullable fields for source game, Gen III Special Attack/Special Defense EVs, Gen III/IV identity values, and Gen IV encounter metadata. Existing rows are retained.

## Generation IV implementation

- Uses separate retail layout profiles for Diamond/Pearl, Platinum, and HeartGold/SoulSilver.
- Validates and selects linked general/storage block copies using save footer metadata and CRC-16-CCITT checksums.
- Reads party and all 18 PC boxes; validates/decrypts 136-byte boxed and 236-byte party Pokémon records, including PID-based stat encryption.
- Preserves existing encrypted Pokémon records and updates relevant block checksums when writing a modified copy.

## Validation

Run all included tests with:

```bash
python -m unittest discover -s tests -v
```

The current suite passes 31 tests using synthetic fixtures. These tests cover Generation II–IV structural logic and Gen III/IV SQLite integration. They do **not** replace validation against known-good retail save files in an emulator. Keep backups and verify generated `.new` files before using them as primary saves.
