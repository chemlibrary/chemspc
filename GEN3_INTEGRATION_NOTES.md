# Generation III SQLite integration

`main.py` now dispatches Generation II and Generation III saves to the appropriate reader/writer. The Generation III supported game labels are `ruby`, `sapphire`, `emerald`, `firered`, and `leafgreen` (or `auto`, which may be ambiguous; explicit selection is recommended).

## Usage

```bash
python main.py pokemon-emerald.sav --game emerald
python main.py pokemon-firered.sav --game firered
python main.py pokemon-ruby.sav --game ruby
```

Gold/Silver remains the default:

```bash
python main.py pokemon-gold.sav
python main.py pokemon-crystal.sav --game crystal
```

For each run, the program imports party and PC Pokémon in a single SQLite transaction. Only after that transaction succeeds does it write a `.new` save beside the original with party and PC Pokémon removed. It never overwrites the input save.

## Database changes

The existing `pokemon` and `inactive_pokemon` tables are migrated automatically with three nullable columns:

- `source_game`: selected game label, or `generation-3` when auto-detection was used.
- `special_attack_ev`: Generation III Special Attack EV.
- `special_defense_ev`: Generation III Special Defense EV.

The Gen II shared `special_ev` field is retained. For Gen III, it stores the sum of the two individual Special EV fields as a compatibility value. Older rows receive `NULL` for the new columns.

## Tests

```bash
python -m unittest discover -s tests -v
```

Tests include the existing Gen II/Gen III structural suites plus end-to-end Gen III extraction and SQLite schema migration using synthetic save fixtures. These tests do not substitute for checking outputs made from real retail save files in an emulator.
