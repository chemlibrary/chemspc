"""Generation II Pokémon data model and binary serialization helpers."""
from __future__ import annotations

from dataclasses import dataclass


def _read_int(data: bytes | bytearray, size: int) -> int:
    if len(data) != size:
        raise ValueError(f"Expected {size} bytes, received {len(data)}")
    return int.from_bytes(data, byteorder="big")


def _write_int(value: int, size: int, field: str) -> bytes:
    try:
        value = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an integer") from exc
    if not 0 <= value < (1 << (8 * size)):
        raise ValueError(f"{field}={value} does not fit in {size} byte(s)")
    return value.to_bytes(size, byteorder="big")


@dataclass
class Pokemon:
    generation: int = 0
    name: str = ""
    species: int = 0
    held_item: int = 0
    move1: int = 0
    move2: int = 0
    move3: int = 0
    move4: int = 0
    original_trainer: int = 0
    original_trainer_name: str = ""
    exp: int = 0
    hp_ev: int = 0
    attack_ev: int = 0
    defense_ev: int = 0
    speed_ev: int = 0
    special_ev: int = 0
    iv: int = 0
    move1_pp: int = 0
    move2_pp: int = 0
    move3_pp: int = 0
    move4_pp: int = 0
    friendship: int = 0
    pokerus: int = 0
    caught: int = 0
    level: int = 0
    status_condition: int = 0
    current_hp: int = 0
    max_hp: int = 0
    attack: int = 0
    defense: int = 0
    speed: int = 0
    special_attack: int = 0
    special_defense: int = 0

    def init_gen2(self, data: bytes | bytearray, party_pokemon: bool = False) -> None:
        """Populate this instance from a Generation II Pokémon data block."""
        expected = 48 if party_pokemon else 32
        if len(data) != expected:
            raise ValueError(f"Generation II Pokémon data must be {expected} bytes")
        self.generation = 2
        self.species = data[0]
        self.held_item = data[1]
        self.move1, self.move2, self.move3, self.move4 = data[2:6]
        self.original_trainer = _read_int(data[6:8], 2)
        self.exp = _read_int(data[8:11], 3)
        self.hp_ev = _read_int(data[11:13], 2)
        self.attack_ev = _read_int(data[13:15], 2)
        self.defense_ev = _read_int(data[15:17], 2)
        self.speed_ev = _read_int(data[17:19], 2)
        self.special_ev = _read_int(data[19:21], 2)
        self.iv = _read_int(data[21:23], 2)
        self.move1_pp, self.move2_pp, self.move3_pp, self.move4_pp = data[23:27]
        self.friendship = data[27]
        self.pokerus = data[28]
        self.caught = _read_int(data[29:31], 2)
        self.level = data[31]
        if party_pokemon:
            self.status_condition = data[32]
            # Byte 33 is unused in party Pokémon blocks.
            self.current_hp = _read_int(data[34:36], 2)
            self.max_hp = _read_int(data[36:38], 2)
            self.attack = _read_int(data[38:40], 2)
            self.defense = _read_int(data[40:42], 2)
            self.speed = _read_int(data[42:44], 2)
            self.special_attack = _read_int(data[44:46], 2)
            self.special_defense = _read_int(data[46:48], 2)
        else:
            self.status_condition = 0
            self.current_hp = 0
            self.max_hp = 0
            self.attack = 0
            self.defense = 0
            self.speed = 0
            self.special_attack = 0
            self.special_defense = 0

    def export_gen2(self, party_pokemon: bool = False) -> bytearray:
        """Serialize to a 32-byte box block or 48-byte party block."""
        raw = bytearray()
        raw.append(int(self.species))
        raw.append(int(self.held_item))
        raw.extend(int(v) for v in (self.move1, self.move2, self.move3, self.move4))
        raw.extend(_write_int(self.original_trainer, 2, "original_trainer"))
        raw.extend(_write_int(self.exp, 3, "exp"))
        for key in ("hp_ev", "attack_ev", "defense_ev", "speed_ev", "special_ev", "iv"):
            raw.extend(_write_int(getattr(self, key), 2, key))
        for key in ("move1_pp", "move2_pp", "move3_pp", "move4_pp", "friendship", "pokerus"):
            raw.append(int(_write_int(getattr(self, key), 1, key)[0]))
        raw.extend(_write_int(self.caught, 2, "caught"))
        raw.append(int(_write_int(self.level, 1, "level")[0]))
        if party_pokemon:
            raw.append(int(_write_int(self.status_condition, 1, "status_condition")[0]))
            raw.append(0)  # Unused byte in the party structure.
            for key in ("current_hp", "max_hp", "attack", "defense", "speed", "special_attack", "special_defense"):
                raw.extend(_write_int(getattr(self, key), 2, key))
        expected = 48 if party_pokemon else 32
        if len(raw) != expected:
            raise AssertionError(f"Internal serializer error: expected {expected} bytes, got {len(raw)}")
        return raw

    # Original public API is retained for callers in older scripts.
    def export_gen2_bytes(self, party_pokemon: bool = False) -> bytes:
        return bytes(self.export_gen2(party_pokemon=party_pokemon))
