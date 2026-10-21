# Generation IV integration notes

## Game selection and usage

The `main.py` entry point supports:

```bash
python main.py input.sav --game diamond
python main.py input.sav --game pearl
python main.py input.sav --game platinum
python main.py input.sav --game heartgold
python main.py input.sav --game soulsilver
```

Gen IV requires an explicit game selection and a raw, unheadered 512 KiB save file. Output is written to `input.sav.new`; the source save is never overwritten.

## Implementation

- `gen4.py` uses separate save block profiles for Diamond/Pearl, Platinum, and HeartGold/SoulSilver.
- It selects valid, linked general/storage block copies by footer IDs and save counters, checks CRC-16-CCITT values, parses party and 18 PC boxes, and maintains checksums after writing.
- Pokémon records are checksum-validated, decrypted with the Gen IV LCG, and unshuffled according to personality-derived block order. The party's 100 battle-stat bytes are also decrypted with the PID.
- Existing Pokémon records are retained byte-for-byte; the extraction workflow clears party/PC records after the SQLite transaction succeeds.
- SQLite records Gen IV personality, ability, language, nature, egg/shiny state, and encounter metadata. Nullable migration columns preserve compatibility with earlier database files.

## Tests and known limitations

Run `python -m unittest discover -s tests -v` from the repository root. Tests use synthetic save-block and Pokémon records. This validates serialization mechanics against the implemented format assumptions, but is not retail-save validation. Test copies from known-good saves in a Nintendo DS emulator before depending on an output file.

The current reader targets English-language layouts and common Gen IV name characters. It is designed for extracting and clearing existing Pokémon, not generating arbitrary new records or rewriting arbitrary field edits.

Format references:

- https://bulbapedia.bulbagarden.net/wiki/Save_data_structure_(Generation_IV)
- https://bulbapedia.bulbagarden.net/wiki/Pok%C3%A9mon_data_structure_in_Generation_IV
- https://github.com/kwsch/PKHeX/blob/master/PKHeX.Core/Saves/SAV4.cs
- https://github.com/kwsch/PKHeX/blob/master/PKHeX.Core/Saves/SAV4Sinnoh.cs
- https://github.com/kwsch/PKHeX/blob/master/PKHeX.Core/Saves/SAV4HGSS.cs
