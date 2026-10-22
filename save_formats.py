"""Registry and safe, generation-aware helpers for the existing save handlers.

This module deliberately imports each generation parser lazily.  The original
chemspc repository provides gen1.py through gen7.py; a reduced checkout that
only contains gen2.py can still start and report supported games correctly.
"""
from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class GameSpec:
    generation: int
    label: str
    parser_module: str
    parser_class: str
    party_capacity: int = 6
    box_count: int = 0
    box_capacity: int = 0
    description: str = ""


GAME_SPECS: dict[str, GameSpec] = {
    # Generation I
    "red": GameSpec(1, "Pokémon Red", "gen1", "Gen1_Save", box_count=12, box_capacity=20, description="English 32 KiB SRAM save"),
    "blue": GameSpec(1, "Pokémon Blue", "gen1", "Gen1_Save", box_count=12, box_capacity=20, description="English 32 KiB SRAM save"),
    "yellow": GameSpec(1, "Pokémon Yellow", "gen1", "Gen1_Save", box_count=12, box_capacity=20, description="English 32 KiB SRAM save"),
    # Generation II
    "gold-silver": GameSpec(2, "Pokémon Gold / Silver", "gen2", "Gen2_Save", box_count=14, box_capacity=20, description="English 32 KiB SRAM save"),
    "crystal": GameSpec(2, "Pokémon Crystal", "gen2", "Crystal_Save", box_count=14, box_capacity=20, description="English 32 KiB SRAM save"),
    # Generation III
    "ruby": GameSpec(3, "Pokémon Ruby", "gen3", "Gen3_Save", box_count=14, box_capacity=30, description="Raw 128 KiB GBA save"),
    "sapphire": GameSpec(3, "Pokémon Sapphire", "gen3", "Gen3_Save", box_count=14, box_capacity=30, description="Raw 128 KiB GBA save"),
    "emerald": GameSpec(3, "Pokémon Emerald", "gen3", "Gen3_Save", box_count=14, box_capacity=30, description="Raw 128 KiB GBA save"),
    "firered": GameSpec(3, "Pokémon FireRed", "gen3", "Gen3_Save", box_count=14, box_capacity=30, description="Raw 128 KiB GBA save"),
    "leafgreen": GameSpec(3, "Pokémon LeafGreen", "gen3", "Gen3_Save", box_count=14, box_capacity=30, description="Raw 128 KiB GBA save"),
    # Generation IV
    "diamond": GameSpec(4, "Pokémon Diamond", "gen4", "Gen4_Save", box_count=18, box_capacity=30, description="Raw unheadered 512 KiB DS save"),
    "pearl": GameSpec(4, "Pokémon Pearl", "gen4", "Gen4_Save", box_count=18, box_capacity=30, description="Raw unheadered 512 KiB DS save"),
    "platinum": GameSpec(4, "Pokémon Platinum", "gen4", "Gen4_Save", box_count=18, box_capacity=30, description="Raw unheadered 512 KiB DS save"),
    "heartgold": GameSpec(4, "Pokémon HeartGold", "gen4", "Gen4_Save", box_count=18, box_capacity=30, description="Raw unheadered 512 KiB DS save"),
    "soulsilver": GameSpec(4, "Pokémon SoulSilver", "gen4", "Gen4_Save", box_count=18, box_capacity=30, description="Raw unheadered 512 KiB DS save"),
    # Generation V
    "black": GameSpec(5, "Pokémon Black", "gen5", "Gen5_Save", box_count=24, box_capacity=30, description="Raw unheadered 512 KiB DS save"),
    "white": GameSpec(5, "Pokémon White", "gen5", "Gen5_Save", box_count=24, box_capacity=30, description="Raw unheadered 512 KiB DS save"),
    "black2": GameSpec(5, "Pokémon Black 2", "gen5", "Gen5_Save", box_count=24, box_capacity=30, description="Raw unheadered 512 KiB DS save"),
    "white2": GameSpec(5, "Pokémon White 2", "gen5", "Gen5_Save", box_count=24, box_capacity=30, description="Raw unheadered 512 KiB DS save"),
    # Generation VI (decrypted 3DS main save, not encrypted outer container)
    "x": GameSpec(6, "Pokémon X", "gen6", "Gen6_Save", box_count=31, box_capacity=30, description="Decrypted PKHeX-compatible 3DS main save"),
    "y": GameSpec(6, "Pokémon Y", "gen6", "Gen6_Save", box_count=31, box_capacity=30, description="Decrypted PKHeX-compatible 3DS main save"),
    "omegaruby": GameSpec(6, "Pokémon Omega Ruby", "gen6", "Gen6_Save", box_count=31, box_capacity=30, description="Decrypted PKHeX-compatible 3DS main save"),
    "alphasapphire": GameSpec(6, "Pokémon Alpha Sapphire", "gen6", "Gen6_Save", box_count=31, box_capacity=30, description="Decrypted PKHeX-compatible 3DS main save"),
    # Generation VII (decrypted 3DS main save)
    "sun": GameSpec(7, "Pokémon Sun", "gen7", "Gen7_Save", box_count=32, box_capacity=30, description="Decrypted PKHeX-compatible 3DS main save"),
    "moon": GameSpec(7, "Pokémon Moon", "gen7", "Gen7_Save", box_count=32, box_capacity=30, description="Decrypted PKHeX-compatible 3DS main save"),
    "ultrasun": GameSpec(7, "Pokémon Ultra Sun", "gen7", "Gen7_Save", box_count=32, box_capacity=30, description="Decrypted PKHeX-compatible 3DS main save"),
    "ultramoon": GameSpec(7, "Pokémon Ultra Moon", "gen7", "Gen7_Save", box_count=32, box_capacity=30, description="Decrypted PKHeX-compatible 3DS main save"),
}

# Exact input lengths expected by the project's native readers/writers. Emulator
# formats sometimes append RTC or other footer bytes; those are not part of the
# raw save layout accepted by these handlers. Sizes for Gen VI/VII differ by title.
SAVE_SIZES: dict[str, int] = {
    # Generation I: some emulator tools emit a 128 KiB dump; only the first
    # 32 KiB are the English cartridge SRAM layout used by this parser.
    "red": 0x8000,
    "blue": 0x8000,
    "yellow": 0x8000,
    # Generation II
    "gold-silver": 0x8000,
    "crystal": 0x8000,
    # Generation III: raw 128 KiB flash saves
    "ruby": 0x20000,
    "sapphire": 0x20000,
    "emerald": 0x20000,
    "firered": 0x20000,
    "leafgreen": 0x20000,
    # Generation IV: raw unheadered 512 KiB saves
    "diamond": 0x80000,
    "pearl": 0x80000,
    "platinum": 0x80000,
    "heartgold": 0x80000,
    "soulsilver": 0x80000,
    # Generation V: raw unheadered 512 KiB saves (the native handler validates
    # the smaller mirrored save copies inside this outer raw save).
    "black": 0x80000,
    "white": 0x80000,
    "black2": 0x80000,
    "white2": 0x80000,
    # Generation VI: decrypted 3DS main save
    "x": 0x65600,
    "y": 0x65600,
    "omegaruby": 0x76000,
    "alphasapphire": 0x76000,
    # Generation VII: decrypted 3DS main save
    "sun": 0x6BE00,
    "moon": 0x6BE00,
    "ultrasun": 0x6CC00,
    "ultramoon": 0x6CC00,
}


def supported_games() -> list[tuple[str, str, int, str]]:
    """Return (game key, label, generation, format description) for templates."""
    return [(key, spec.label, spec.generation, spec.description) for key, spec in GAME_SPECS.items()]


def get_game_spec(game: str) -> GameSpec:
    key = (game or "").strip().lower().replace("_", "-")
    if key not in GAME_SPECS:
        raise ValueError("Choose one of the supported English Generation I–VII games.")
    return GAME_SPECS[key]


def required_save_size(game: str) -> int:
    """Return the exact raw save size expected for the selected title."""
    key = (game or "").strip().lower().replace("_", "-")
    get_game_spec(key)  # Validate the title before consulting the size registry.
    try:
        return SAVE_SIZES[key]
    except KeyError as exc:  # Defensive guard if a future title lacks a size.
        raise ValueError(f"No required save size is configured for {key!r}.") from exc


def trim_save_file(path: str | Path, game: str) -> tuple[int, int]:
    """Trim trailing upload bytes to the selected game's raw save size.

    Returns (original_size, retained_size). Short files are rejected rather than
    padded, because padding can turn incomplete/corrupt saves into misleading input.
    Only the staged upload path is modified; the user's original local file is
    never touched by this function.
    """
    save_path = Path(path)
    required = required_save_size(game)
    try:
        original_size = save_path.stat().st_size
    except OSError as exc:
        raise ValueError(f"Unable to read uploaded save file: {exc}") from exc

    if original_size < required:
        raise ValueError(
            f"The uploaded save is too small for the selected game "
            f"({original_size:,} bytes; {required:,} bytes required). "
            "The file appears incomplete, so it was not modified."
        )

    if original_size > required:
        try:
            with save_path.open("r+b") as stream:
                stream.truncate(required)
        except OSError as exc:
            raise ValueError(f"Unable to trim uploaded save file: {exc}") from exc

    return original_size, required


def open_save(path: str | Path, game: str):
    """Instantiate the repository's native parser for the selected title."""
    key = (game or "").strip().lower().replace("_", "-")
    spec = get_game_spec(key)
    try:
        module = import_module(spec.parser_module)
    except ModuleNotFoundError as exc:
        raise ValueError(
            f"The {spec.parser_module}.py save handler is missing from this checkout. "
            "Keep the original generation handlers from the chemspc repository when "
            "applying the Flask update."
        ) from exc
    parser_class = getattr(module, spec.parser_class, None)
    if parser_class is None:
        raise ValueError(f"The {spec.parser_module}.py handler does not provide {spec.parser_class}.")
    if spec.generation == 1:
        return parser_class(path=path, game=key)
    if spec.generation == 2:
        return parser_class(path=path)
    return parser_class(path=path, game=key)


def box_record(pokemon: Any, generation: int) -> bytes | None:
    """Return retained native box record bytes when this row has them."""
    attr_by_gen = {
        1: "_gen1_box_record",
        3: "gen3_box_record",
        4: "gen4_box_record",
        5: "gen5_box_record",
        6: "gen6_record",
        7: "gen7_record",
    }
    if generation == 2:
        return None  # Gen II records are reconstructed from validated fields.
    attr = attr_by_gen.get(generation)
    value = getattr(pokemon, attr, None) if attr else None
    if not isinstance(value, (bytes, bytearray)):
        return None
    raw = bytes(value)
    # Gen VI/VII use one parser attribute for stored and party forms.
    if generation in (6, 7) and len(raw) >= 232:
        raw = raw[:232]
    expected = {1: 33, 3: 80, 4: 136, 5: 136, 6: 232, 7: 232}.get(generation)
    if expected is None or len(raw) != expected:
        return None
    return raw


def has_native_export_record(pokemon: Any, generation: int) -> bool:
    """Whether the database row retains the binary data needed by that writer."""
    if int(getattr(pokemon, "generation", 0) or 0) != generation:
        return False
    if generation == 2:
        return True
    if box_record(pokemon, generation) is None:
        return False
    if generation == 1:
        return all(
            isinstance(getattr(pokemon, attr, None), (bytes, bytearray)) and len(getattr(pokemon, attr)) == 11
            for attr in ("_gen1_ot_name_bytes", "_gen1_nickname_bytes")
        ) and isinstance(getattr(pokemon, "_gen1_species_index", None), int)
    if generation == 3:
        return isinstance(getattr(pokemon, "_gen3_original_snapshot_box", None), dict)
    return True


def choose_box_slot(save: Any, generation: int, box_index: int) -> int | None:
    """Find a vacant native slot in a compact list of Pokémon for this box."""
    spec = next((s for s in GAME_SPECS.values() if s.generation == generation and s.box_count == len(save.box_pokemon)), None)
    capacity = spec.box_capacity if spec else 30
    occupied: set[int] = set()
    slot_attr = {3: "gen3_box_slot", 4: "gen4_box_slot", 5: "gen5_box_slot", 6: "gen6_box_slot", 7: "gen7_box_slot"}.get(generation)
    box_attr = {3: "gen3_box_number", 4: "gen4_box_index", 5: "gen5_box_index", 6: "gen6_box_index", 7: "gen7_box_index"}.get(generation)
    if slot_attr and box_attr:
        for pokemon in save.box_pokemon[box_index]:
            b = getattr(pokemon, box_attr, None)
            slot = getattr(pokemon, slot_attr, None)
            if b == box_index and isinstance(slot, int) and 0 <= slot < capacity:
                occupied.add(slot)
    else:
        occupied.update(range(len(save.box_pokemon[box_index])))
    return next((slot for slot in range(capacity) if slot not in occupied), None)


def put_in_box(save: Any, pokemon: Any, generation: int, box_index: int, slot: int) -> None:
    """Place an exported Pokémon into a native PC slot, preserving record form."""
    box = save.box_pokemon[box_index]
    if generation == 2:
        box.append(pokemon)
        return
    if generation == 1:
        box.append(pokemon)
        return
    if generation == 3:
        pokemon.gen3_box_number = box_index
        pokemon.gen3_box_slot = slot
        box.append(pokemon)
        return
    if generation == 4:
        pokemon.gen4_box_index = box_index
        pokemon.gen4_box_slot = slot
        box.append(pokemon)
        return
    if generation == 5:
        pokemon.gen5_box_index = box_index
        pokemon.gen5_box_slot = slot
        box.append(pokemon)
        return
    if generation in (6, 7):
        record = box_record(pokemon, generation)
        if record is None:
            raise ValueError(f"No retained Generation {generation} boxed record is available for {getattr(pokemon, 'name', 'Pokémon')}.")
        box_attr = f"gen{generation}_box_index"
        slot_attr = f"gen{generation}_box_slot"
        record_attr = f"gen{generation}_record"
        setattr(pokemon, box_attr, box_index)
        setattr(pokemon, slot_attr, slot)
        setattr(pokemon, record_attr, record)
        if generation == 6:
            start = save.box_offset + (box_index * 30 + slot) * 232
        else:
            start = save.box_offset + (box_index * 30 + slot) * 232
        save.save_bytes[start:start + 232] = record
        # These writers only retain records they know about. Register this newly
        # inserted, same-generation record as a validated native slot.
        save._original_box_records[(box_index, slot)] = record
        box.append(pokemon)
        return
    raise ValueError(f"Exporting records to Generation {generation} is not implemented.")
