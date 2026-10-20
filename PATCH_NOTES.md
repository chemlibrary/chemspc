# chemspc source updates

Replace the repository's `gen2.py`, `pokemon.py`, `db.py`, and `main.py` with the versions here, and add `tests/test_gen2_save.py`.

## Changes

- Reads all 14 English Gold/Silver PC boxes at their actual offsets, including the gap between boxes 7 and 8.
- Treats the selected PC box at `0x2D6C` as the live copy on load and synchronizes it with its numbered box on write.
- Serializes party records to exactly 428 bytes and each PC box to exactly 1,104 bytes; stores OT-name and nickname blocks in the correct order and fixed-width fields.
- Fixes name handling for ten-character strings ending in digit `9` and enforces the ten-byte name limit.
- Synchronizes all five primary-to-backup data regions and recomputes the Gold/Silver checksums over their documented inclusive ranges, in little-endian order.
- Fixes `Pokemon` constructor attributes that previously became one-element tuples.
- Commits SQLite inserts. `main.py` uses a single batch transaction, and only then writes an output save with Pokémon removed. The input file is left untouched; output is `<input>.new`.
- Refuses to write Crystal saves through the Gold/Silver serializer rather than silently applying the wrong layout. The separate Crystal checksum helper has corrected ranges.

## Tests

From the repository root, run:

```bash
python -m unittest discover -s tests -v
```

The tests use a synthetic 32 KiB save buffer to check structure lengths, all 14 box offsets, name round-trips, live-box handling, backup-region synchronization, and checksums. They do not replace testing with the repository's real example save in an emulator.
