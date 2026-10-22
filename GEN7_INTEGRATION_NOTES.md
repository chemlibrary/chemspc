# Generation VII integration notes

## Scope

Generation VII support covers the 3DS titles only:

- Pokémon Sun (`sun`)
- Pokémon Moon (`moon`)
- Pokémon Ultra Sun (`ultrasun`)
- Pokémon Ultra Moon (`ultramoon`)

Pokémon: Let's Go, Pikachu! and Pokémon: Let's Go, Eevee! are not included. Those titles use a different format and are not recognized by `Gen7_Save`.

## Input save format

`gen7.py` expects a decrypted PKHeX-compatible 3DS `main` save dump. The expected sizes are:

| Games | Decrypted main size | Party data | PC box data |
|---|---:|---:|---:|
| Sun / Moon | `0x6BE00` (441,856 bytes) | `0x1400` | `0x4E00` |
| Ultra Sun / Ultra Moon | `0x6CC00` (445,440 bytes) | `0x1600` | `0x5200` |

The party checksum block is ID 4 and the box-Pokémon block is ID 14 in the save footer metadata. Both are protected with CRC-16/CCITT and are verified before extraction. The footer's `FEEB` marker is also checked. The outer console-encrypted save container is not supported; export/import decrypted `main` data with a save manager compatible with your console/save source.

## Pokémon records

The handler reads six party slots and 32 PC boxes of 30 Pokémon each. PK7 uses the Generation VI/VII 232-byte stored format and 260-byte party format. The parser reuses the project's Generation VI record decryption/field decoder because the core record layout and crypto are shared, and marks imported Pokémon as generation 7 with the chosen `source_game` value.

This writer is for extraction/clearing existing records, not for creating Pokémon from scratch or re-encoding arbitrary edits. Retained Pokémon records remain in their original encrypted form; retained box Pokémon must remain in their original box/slot. The party list can be compacted if some party members are removed.

## SQLite and output behavior

`main.py` inserts extracted Pokémon into SQLite using the existing batch transaction. Only after that transaction succeeds does it clear the party and PC box Pokémon and write `<input>.new`. The input file remains unchanged. The existing schema's modern metadata columns are reused; no schema migration specific to Gen VII is required.

## Commands

```bash
python main.py pokemon-sun.main --game sun
python main.py pokemon-moon.main --game moon
python main.py pokemon-ultra-sun.main --game ultrasun
python main.py pokemon-ultra-moon.main --game ultramoon
```

## Validation

Run tests using:

```bash
python -m unittest discover -s tests -v
```

The Generation VII unit tests use synthetic save buffers and cover each profile, record parsing, preservation on untouched round trips, checksums after clearing, retained-box-slot preservation, invalid save rejection, SQLite integration, and aborting output creation on SQLite failure. These tests are not a substitute for testing a known-good retail save and emulator. Always preserve backups and validate output before restoring it to a console.

## Format references

- PKHeX `SAV7`: https://github.com/kwsch/PKHeX/blob/master/PKHeX.Core/Saves/SAV7.cs
- PKHeX `SAV7SM`: https://github.com/kwsch/PKHeX/blob/master/PKHeX.Core/Saves/SAV7SM.cs
- PKHeX `SAV7USUM`: https://github.com/kwsch/PKHeX/blob/master/PKHeX.Core/Saves/SAV7USUM.cs
- Sun/Moon block map: https://github.com/kwsch/PKHeX/blob/master/PKHeX.Core/Saves/Access/SaveBlockAccessor7SM.cs
- Ultra Sun/Ultra Moon block map: https://github.com/kwsch/PKHeX/blob/master/PKHeX.Core/Saves/Access/SaveBlockAccessor7USUM.cs
- PK7 record crypto: https://github.com/kwsch/PKHeX/blob/master/PKHeX.Core/PKM/Util/PokeCrypto.cs
