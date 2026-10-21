"""Extract Pokémon from English Generation II saves into SQLite.

The original save is never overwritten. A modified save is written beside it
with the suffix ``.new`` after the database transaction succeeds.
"""

import argparse

from db import add_pokemon_batch, init_tables
from gen2 import Crystal_Save, Gen2_Save


def import_gen2(path: str, game: str = "gold-silver"):
    """Import every Pokémon from an English Gold/Silver or Crystal save.

    ``game`` must be ``"gold-silver"`` or ``"crystal"``. Database insertion
    commits as one transaction before an empty-party/empty-box save is written.
    """
    normalized_game = game.lower().replace("_", "-")
    if normalized_game in ("gold", "silver", "gold-silver", "gs"):
        save_class = Gen2_Save
    elif normalized_game in ("crystal", "c"):
        save_class = Crystal_Save
    else:
        raise ValueError(
            "Unsupported Generation II game. Choose 'gold-silver' or 'crystal'."
        )

    init_tables()
    save = save_class(path=path)
    save.print_all_pokemon()

    # Insert party and PC Pokémon, committing the complete import before
    # removing any of them from the output save.
    extracted = list(save.party_pokemon)
    for box in save.box_pokemon:
        extracted.extend(box)
    add_pokemon_batch(extracted)
    save.party_pokemon = []
    save.box_pokemon = [[] for _ in range(14)]

    output_path = save.write_save()
    print(f"Imported {len(extracted)} Pokémon into SQLite.")
    print(f"Wrote Pokémon-free save to {output_path}")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Extract Pokémon from an English Generation II save into SQLite "
            "and write a copy without party/PC Pokémon."
        )
    )
    parser.add_argument("save_file", help="Path to the 32 KiB .sav file")
    parser.add_argument(
        "--game",
        choices=("gold-silver", "crystal"),
        default="gold-silver",
        help="Game version/layout (default: gold-silver)",
    )
    args = parser.parse_args()
    import_gen2(args.save_file, game=args.game)


if __name__ == "__main__":
    main()
