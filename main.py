"""Extract Pokémon from Generation I through VII saves into SQLite.

The original save is never overwritten. Once all extracted Pokémon have been
committed to SQLite in one transaction, a modified copy without party/PC
Pokémon is written beside the original with the suffix ``.new``.
"""

import argparse
from db import add_pokemon_batch, init_tables
from gen1 import Gen1_Save
from gen2 import Crystal_Save, Gen2_Save
from gen3 import Gen3_Save
from gen4 import Gen4_Save
from gen5 import Gen5_Save
from gen6 import Gen6_Save
from gen7 import Gen7_Save

GEN1_GAMES = {"red", "blue", "yellow"}
GEN3_GAMES = {"ruby", "sapphire", "emerald", "firered", "leafgreen"}
GEN4_GAMES = {"diamond", "pearl", "platinum", "heartgold", "soulsilver"}
GEN5_GAMES = {"black", "white", "black2", "white2"}
GEN6_GAMES = {"x", "y", "omegaruby", "alphasapphire"}
GEN7_GAMES = {"sun", "moon", "ultrasun", "ultramoon"}
GEN2_GAMES = {"gold", "silver", "gold-silver", "gs", "crystal", "c"}


def _all_pokemon(save) -> list:
    extracted = list(save.party_pokemon)
    for box in save.box_pokemon:
        extracted.extend(box)
    return extracted


def import_gen1(path: str, game: str) -> str:
    """Import all Pokémon from an English Red/Blue/Yellow save into SQLite."""
    normalized_game = game.strip().lower()
    if normalized_game not in GEN1_GAMES:
        raise ValueError("Generation I supports only red, blue, or yellow")

    init_tables()
    save = Gen1_Save(path=path, game=normalized_game)
    save.print_all_pokemon()

    extracted = _all_pokemon(save)
    for pokemon in extracted:
        pokemon.game_name = save.game_name

    # Commit the full extract before clearing or writing any save data.
    add_pokemon_batch(extracted)

    save.party_pokemon = []
    save.box_pokemon = [[] for _ in range(12)]
    output_path = save.write_save()
    print(f"Imported {len(extracted)} Pokémon into SQLite ({save.game_name}).")
    print(f"Wrote Pokémon-free save to {output_path}")
    return output_path


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


def import_gen5(path: str, game: str) -> str:
    """Import all Pokémon from a Black/White/Black 2/White 2 save into SQLite."""
    normalized_game = game.strip().lower().replace("_", "-")
    if normalized_game not in GEN5_GAMES:
        raise ValueError("Choose black, white, black2, or white2 for Generation V")

    init_tables()
    save = Gen5_Save(path=path, game=normalized_game)
    save.print_all_pokemon()

    extracted = _all_pokemon(save)
    for pokemon in extracted:
        pokemon.game_name = save.game_name

    # Do not mutate/write the save unless the complete DB transaction succeeds.
    add_pokemon_batch(extracted)

    save.party_pokemon = []
    save.box_pokemon = [[] for _ in range(24)]
    output_path = save.write_save()
    print(f"Imported {len(extracted)} Pokémon into SQLite ({save.game_name}).")
    print(f"Wrote Pokémon-free save to {output_path}")
    return output_path


def import_gen6(path: str, game: str) -> str:
    """Import all Pokémon from an X/Y/ORAS decrypted save into SQLite."""
    normalized_game = game.strip().lower().replace("_", "-")
    if normalized_game not in GEN6_GAMES:
        raise ValueError("Choose x, y, omegaruby, or alphasapphire for Generation VI")

    init_tables()
    save = Gen6_Save(path=path, game=normalized_game)
    save.print_all_pokemon()

    extracted = _all_pokemon(save)
    for pokemon in extracted:
        pokemon.game_name = save.game_name

    # Do not clear or write the save until the entire import commits.
    add_pokemon_batch(extracted)

    save.party_pokemon = []
    save.box_pokemon = [[] for _ in range(31)]
    output_path = save.write_save()
    print(f"Imported {len(extracted)} Pokémon into SQLite ({save.game_name}).")
    print(f"Wrote Pokémon-free save to {output_path}")
    return output_path


def import_gen7(path: str, game: str) -> str:
    """Import all Pokémon from a Sun/Moon/Ultra Sun/Ultra Moon save into SQLite."""
    normalized_game = game.strip().lower().replace("_", "-")
    if normalized_game not in GEN7_GAMES:
        raise ValueError("Choose sun, moon, ultrasun, or ultramoon for Generation VII")

    init_tables()
    save = Gen7_Save(path=path, game=normalized_game)
    save.print_all_pokemon()

    extracted = _all_pokemon(save)
    for pokemon in extracted:
        pokemon.game_name = save.game_name

    # Commit the complete batch before modifying or writing the save.
    add_pokemon_batch(extracted)

    save.party_pokemon = []
    save.box_pokemon = [[] for _ in range(32)]
    output_path = save.write_save()
    print(f"Imported {len(extracted)} Pokémon into SQLite ({save.game_name}).")
    print(f"Wrote Pokémon-free save to {output_path}")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Extract Pokémon from Generation I–VII saves into SQLite and "
            "write a copy without party/PC Pokémon."
        )
    )
    parser.add_argument("save_file", help="Path to a save file (see README for per-generation format requirements)")
    parser.add_argument(
        "--game",
        choices=(
            "red", "blue", "yellow", "gold-silver", "crystal", "ruby", "sapphire", "emerald",
            "firered", "leafgreen", "diamond", "pearl", "platinum",
            "heartgold", "soulsilver", "black", "white", "black2", "white2",
            "x", "y", "omegaruby", "alphasapphire",
            "sun", "moon", "ultrasun", "ultramoon", "auto",
        ),
        default="gold-silver",
        help=(
            "Game version/layout (default: gold-silver). Gen I supports red, blue, and yellow; "
            "Gen III supports ruby, "
            "sapphire, emerald, firered, leafgreen, or auto; Gen IV supports "
            "diamond, pearl, platinum, heartgold, and soulsilver; Gen V supports "
            "black, white, black2, and white2; Gen VI supports x, y, omegaruby, "
            "and alphasapphire (decrypted 3DS main saves only); Gen VII supports sun, moon, "
            "ultrasun, and ultramoon (decrypted 3DS main saves only)."
        ),
    )
    args = parser.parse_args()

    selected_game = args.game.lower()
    if selected_game in GEN1_GAMES:
        import_gen1(args.save_file, game=selected_game)
    elif selected_game in GEN3_GAMES or selected_game == "auto":
        import_gen3(args.save_file, game=selected_game)
    elif selected_game in GEN4_GAMES:
        import_gen4(args.save_file, game=selected_game)
    elif selected_game in GEN5_GAMES:
        import_gen5(args.save_file, game=selected_game)
    elif selected_game in GEN6_GAMES:
        import_gen6(args.save_file, game=selected_game)
    elif selected_game in GEN7_GAMES:
        import_gen7(args.save_file, game=selected_game)
    else:
        import_gen2(args.save_file, game=selected_game)


if __name__ == "__main__":
    main()
