# Generation I integration notes

## Supported games

English Pokémon Red, Blue, and Yellow (`--game red|blue|yellow`). The save file itself does not contain an unambiguous game-version marker, so callers must identify the title.

## Input/output format

The handler reads the first `0x8000` bytes of a raw SRAM save dump and requires a valid main checksum at `0x3523`. This accepts 32 KiB dumps and oversized Yellow dumps whose actual SRAM save occupies the first 32 KiB. It writes `<input>.new`, leaving the original untouched.

## Pokémon storage

- Party starts at `0x2F2C`, size `0x194`, up to six records of 44 bytes.
- The active box is duplicated at `0x30C0`; its zero-based index is the low seven bits of `0x284C`.
- The 12 stored boxes begin at `0x4000` and `0x6000`, six per bank; each box is `0x462` bytes and holds 20 records.
- If a PC SRAM bank's whole-bank checksum is invalid, its non-active boxes are treated as uninitialized/empty, matching retail game behavior. The active Current Box copy remains authoritative. When writing modified box data, both copies and every whole-bank/individual-box checksum are synchronized.

## SQLite fields

`species` uses the National Pokédex number for recognized species; `gen1_internal_species` stores the exact Generation I index. `held_item` holds Gen I's catch-rate byte. The five stat-experience values are retained in the legacy stat fields (`hp_ev`, `attack_ev`, `defense_ev`, `speed_ev`, `special_ev`) as raw 16-bit stat experience, not modern EVs. The single Special stat is stored in `special_attack`; `special_defense` is `NULL`.

## Scope and limitations

The handler reads English character-map data, extracts party/box Pokémon, preserves retained records, clears removed records, and updates the relevant checksums. It refuses malformed party/box counts and a bad main checksum. Unusual punctuation may decode as `?`. It does not synthesize new Gen I Pokémon from the cross-generation model. Test with a backup and verify in an emulator; synthetic tests are not a replacement for validation against a retail save.
