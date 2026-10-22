# chemspc

`chemspc` extracts Pokémon data from supported Generation I–VII save files into a local SQLite database. After the database import succeeds, it writes a separate save-file copy with Pokémon removed from the party and PC boxes.

> **Protect your saves:** the input `.sav` file is never overwritten. The program writes its modified result to `<input-file>.new`. Keep a separate backup and validate output with a known-good retail save and an emulator before relying on it.

## Supported games

| Generation | Games | CLI value |
|---|---|---|
| I | Pokémon Red | `red` |
| I | Pokémon Blue | `blue` |
| I | Pokémon Yellow | `yellow` |
| II | Pokémon Gold / Silver | `gold-silver` (default) |
| II | Pokémon Crystal | `crystal` |
| III | Pokémon Ruby | `ruby` |
| III | Pokémon Sapphire | `sapphire` |
| III | Pokémon Emerald | `emerald` |
| III | Pokémon FireRed | `firered` |
| III | Pokémon LeafGreen | `leafgreen` |
| III | Detect a compatible Gen III layout | `auto` |
| IV | Pokémon Diamond | `diamond` |
| IV | Pokémon Pearl | `pearl` |
| IV | Pokémon Platinum | `platinum` |
| IV | Pokémon HeartGold | `heartgold` |
| IV | Pokémon SoulSilver | `soulsilver` |
| V | Pokémon Black | `black` |
| V | Pokémon White | `white` |
| V | Pokémon Black 2 | `black2` |
| V | Pokémon White 2 | `white2` |
| VI | Pokémon X | `x` |
| VI | Pokémon Y | `y` |
| VI | Pokémon Omega Ruby | `omegaruby` |
| VI | Pokémon Alpha Sapphire | `alphasapphire` |
| VII | Pokémon Sun | `sun` |
| VII | Pokémon Moon | `moon` |
| VII | Pokémon Ultra Sun | `ultrasun` |
| VII | Pokémon Ultra Moon | `ultramoon` |

The program expects save data, not ROMs. Generation I accepts English Red/Blue/Yellow SRAM dumps; Generations II–V support the documented layouts noted below. Generations VI and VII require decrypted, PKHeX-compatible 3DS `main` save dumps: X/Y are `0x65600` bytes, Omega Ruby/Alpha Sapphire are `0x76000` bytes, Sun/Moon are `0x6BE00` bytes, and Ultra Sun/Ultra Moon are `0x6CC00` bytes. These handlers do not accept the encrypted outer 3DS save container; use a compatible save manager to export/import the decrypted `main` data. Specify the exact game for Generations IV–VII. Gen III `auto` mode may identify a compatible layout without determining the exact title; ambiguous layouts raise an error instead of guessing. Gen V distinguishes the Black/White layout from the Black 2/White 2 layout.

## Installation

Run the program with the Python environment and dependencies used by the project. From the project directory, see the command examples below. No external database server is needed; SQLite stores data in `chemspc.db` in the current working directory.

## How extraction works

For a selected save file, the program:

1. Reads Pokémon from the party and PC boxes.
2. Inserts the extracted Pokémon as a batch in one SQLite transaction.
3. Only after the database transaction succeeds, clears the extracted Pokémon from the in-memory party and PC boxes.
4. Writes a new save next to the input file with the `.new` suffix.

If the database insert fails, the program raises an error before writing the Pokémon-free save. The original save remains unchanged. This workflow is intended to reduce the risk of losing Pokémon during extraction, but it does not replace a separate backup.

## Usage

### Generation I: Red, Blue, Yellow (English)

```bash
python main.py pokemon-red.sav --game red
python main.py pokemon-blue.sav --game blue
python main.py pokemon-yellow.sav --game yellow
```

Generation I expects an English 32 KiB SRAM `.sav` dump. Oversized dumps (for example 128 KiB dumps from some Yellow tools) are accepted and only the first 32 KiB are used. The handler validates the main checksum, reads the active PC box from the live copy in bank 1, and reads the other boxes from the two PC-box banks. Uninitialized box banks are treated as empty, matching the game's save behavior. The 12 boxes contain 20 Pokémon each.

The Gen I parser converts standard internal species indexes to National Pokédex numbers for the common `species` database column and separately preserves the exact internal species index in `gen1_internal_species`. Generation I has stat experience rather than modern EVs; the values are stored in the existing stat fields as raw stat experience. The single Special stat is stored in `special_attack`, and `special_defense` is left `NULL`. The `held_item` field contains Gen I's catch-rate byte, not a held item.

### Generation II: Gold / Silver

Gold/Silver is the default, so the game flag can be omitted:

```bash
python main.py pokemon-gold.sav
python main.py pokemon-silver.sav --game gold-silver
```

### Generation II: Crystal

```bash
python main.py pokemon-crystal.sav --game crystal
```

### Generation III: Ruby, Sapphire, Emerald, FireRed, LeafGreen

```bash
python main.py pokemon-ruby.sav --game ruby
python main.py pokemon-sapphire.sav --game sapphire
python main.py pokemon-emerald.sav --game emerald
python main.py pokemon-firered.sav --game firered
python main.py pokemon-leafgreen.sav --game leafgreen
```

Gen III layout detection can be requested when the game version is unknown:

```bash
python main.py pokemon.sav --game auto
```

### Generation IV: Diamond, Pearl, Platinum, HeartGold, SoulSilver

```bash
python main.py pokemon-diamond.sav --game diamond
python main.py pokemon-pearl.sav --game pearl
python main.py pokemon-platinum.sav --game platinum
python main.py pokemon-heartgold.sav --game heartgold
python main.py pokemon-soulsilver.sav --game soulsilver
```

Gen IV requires an explicit game because Diamond/Pearl, Platinum, and HeartGold/SoulSilver use different block layouts. The Gen IV handler expects an unheadered 512 KiB (`524288` byte) raw save file, and it validates the linked save blocks and their CRC-16-CCITT checksums before reading or writing them.

### Generation V: Black, White, Black 2, White 2

```bash
python main.py pokemon-black.sav --game black
python main.py pokemon-white.sav --game white
python main.py pokemon-black2.sav --game black2
python main.py pokemon-white2.sav --game white2
```

The Generation V handler expects an unheadered 512 KiB (`524288` byte) save. Black/White use `0x24000`-byte save copies; Black 2/White 2 use `0x26000`-byte copies. It validates the mirrored CRC-16-CCITT checksums for the 24 PC-box blocks and party block before extraction. Pokémon records are decrypted for parsing but retained in their original encrypted form when writing. Both valid save copies are updated after extraction, while unrelated save sections and the original input file are preserved.

### Generation VI: X, Y, Omega Ruby, Alpha Sapphire

```bash
python main.py pokemon-x.main --game x
python main.py pokemon-y.main --game y
python main.py pokemon-omega-ruby.main --game omegaruby
python main.py pokemon-alpha-sapphire.main --game alphasapphire
```

The Generation VI handler supports decrypted PKHeX-compatible save data only (X/Y: `0x65600` bytes; Omega Ruby/Alpha Sapphire: `0x76000` bytes). It validates the `FEEB` footer marker plus the party and PC-box block metadata/checksums before extracting Pokémon. Gen VI has 31 PC boxes with 30 slots each. Party and box PK6 records are decrypted for parsing; retained original records are preserved byte-for-byte. After extraction, the handler clears the party and PC Pokémon, updates the affected block checksums, and writes a `.new` file. It does **not** encrypt/decrypt the outer 3DS DISA/IVFC container or handle console-specific authentication; use a compatible save manager to export the decrypted `main` file and import the output back into the save container.

### Generation VII: Sun, Moon, Ultra Sun, Ultra Moon (3DS only)

```bash
python main.py pokemon-sun.main --game sun
python main.py pokemon-moon.main --game moon
python main.py pokemon-ultra-sun.main --game ultrasun
python main.py pokemon-ultra-moon.main --game ultramoon
```

The Generation VII handler supports the decrypted, PKHeX-compatible 3DS `main` save format only: Sun/Moon are `0x6BE00` bytes and Ultra Sun/Ultra Moon are `0x6CC00` bytes. It validates the `FEEB` footer marker and the party and PC-box block metadata/checksums. Generation VII has 32 PC boxes with 30 stored Pokémon slots each. Party PK7 records are 260 bytes and boxed PK7 records are 232 bytes; Pokémon record decryption is shared with Generation VI. Retained records are preserved byte-for-byte, and the writer updates the checksums for the party and box blocks after extraction. The encrypted outer 3DS save container is not supported; use a compatible save manager to export the decrypted `main` file and import the output back into the save container.

This project adds only the 3DS Generation VII games. **Pokémon: Let's Go, Pikachu! and Pokémon: Let's Go, Eevee! are not supported**; those games use a different save/Pokémon format.

To see supported arguments:

```bash
python main.py --help
```

For example, running:

```bash
python main.py pokemon-emerald.sav --game emerald
```

leaves `pokemon-emerald.sav` unchanged and writes `pokemon-emerald.sav.new` if the import succeeds.

## SQLite database

The program writes to `chemspc.db` in the current working directory. It creates a `pokemon` table and an `inactive_pokemon` table used by the existing project data model. A schema migration adds missing nullable fields to older databases without deleting existing records.

The shared schema stores generation and source-game information along with species, names, original trainer details, moves, experience, EVs/IVs, party stats, and other values available from each generation's parser. `gen1_internal_species` preserves Generation I internal species indexes, which differ from National Pokédex numbers.

### Generation-specific data

- `source_game`: the selected game/layout name, such as `emerald`, `firered`, `diamond`, or `soulsilver`.
- `gen1_internal_species`: retains the internal species index used by English Red/Blue/Yellow; the common `species` column is converted to a National Pokédex number when the internal value maps to a normal species.
- `special_attack_ev` and `special_defense_ev`: preserve the separate Special Attack and Special Defense EV values introduced in Generation III; `special_ev` remains for Generation II compatibility and holds their sum where appropriate.
- `personality`, `ability`, `language`, `gender`, `nature`, `is_egg`, and `is_shiny`: parsed Generation III–VII identity and status fields where available.
- `game_of_origin`, `met_location`, `egg_location`, `met_level`, `pokeball`, `encounter_type`, `egg_date`, `met_date`, and `original_trainer_gender`: Generation IV–VII encounter and origin metadata when exposed by a generation. Date fields are stored as raw packed three-byte values, avoiding an assumed date convention.

Columns that do not apply to a particular game's format can be `NULL`. Fields that originate in one generation may have a different meaning in another; interpret generation-specific values with `generation` and `source_game` rather than assuming every field is uniform across all formats.

The extraction inserts all Pokémon in one transaction. If any database insert fails, the transaction rolls back rather than leaving a partial batch.

## Tests

Run the test suite from the project root:

```bash
python -m unittest discover -s tests -v
```

The tests cover Generation I–VII format handling, save-block layouts and checksums, encrypted Pokémon records, SQLite schema migrations, and the extraction workflows for supported game labels using synthetic fixtures. Synthetic tests are useful regression checks, but **they do not replace testing with a known-good retail save and an emulator**. Generated saves have not been verified against every retail game in an emulator; always validate the `.new` file before using it as the primary save.

## Project files

| File | Purpose |
|---|---|
| `main.py` | Command-line entry point and extraction-to-SQLite workflow |
| `gen1.py` | Red, Blue, and Yellow save reader/writer |
| `gen2.py` | Gold/Silver and Crystal save reader/writer |
| `gen3.py` | Ruby, Sapphire, Emerald, FireRed, and LeafGreen save reader/writer |
| `gen4.py` | Diamond, Pearl, Platinum, HeartGold, and SoulSilver save reader/writer |
| `gen5.py` | Black, White, Black 2, and White 2 save reader/writer |
| `gen6.py` | X, Y, Omega Ruby, and Alpha Sapphire decrypted save reader/writer |
| `gen7.py` | Sun, Moon, Ultra Sun, and Ultra Moon decrypted save reader/writer |
| `pokemon.py` | Shared Pokémon data model and Generation II record conversion |
| `db.py` | SQLite schema, migrations, and transactional insert helpers |
| `tests/` | Unit and integration tests |

## Limitations

- Generation VIII+ save handling is not implemented yet. Generation VII support is limited to the 3DS Sun/Moon/Ultra Sun/Ultra Moon titles; Let’s Go is intentionally excluded.
- Generation I support is limited to English Red/Blue/Yellow saves. Common species indexes are mapped to National Dex numbers; glitch species retain their raw internal index but use species `0` in the common field when no National Dex mapping exists. Generation I stat experience is stored in existing EV columns as raw stat experience. The writer preserves existing Pokémon records and supports removal; it does not synthesize new Gen I records.
- Generation II–V handlers target documented English save layouts. The Generation IV text decoder handles standard letters, digits, and common punctuation; uncommon symbols or language-specific characters may display as `?` in SQLite. The original encrypted Pokémon records are retained in the save when Pokémon are preserved.
- The Generation IV–VII handlers are intended for extraction/clearing of existing party and PC Pokémon records. They do not create new Pokémon records from just a species/name or re-encode arbitrary Pokémon field edits. The Generation V/VI/VII readers preserve common text fields for parsing; uncommon symbols and some language-specific glyphs may render as `?` in SQLite, while retained encrypted records remain unchanged.
- Some game-specific or less common Pokémon metadata is not yet normalized into friendly text values. Generation IV–VII encounter dates are retained as packed raw values. Generation V gender is left unset in SQLite because it requires species-specific gender-ratio rules.
- Verify output with real saves and an emulator before relying on it. Always retain backups of original save files.
