"""Extract Pokémon from Generation II, III, and IV saves into SQLite.

The original save is never overwritten. Once all extracted Pokémon have been
committed to SQLite in one transaction, a modified copy without party/PC
Pokémon is written beside the original with the suffix ``.new``.
"""

import argparse
from db import add_pokemon_batch, init_tables
from gen2 import Crystal_Save, Gen2_Save
from gen3 import Gen3_Save
from gen4 import Gen4_Save

GEN3_GAMES = {"ruby", "sapphire", "emerald", "firered", "leafgreen"}
GEN4_GAMES = {"diamond", "pearl", "platinum", "heartgold", "soulsilver"}
GEN2_GAMES = {"gold", "silver", "gold-silver", "gs", "crystal", "c"}


def _all_pokemon(save) -> list:
    extracted = list(save.party_pokemon)
    for box in save.box_pokemon:
        extracted.extend(box)
    return extracted


def import_gen2(path: str, game: str = "gold-silver") -> str:
    """Import every Pokémon from an English Gold/Silver or Crystal save."""
    normalized_game = game.lower().replace("_", "-")
    if normalized_game in ("gold", "silver", "gold-silver", "gs"):
        save_class = Gen2_Save
        source_game = "gold-silver" if normalized_game in ("gold-silver", "gs") else normalized_game
    elif normalized_game in ("crystal", "c"):
        save_class = Crystal_Save
        source_game = "crystal"
    else:
        raise ValueError(
            "Unsupported Generation II game. Choose 'gold-silver' or 'crystal'."
        )

    init_tables()
    save = save_class(path=path)
    save.print_all_pokemon()

    extracted = _all_pokemon(save)
    for pokemon in extracted:
        pokemon.game_name = source_game
    # The complete import is committed before the output save is modified.
    add_pokemon_batch(extracted)

    save.party_pokemon = []
    save.box_pokemon = [[] for _ in range(14)]
    output_path = save.write_save()
    print(f"Imported {len(extracted)} Pokémon into SQLite.")
    print(f"Wrote Pokémon-free save to {output_path}")
    return output_path


def import_gen3(path: str, game: str) -> str:
    """Import all Pokémon from a Ruby/Sapphire/Emerald/FRLG save into SQLite."""
    normalized_game = game.strip().lower().replace("_", "-")
    if normalized_game not in GEN3_GAMES and normalized_game != "auto":
        raise ValueError(
            "Unsupported Generation III game. Choose ruby, sapphire, emerald, "
            "firered, leafgreen, or auto."
        )

    init_tables()
    save = Gen3_Save(path=path, game=normalized_game)
    save.print_all_pokemon()

    extracted = _all_pokemon(save)
    # Store the caller's explicit game selection as provenance. Auto mode only
    # determines a compatible layout, not necessarily Ruby versus Sapphire.
    source_game = save.game_name
    for pokemon in extracted:
        pokemon.game_name = source_game

    # add_pokemon_batch commits atomically, or raises before save mutation.
    add_pokemon_batch(extracted)

    save.party_pokemon = []
    save.box_pokemon = [[] for _ in range(14)]
    output_path = save.write_save()
    print(f"Imported {len(extracted)} Pokémon into SQLite ({source_game}).")
    print(f"Wrote Pokémon-free save to {output_path}")
    return output_path


def import_gen4(path: str, game: str) -> str:
    """Import all Pokémon from a Diamond/Pearl/Platinum/HGSS save into SQLite."""
    normalized_game = game.strip().lower().replace("_", "-")
    init_tables()
    save = Gen4_Save(path=path, game=normalized_game)
    save.print_all_pokemon()

    extracted = _all_pokemon(save)
    for pokemon in extracted:
        pokemon.game_name = save.game_name

    # SQLite commits the entire extraction atomically before save mutation.
    add_pokemon_batch(extracted)

    save.party_pokemon = []
    save.box_pokemon = [[] for _ in range(18)]
    output_path = save.write_save()
    print(f"Imported {len(extracted)} Pokémon into SQLite ({save.game_name}).")
    print(f"Wrote Pokémon-free save to {output_path}")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Extract Pokémon from Generation II, III, or IV saves into SQLite and "
            "write a copy without party/PC Pokémon."
        )
    )
    parser.add_argument("save_file", help="Path to the raw .sav file")
    parser.add_argument(
        "--game",
        choices=(
            "gold-silver", "crystal", "ruby", "sapphire", "emerald",
            "firered", "leafgreen", "diamond", "pearl", "platinum",
            "heartgold", "soulsilver", "auto",
        ),
        default="gold-silver",
        help=(
            "Game version/layout (default: gold-silver). Gen III supports ruby, "
            "sapphire, emerald, firered, leafgreen, or auto; Gen IV supports "
            "diamond, pearl, platinum, heartgold, and soulsilver."
        ),
    )
    args = parser.parse_args()

    selected_game = args.game.lower()
    if selected_game in GEN3_GAMES or selected_game == "auto":
        import_gen3(args.save_file, game=selected_game)
    elif selected_game in GEN4_GAMES:
        import_gen4(args.save_file, game=selected_game)
    else:
        import_gen2(args.save_file, game=selected_game)


if __name__ == "__main__":
    main()
