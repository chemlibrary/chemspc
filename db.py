"""SQLite persistence for active/inactive Pokémon with generation-native payloads."""
from __future__ import annotations

import base64
import json
import os
import sqlite3
from pathlib import Path
from typing import Iterable

from pokemon import Pokemon

DATABASE_NAME = os.environ.get("CHEMSPC_DATABASE", str(Path(__file__).with_name("chemspc.db")))
POKEMON_COLUMNS = (
    "generation", "name", "species", "held_item", "move1", "move2", "move3", "move4",
    "original_trainer", "original_trainer_name", "exp", "hp_ev", "attack_ev", "defense_ev",
    "speed_ev", "special_ev", "iv", "move1_pp", "move2_pp", "move3_pp", "move4_pp",
    "friendship", "pokerus", "caught", "level", "status_condition", "current_hp", "max_hp",
    "attack", "defense", "speed", "special_attack", "special_defense",
)
_TEXT_FIELDS = {"name", "original_trainer_name"}
_SCHEMA_FIELDS = ", ".join(
    f"{field} {'TEXT' if field in _TEXT_FIELDS else 'INTEGER'}" for field in POKEMON_COLUMNS
)
_ACTIVE_SCHEMA = f"CREATE TABLE IF NOT EXISTS pokemon (uid INTEGER PRIMARY KEY AUTOINCREMENT, {_SCHEMA_FIELDS}, record_payload TEXT)"
_INACTIVE_SCHEMA = f"CREATE TABLE IF NOT EXISTS inactive_pokemon (uid INTEGER, {_SCHEMA_FIELDS}, record_payload TEXT)"


def _pack(value):
    """JSON encode bytes and tuples without pickle (the database is user-editable)."""
    if isinstance(value, (bytes, bytearray, memoryview)):
        return {"__chemspc_type__": "bytes", "value": base64.b64encode(bytes(value)).decode("ascii")}
    if isinstance(value, tuple):
        return {"__chemspc_type__": "tuple", "value": [_pack(item) for item in value]}
    if isinstance(value, list):
        return [_pack(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _pack(item) for key, item in value.items()}
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    # Parser metadata should consist of the types above. Fail closed rather than
    # silently dropping an unfamiliar object needed for a lossless save write.
    raise TypeError(f"Unsupported Pokémon metadata value: {type(value).__name__}")


def _unpack(value):
    if isinstance(value, list):
        return [_unpack(item) for item in value]
    if isinstance(value, dict):
        tag = value.get("__chemspc_type__")
        if tag == "bytes":
            return base64.b64decode(value["value"], validate=True)
        if tag == "tuple":
            return tuple(_unpack(item) for item in value["value"])
        return {key: _unpack(item) for key, item in value.items()}
    return value


def encode_record_payload(pokemon: Pokemon) -> str:
    return json.dumps(_pack(vars(pokemon)), ensure_ascii=False, separators=(",", ":"))


def restore_record_payload(pokemon: Pokemon, payload: str | bytes | None) -> Pokemon:
    if not payload:
        return pokemon
    try:
        decoded = json.loads(payload)
        if not isinstance(decoded, dict):
            raise ValueError("Pokémon record metadata is not an object")
        values = _unpack(decoded)
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("A Pokémon's retained save-record metadata is damaged.") from exc
    for name, value in values.items():
        setattr(pokemon, name, value)
    return pokemon


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DATABASE_NAME, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _ensure_payload_column(conn: sqlite3.Connection, table: str) -> None:
    present = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if "record_payload" not in present:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN record_payload TEXT")


def init_tables() -> bool:
    conn = connect()
    try:
        conn.execute(_ACTIVE_SCHEMA)
        conn.execute(_INACTIVE_SCHEMA)
        # Upgrade databases created by the previous Flask update. Existing rows
        # remain valid but cannot be exported to formats requiring raw records;
        # they have no payload and will be marked incompatible in the UI.
        _ensure_payload_column(conn, "pokemon")
        _ensure_payload_column(conn, "inactive_pokemon")
        conn.commit()
        return True
    finally:
        conn.close()


def _pokemon_values(pokemon: Pokemon) -> tuple:
    return tuple(getattr(pokemon, col) for col in POKEMON_COLUMNS)


def row_to_pokemon(row: sqlite3.Row | dict) -> Pokemon:
    pokemon = Pokemon(**{column: row[column] for column in POKEMON_COLUMNS})
    return restore_record_payload(pokemon, row.get("record_payload") if isinstance(row, dict) else row["record_payload"])


def add_pokemon(pokemon: Pokemon) -> bool:
    conn = connect()
    try:
        insert_pokemon(conn, pokemon)
        conn.commit()
        return True
    finally:
        conn.close()


def insert_pokemon(conn: sqlite3.Connection, pokemon: Pokemon) -> int:
    columns = ", ".join((*POKEMON_COLUMNS, "record_payload"))
    placeholders = ", ".join("?" for _ in range(len(POKEMON_COLUMNS) + 1))
    cur = conn.execute(
        f"INSERT INTO pokemon ({columns}) VALUES ({placeholders})",
        (*_pokemon_values(pokemon), encode_record_payload(pokemon)),
    )
    return int(cur.lastrowid)


def list_pokemon(active: bool = True) -> list[dict]:
    table = "pokemon" if active else "inactive_pokemon"
    conn = connect()
    try:
        rows = conn.execute(
            f"SELECT uid, {', '.join(POKEMON_COLUMNS)}, record_payload FROM {table} ORDER BY uid"
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_active_pokemon(uids: Iterable[int]) -> dict[int, dict]:
    requested = sorted({int(uid) for uid in uids})
    if not requested:
        return {}
    placeholders = ", ".join("?" for _ in requested)
    conn = connect()
    try:
        rows = conn.execute(
            f"SELECT uid, {', '.join(POKEMON_COLUMNS)}, record_payload FROM pokemon WHERE uid IN ({placeholders})",
            requested,
        ).fetchall()
        return {int(row["uid"]): dict(row) for row in rows}
    finally:
        conn.close()


def move_active_to_inactive(conn: sqlite3.Connection, uid: int) -> None:
    """Move an active row into the inactive table without losing native record data."""
    row = conn.execute(
        f"SELECT uid, {', '.join(POKEMON_COLUMNS)}, record_payload FROM pokemon WHERE uid = ?",
        (int(uid),),
    ).fetchone()
    if row is None:
        raise ValueError(f"Pokémon uid {uid} is no longer active")
    cols = "uid, " + ", ".join((*POKEMON_COLUMNS, "record_payload"))
    placeholders = ", ".join("?" for _ in range(len(POKEMON_COLUMNS) + 2))
    conn.execute(
        f"INSERT INTO inactive_pokemon ({cols}) VALUES ({placeholders})",
        tuple(row[col] for col in ("uid", *POKEMON_COLUMNS, "record_payload")),
    )
    conn.execute("DELETE FROM pokemon WHERE uid = ?", (int(uid),))
