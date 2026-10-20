"""Import Pokémon from an English Gold/Silver save into SQLite.

The original save is never overwritten. A modified save is written beside it
with the suffix ``.new`` after the database transaction succeeds.
"""

import argparse

from db import add_pokemon_batch, init_tables
from gen2 import Gen2_Save


def import_gen2(path: str):
    init_tables()
    save = Gen2_Save(path=path)
    save.print_all_pokemon()

    # Include the party and each PC box, then commit the complete extraction
    # before removing anything from the save copy.
    extracted = list(save.party_pokemon)
    for box in save.box_pokemon:
        extracted.extend(box)
    add_pokemon_batch(extracted)

    # The output save has no Pokémon in the party or PC. The input remains
    # untouched; Gen2_Save.write_save() writes to <path>.new.
    save.party_pokemon = []
    save.box_pokemon = [[] for _ in range(14)]
    output_path = save.write_save(gold_silver=True)
    print(f"Imported {len(extracted)} Pokémon into SQLite.")
    print(f"Wrote Pokémon-free save to {path}.new")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract Pokémon from an English Pokémon Gold/Silver save into SQLite."
    )
    parser.add_argument("save_file", help="Path to the 32 KiB .sav file")
    args = parser.parse_args()
    import_gen2(args.save_file)


if __name__ == "__main__":
    main()
