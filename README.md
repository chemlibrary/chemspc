# chemspc

`chemspc` extracts Pokémon data from supported English Generation II, III, and IV save files into a local SQLite database. After the database import succeeds, it writes a separate save-file copy with Pokémon removed from the party and PC boxes.

> **Protect your saves:** the input `.sav` file is never overwritten. The program writes its modified result to `<input-file>.new`. Keep a separate backup and validate output with a known-good retail save and an emulator before relying on it.

## Supported games

| Generation | Games | CLI value |
|---|---|---|
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

The program expects raw save files, not ROMs. Generation II–IV support the documented English layouts; Generation IV uses separate save-block profiles for Diamond/Pearl, Platinum, and HeartGold/SoulSilver. Specify the exact game when known. Gen III `auto` mode may identify a compatible layout without determining the exact title; ambiguous layouts raise an error instead of guessing. Gen IV currently requires an explicit game selection.

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

The shared schema stores generation and source-game information along with species, names, original trainer details, moves, experience, EVs/IVs, party stats, and other values available from each generation's parser.

### Generation-specific data

- `source_game`: the selected game/layout name, such as `emerald`, `firered`, `diamond`, or `soulsilver`.
- `special_attack_ev` and `special_defense_ev`: preserve the separate Special Attack and Special Defense EV values introduced in Generation III; `special_ev` remains for Generation II compatibility and holds their sum where appropriate.
- `personality`, `ability`, `language`, `gender`, `nature`, `is_egg`, and `is_shiny`: parsed Generation III/IV identity and status fields where available.
- `game_of_origin`, `met_location`, `egg_location`, `met_level`, `pokeball`, `encounter_type`, `egg_date`, `met_date`, and `original_trainer_gender`: Generation IV encounter/origin metadata. Date fields are stored as raw packed three-byte values so the original components are not lost through an assumed date convention.

Columns that do not apply to a particular game's format can be `NULL`. Fields that originate in one generation may have a different meaning in another; interpret generation-specific values with `generation` and `source_game` rather than assuming every field is uniform across all formats.

The extraction inserts all Pokémon in one transaction. If any database insert fails, the transaction rolls back rather than leaving a partial batch.

## Tests

Run the test suite from the project root:

```bash
python -m unittest discover -s tests -v
```

The tests cover Generation II/III/IV format handling, selected save-block layouts and checksums, encrypted Generation IV Pokémon records, SQLite schema migrations, and the extraction workflow for supported Gen III/IV game labels using synthetic fixtures. Synthetic tests are useful regression checks, but **they do not replace testing with a known-good retail save and an emulator**. Generated saves have not been verified against every retail game in an emulator; always validate the `.new` file before using it as the primary save.

## Project files

| File | Purpose |
|---|---|
| `main.py` | Command-line entry point and extraction-to-SQLite workflow |
| `gen2.py` | Gold/Silver and Crystal save reader/writer |
| `gen3.py` | Ruby, Sapphire, Emerald, FireRed, and LeafGreen save reader/writer |
| `gen4.py` | Diamond, Pearl, Platinum, HeartGold, and SoulSilver save reader/writer |
| `pokemon.py` | Shared Pokémon data model and Generation II record conversion |
| `db.py` | SQLite schema, migrations, and transactional insert helpers |
| `tests/` | Unit and integration tests |

## Limitations

- Generation I and Generation V–VI save handling is not implemented yet.
- Generation II–IV handlers target documented English save layouts. The Generation IV text decoder handles standard letters, digits, and common punctuation; uncommon symbols or language-specific characters may display as `?` in SQLite. The original encrypted Pokémon records are retained in the save when Pokémon are preserved.
- The Generation IV handler is intended for extraction/clearing of existing party and PC Pokémon records. It does not create new Pokémon records from just a species/name or re-encode arbitrary Pokémon field edits.
- Some game-specific or less common Pokémon metadata is not yet normalized into friendly text values. Generation IV encounter dates are retained as packed raw values.
- Verify output with real saves and an emulator before relying on it. Always retain backups of original save files.
