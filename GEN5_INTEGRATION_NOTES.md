# Generation V integration notes

## Added game options

- `black`
- `white`
- `black2`
- `white2`

Run the command-line entry point as, for example:

```bash
python main.py pokemon-black.sav --game black
python main.py pokemon-white.sav --game white
python main.py pokemon-black2.sav --game black2
python main.py pokemon-white2.sav --game white2
```

## Save handling

`gen5.py` reads raw unheadered 512 KiB saves. Black/White use a `0x24000`-byte main-save region and backup; Black 2/White 2 use `0x26000`-byte regions. Each region contains 24 PC-box blocks (30 136-byte records per box) and one party block (up to six 220-byte records). The module validates the CRC-16/CCITT values stored in each touched block and their mirrored checksum table before allowing that copy to be modified.

Generation V Pokémon records have an eight-byte unencrypted header, PID-dependent ordering of four 32-byte substructures, and LCRNG XOR encryption. Party records include 84 additional bytes encrypted using the PID. The parser validates the internal Pokémon checksum and decodes the fields represented in the shared `Pokemon` model. Original encrypted records are retained for lossless re-emission; this module does not manufacture a new PK5 from high-level fields alone.

During extraction, `main.py` inserts the complete party/box batch into SQLite first. Only after that transaction commits does it clear the in-memory party and 24 boxes and write `<input>.new`. Every valid save copy is updated so a backup restore will not reintroduce Pokémon that the extraction removed. The input file is never overwritten. Unrelated blocks outside the party and PC boxes are preserved.

## SQLite

The existing shared schema already includes source-game, PID/personality, ability, language, nature, egg/shiny state, separate Special Attack and Special Defense EVs, and origin/encounter metadata. Generation V values populate those columns where their meaning matches. Gender is left null because accurate Gen V gender interpretation depends on species gender ratio rules; the field at the corresponding record byte is not a generic gender value.

No schema migration is required specifically for this integration; `source_game` records the exact title.

## Verification

Run:

```bash
python -m unittest discover -s tests -v
```

The tests use synthetic save fixtures for all four titles, generate internally consistent block/footer checksums and Pokémon records, verify decryption/field parsing, check that both copies are updated, test backup fallback, and exercise the SQLite transaction/output-save workflow including a simulated database failure.

These synthetic tests are structural regression tests, not evidence that output has been validated against every real retail save or emulator. Keep a backup and test the `.new` file in a compatible emulator before relying on it.

## Format references

- [Pokémon Black/White save structure](https://projectpokemon.org/home/docs/gen-5/bw-save-structure-r60/)
- [Pokémon Black 2/White 2 save structure](https://projectpokemon.org/home/docs/gen-5/b2w2-save-structure-r72/)
- [PKHeX Generation V Pokémon encryption/decryption](https://github.com/kwsch/PKHeX/blob/master/PKHeX.Core/PKM/Util/PokeCrypto.cs)
- [PKHeX Generation V Pokémon fields](https://github.com/kwsch/PKHeX/blob/master/PKHeX.Core/PKM/PK5.cs)
- [PKHeX Generation V save handler](https://github.com/kwsch/PKHeX/blob/master/PKHeX.Core/Saves/SAV5.cs)
