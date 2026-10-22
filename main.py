"""Extract Pokémon from Generation I through VII saves into SQLite.

The original save is never overwritten. Once all extracted Pokémon have been
committed to SQLite in one transaction, a modified copy without party/PC
Pokémon is written beside the original with the suffix ``.new``.
"""

import argparse
from pathlib import Path

from db import add_pokemon_batch, init_tables
from gen1 import Gen1_Save
from gen2 import (
    Crystal_Save,
    Gen2_Save,
    is_valid_crystal_save,
    is_valid_gold_silver_save,
)
from gen3 import Gen3_Save
from gen4 import Gen4_Save
from gen5 import Gen5_Save
from gen6 import Gen6_Save
from gen7 import Gen7_Save

GEN1_GAMES = {"red", "blue", "yellow"}
GEN2_GAMES = {"gold", "silver", "gold-silver", "crystal"}
GEN3_GAMES = {"ruby", "sapphire", "emerald", "firered", "leafgreen"}
GEN4_GAMES = {"diamond", "pearl", "platinum", "heartgold", "soulsilver"}
GEN5_GAMES = {"black", "white", "black2", "white2"}
GEN6_GAMES = {"x", "y", "omegaruby", "alphasapphire"}
GEN7_GAMES = {"sun", "moon", "ultrasun", "ultramoon"}


def _all_pokemon(save) -> list:
    extracted = list(save.party_pokemon)
    for box in save.box_pokemon:
        extracted.extend(box)
    return extracted


def import_gen1(path: str, game: str, *, source_game: str | None = None) -> str:
    """Import all Pokémon from an English Red/Blue/Yellow save into SQLite."""
    normalized_game = game.strip().lower()
    if normalized_game not in GEN1_GAMES:
        raise ValueError("Generation I supports only red, blue, or yellow")

    init_tables()
    save = Gen1_Save(path=path, game=normalized_game)
    save.print_all_pokemon()

    extracted = _all_pokemon(save)
    provenance = source_game or save.game_name
    for pokemon in extracted:
        pokemon.game_name = provenance

    # Commit the full extract before clearing or writing any save data.
    add_pokemon_batch(extracted)

    save.party_pokemon = []
    save.box_pokemon = [[] for _ in range(12)]
    output_path = save.write_save()
    print(f"Imported {len(extracted)} Pokémon into SQLite ({provenance}).")
    print(f"Wrote Pokémon-free save to {output_path}")
    return output_path


def import_gen2(path: str, game: str = "gold-silver", *, source_game: str | None = None) -> str:
    """Import every Pokémon from an English Gold/Silver or Crystal save."""
    normalized_game = game.strip().lower().replace("_", "-")
    if normalized_game in ("gold", "silver", "gold-silver"):
        save_class = Gen2_Save
        layout_game = "gold-silver"
    elif normalized_game == "crystal":
        save_class = Crystal_Save
        layout_game = "crystal"
    else:
        raise ValueError(
            "Unsupported Generation II game. Choose 'gold-silver' or 'crystal'."
        )

    init_tables()
    save = save_class(path=path)
    save.print_all_pokemon()

    extracted = _all_pokemon(save)
    provenance = source_game or layout_game
    for pokemon in extracted:
        pokemon.game_name = provenance
    # The complete import is committed before the output save is modified.
    add_pokemon_batch(extracted)

    save.party_pokemon = []
    save.box_pokemon = [[] for _ in range(14)]
    output_path = save.write_save()
    print(f"Imported {len(extracted)} Pokémon into SQLite ({provenance}).")
    print(f"Wrote Pokémon-free save to {output_path}")
    return output_path


def import_gen3(path: str, game: str, *, source_game: str | None = None) -> str:
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
    provenance = source_game or save.game_name
    for pokemon in extracted:
        pokemon.game_name = provenance

    # add_pokemon_batch commits atomically, or raises before save mutation.
    add_pokemon_batch(extracted)

    save.party_pokemon = []
    save.box_pokemon = [[] for _ in range(14)]
    output_path = save.write_save()
    print(f"Imported {len(extracted)} Pokémon into SQLite ({provenance}).")
    print(f"Wrote Pokémon-free save to {output_path}")
    return output_path


def import_gen4(path: str, game: str, *, source_game: str | None = None) -> str:
    """Import all Pokémon from a Diamond/Pearl/Platinum/HGSS save into SQLite."""
    normalized_game = game.strip().lower().replace("_", "-")
    init_tables()
    save = Gen4_Save(path=path, game=normalized_game)
    save.print_all_pokemon()

    extracted = _all_pokemon(save)
    provenance = source_game or save.game_name
    for pokemon in extracted:
        pokemon.game_name = provenance

    # SQLite commits the entire extraction atomically before save mutation.
    add_pokemon_batch(extracted)

    save.party_pokemon = []
    save.box_pokemon = [[] for _ in range(18)]
    output_path = save.write_save()
    print(f"Imported {len(extracted)} Pokémon into SQLite ({provenance}).")
    print(f"Wrote Pokémon-free save to {output_path}")
    return output_path


def import_gen5(path: str, game: str, *, source_game: str | None = None) -> str:
    """Import all Pokémon from a Black/White/Black 2/White 2 save into SQLite."""
    normalized_game = game.strip().lower().replace("_", "-")
    if normalized_game not in GEN5_GAMES:
        raise ValueError("Choose black, white, black2, or white2 for Generation V")

    init_tables()
    save = Gen5_Save(path=path, game=normalized_game)
    save.print_all_pokemon()

    extracted = _all_pokemon(save)
    provenance = source_game or save.game_name
    for pokemon in extracted:
        pokemon.game_name = provenance

    # Do not mutate/write the save unless the complete DB transaction succeeds.
    add_pokemon_batch(extracted)

    save.party_pokemon = []
    save.box_pokemon = [[] for _ in range(24)]
    output_path = save.write_save()
    print(f"Imported {len(extracted)} Pokémon into SQLite ({provenance}).")
    print(f"Wrote Pokémon-free save to {output_path}")
    return output_path


def import_gen6(path: str, game: str, *, source_game: str | None = None) -> str:
    """Import all Pokémon from an X/Y/ORAS decrypted save into SQLite."""
    normalized_game = game.strip().lower().replace("_", "-")
    if normalized_game not in GEN6_GAMES:
        raise ValueError("Choose x, y, omegaruby, or alphasapphire for Generation VI")

    init_tables()
    save = Gen6_Save(path=path, game=normalized_game)
    save.print_all_pokemon()

    extracted = _all_pokemon(save)
    provenance = source_game or save.game_name
    for pokemon in extracted:
        pokemon.game_name = provenance

    # Do not clear or write the save until the entire import commits.
    add_pokemon_batch(extracted)

    save.party_pokemon = []
    save.box_pokemon = [[] for _ in range(31)]
    output_path = save.write_save()
    print(f"Imported {len(extracted)} Pokémon into SQLite ({provenance}).")
    print(f"Wrote Pokémon-free save to {output_path}")
    return output_path


def import_gen7(path: str, game: str, *, source_game: str | None = None) -> str:
    """Import all Pokémon from a Sun/Moon/Ultra Sun/Ultra Moon save into SQLite."""
    normalized_game = game.strip().lower().replace("_", "-")
    if normalized_game not in GEN7_GAMES:
        raise ValueError("Choose sun, moon, ultrasun, or ultramoon for Generation VII")

    init_tables()
    save = Gen7_Save(path=path, game=normalized_game)
    save.print_all_pokemon()

    extracted = _all_pokemon(save)
    provenance = source_game or save.game_name
    for pokemon in extracted:
        pokemon.game_name = provenance

    # Commit the complete batch before modifying or writing the save.
    add_pokemon_batch(extracted)

    save.party_pokemon = []
    save.box_pokemon = [[] for _ in range(32)]
    output_path = save.write_save()
    print(f"Imported {len(extracted)} Pokémon into SQLite ({provenance}).")
    print(f"Wrote Pokémon-free save to {output_path}")
    return output_path



def _probe_layout(path: str, save_class, game: str):
    """Return a validated save instance, or None if this layout does not fit."""
    try:
        return save_class(path=path, game=game)
    except (OSError, ValueError, IndexError, OverflowError):
        return None


def _probe_oversized_gen1(path: str):
    """Recognize a padded Gen I SRAM dump without misclassifying random files.

    Gen I deliberately accepts data larger than 32 KiB. For oversized inputs,
    require at least one valid PC-bank checksum in addition to the main checksum
    and valid current-box number to reduce accidental matches with other formats.
    """
    candidate = _probe_layout(path, Gen1_Save, "red")
    if candidate is None or not any(candidate._box_bank_valid.values()):
        return None
    return candidate


def detect_save_game(path: str) -> tuple[int, str, str]:
    """Detect a supported save generation and the layout needed to read it.

    Returns ``(generation, handler_game, source_game)``. Some retail pairs
    (for example Red/Blue/Yellow or Diamond/Pearl) share indistinguishable save
    layouts, so automatic mode records a generation-level source label instead
    of pretending to know the exact title. Layouts that affect parsing are
    still selected and validated before the save can be modified.
    """
    raw = Path(path).read_bytes()
    size = len(raw)

    # Gen I and Gen II both use 32 KiB SRAM. Use stored checksums rather than
    # file size alone: the older Gen II reader intentionally accepts incomplete
    # dumps for explicit/manual use, which is too permissive for auto-detection.
    if size == 0x8000:
        gen1_valid = _probe_layout(path, Gen1_Save, "red") is not None
        gen2_matches = []
        if is_valid_gold_silver_save(raw):
            gen2_matches.append(("gold-silver", "gold-silver"))
        if is_valid_crystal_save(raw):
            gen2_matches.append(("crystal", "crystal"))

        if gen1_valid and not gen2_matches:
            return 1, "red", "generation-1"
        if not gen1_valid and len(gen2_matches) == 1:
            handler_game, source_game = gen2_matches[0]
            return 2, handler_game, source_game
        if len(gen2_matches) > 1 or (gen1_valid and gen2_matches):
            raise ValueError(
                "The 32 KiB save matches more than one supported Generation I/II "
                "format. Specify --game explicitly."
            )
        raise ValueError(
            "Could not identify this 32 KiB save as a checksum-valid English "
            "Generation I or II save. Specify --game explicitly if the dump is "
            "known to be supported."
        )

    # A common oversized Generation I dump is 128 KiB. Prefer a fully valid
    # Gen III slot when present; otherwise accept the Gen I checksum/layout.
    if size == 0x20000:
        try:
            Gen3_Save(path=path, game="auto")
            return 3, "auto", "generation-3"
        except ValueError as exc:
            # Preserve meaningful errors for a structurally valid Gen III file
            # whose layout is ambiguous or whose contained records are invalid.
            if "No complete valid Generation III save slot" not in str(exc):
                raise
        if _probe_oversized_gen1(path) is not None:
            return 1, "red", "generation-1"
        raise ValueError(
            "Could not identify this 128 KiB file as a valid Generation I or III "
            "save. Ensure it is a supported raw save dump."
        )

    # Generation IV and V both use 512 KiB files, but their block structures
    # and checksums differ. Probe representative layouts for each family.
    if size == 0x80000:
        gen4_matches = []
        for game in ("diamond", "platinum", "heartgold"):
            candidate = _probe_layout(path, Gen4_Save, game)
            if candidate is not None:
                gen4_matches.append((game, candidate.profile["profile"]))
        gen5_matches = []
        for game in ("black", "black2"):
            candidate = _probe_layout(path, Gen5_Save, game)
            if candidate is not None:
                gen5_matches.append((game, candidate.profile["family"]))

        if gen4_matches and not gen5_matches:
            profiles = {profile for _game, profile in gen4_matches}
            if len(profiles) != 1:
                raise ValueError(
                    "The save matches multiple incompatible Generation IV layouts. "
                    "Specify --game explicitly."
                )
            profile = profiles.pop()
            layout_game = {"dp": "diamond", "pt": "platinum", "hgss": "heartgold"}[profile]
            return 4, layout_game, "generation-4"
        if gen5_matches and not gen4_matches:
            families = {family for _game, family in gen5_matches}
            if len(families) != 1:
                raise ValueError(
                    "The save matches multiple incompatible Generation V layouts. "
                    "Specify --game explicitly."
                )
            family = families.pop()
            layout_game = "black" if family == "bw" else "black2"
            return 5, layout_game, "generation-5"
        if gen4_matches and gen5_matches:
            raise ValueError(
                "The 512 KiB save validates as both Generation IV and V. "
                "Specify --game explicitly rather than risking the wrong layout."
            )
        if _probe_oversized_gen1(path) is not None:
            return 1, "red", "generation-1"
        raise ValueError(
            "The 512 KiB file is not a valid supported Generation IV or V save. "
            "Check that it is a raw, unheadered save file."
        )

    # The supported decrypted 3DS main-save sizes uniquely identify the family.
    for game in ("x", "omegaruby"):
        candidate = _probe_layout(path, Gen6_Save, game)
        if candidate is not None:
            return 6, game, "generation-6"
    for game in ("sun", "ultrasun"):
        candidate = _probe_layout(path, Gen7_Save, game)
        if candidate is not None:
            return 7, game, "generation-7"

    if size > 0x8000 and _probe_oversized_gen1(path) is not None:
        return 1, "red", "generation-1"

    raise ValueError(
        f"Could not automatically identify a supported Pokémon save ({size:,} bytes). "
        "Use --game to select a supported game, and check the README for the "
        "required raw/decrypted save format."
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Extract Pokémon from Generation I–VII saves into SQLite and "
            "write a copy without party/PC Pokémon."
        )
    )
    parser.add_argument(
        "save_file",
        help="Path to a save file (see README for per-generation format requirements)",
    )
    parser.add_argument(
        "--game",
        choices=(
            "red", "blue", "yellow", "gold", "silver", "gold-silver", "crystal",
            "ruby", "sapphire", "emerald",
            "firered", "leafgreen", "diamond", "pearl", "platinum",
            "heartgold", "soulsilver", "black", "white", "black2", "white2",
            "x", "y", "omegaruby", "alphasapphire",
            "sun", "moon", "ultrasun", "ultramoon", "auto",
        ),
        default="auto",
        help=(
            "Game version/layout (default: auto). Auto validates the save format "
            "across Generations I–VII. Some titles share the same save layout, so "
            "auto may report only the generation when the exact title is not encoded "
            "unambiguously. Gen VI/VII require decrypted 3DS main saves."
        ),
    )
    args = parser.parse_args()

    selected_game = args.game.strip().lower()
    if selected_game == "auto":
        generation, layout_game, provenance = detect_save_game(args.save_file)
        print(f"Auto-detected Generation {generation} save layout ({provenance}).")
        if generation == 1:
            import_gen1(args.save_file, game=layout_game, source_game=provenance)
        elif generation == 2:
            import_gen2(args.save_file, game=layout_game, source_game=provenance)
        elif generation == 3:
            import_gen3(args.save_file, game=layout_game, source_game=provenance)
        elif generation == 4:
            import_gen4(args.save_file, game=layout_game, source_game=provenance)
        elif generation == 5:
            import_gen5(args.save_file, game=layout_game, source_game=provenance)
        elif generation == 6:
            import_gen6(args.save_file, game=layout_game, source_game=provenance)
        elif generation == 7:
            import_gen7(args.save_file, game=layout_game, source_game=provenance)
        else:
            parser.error(f"Unable to auto-detect save type!")

    elif selected_game in GEN1_GAMES:
        import_gen1(args.save_file, game=selected_game)
    elif selected_game in GEN3_GAMES:
        import_gen3(args.save_file, game=selected_game)
    elif selected_game in GEN4_GAMES:
        import_gen4(args.save_file, game=selected_game)
    elif selected_game in GEN5_GAMES:
        import_gen5(args.save_file, game=selected_game)
    elif selected_game in GEN6_GAMES:
        import_gen6(args.save_file, game=selected_game)
    elif selected_game in GEN7_GAMES:
        import_gen7(args.save_file, game=selected_game)
    elif selected_game in GEN2_GAMES:
        import_gen2(args.save_file, game=selected_game)
    else:  # argparse choices should keep this unreachable.
        parser.error(f"Unsupported game selection: {selected_game}")


if __name__ == "__main__":
    main()
