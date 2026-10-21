# chemspc source updates: English Generation II and Crystal support

This bundle supports reading and writing English Pokémon Gold, Silver, and
Crystal save files. It keeps the input save unchanged and writes the modified
save to `<input-path>.new`.

## Crystal implementation

- Added `Crystal_Save` (also exported as `Gen2_Crystal_Save`) to `gen2.py`.
- Uses Crystal's party offset (`0x2865`), current-box number offset (`0x2700`),
  and live Current Box offset (`0x2D10`).
- Reuses the English Generation II party and PC box serializer; English Crystal
  uses the same 428-byte party, 14 boxes, and box offsets as Gold/Silver.
- Copies Crystal's primary data bytes `0x2009..0x2B82` to its secondary copy at
  `0x1209..0x1D82`, recalculates both little-endian checksums, and updates the
  Crystal save-magic bytes for both copies.
- Keeps the live Current Box synchronized with the selected numbered PC box.
- Adds `--game crystal` to the CLI; Gold/Silver remains the default.

## Usage

Gold/Silver (default):

```bash
python main.py path/to/save.sav
```

Crystal:

```bash
python main.py path/to/crystal.sav --game crystal
```

The tool inserts extracted Pokémon in one SQLite transaction before writing
an output save with the party and PC boxes cleared. The original save is never
overwritten. Review the `.new` file before using it in an emulator or replacing
any other save copy.

## Tests

Run from the project root:

```bash
python -m unittest discover -s tests -v
```

The tests check the structural layout and checksums with synthetic 32 KiB
fixtures. A known-good real Crystal save and emulator validation are still
recommended before relying on the output for a valuable save file.

## Scope and limitations

- English Gold, Silver, and Crystal saves are supported. Japanese layouts are
  not supported.
- Text encoding supports the character subset already implemented by this
  project; unsupported characters raise an error rather than silently changing
  names.
- Pokémon are stored with the fields modeled in `pokemon.py`; no unrelated
  Crystal game state is intentionally modified beyond the party/box data,
  backup copy, and checksum/magic fields needed for a valid save.
