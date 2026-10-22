"""SQLite persistence for active and inactive Pokémon."""
from __future__ import annotations

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
_SCHEMA_FIELDS = ", ".join(f"{field} INTEGER" if field not in {"name", "original_trainer_name"} else f"{field} TEXT" for field in POKEMON_COLUMNS)
_ACTIVE_SCHEMA = f"CREATE TABLE IF NOT EXISTS pokemon (uid INTEGER PRIMARY KEY AUTOINCREMENT, {_SCHEMA_FIELDS})"
_INACTIVE_SCHEMA = f"CREATE TABLE IF NOT EXISTS inactive_pokemon (uid INTEGER, {_SCHEMA_FIELDS})"


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DATABASE_NAME, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_tables() -> bool:
    conn = connect()
    try:
        conn.execute(_ACTIVE_SCHEMA)
        conn.execute(_INACTIVE_SCHEMA)
        conn.commit()
        return True
    finally:
        conn.close()


def _pokemon_values(pokemon: Pokemon) -> tuple:
    return tuple(getattr(pokemon, col) for col in POKEMON_COLUMNS)


def row_to_pokemon(row: sqlite3.Row | dict) -> Pokemon:
    return Pokemon(**{col: row[col] for col in POKEMON_COLUMNS})


def add_pokemon(pokemon: Pokemon) -> bool:
    conn = connect()
    try:
        insert_pokemon(conn, pokemon)
        conn.commit()
        return True
    finally:
        conn.close()


def insert_pokemon(conn: sqlite3.Connection, pokemon: Pokemon) -> int:
    columns = ", ".join(POKEMON_COLUMNS)
    placeholders = ", ".join("?" for _ in POKEMON_COLUMNS)
    cur = conn.execute(
        f"INSERT INTO pokemon ({columns}) VALUES ({placeholders})",
        _pokemon_values(pokemon),
    )
    return int(cur.lastrowid)


def list_pokemon(active: bool = True) -> list[dict]:
    table = "pokemon" if active else "inactive_pokemon"
    conn = connect()
    try:
        rows = conn.execute(f"SELECT uid, {', '.join(POKEMON_COLUMNS)} FROM {table} ORDER BY uid").fetchall()
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
            f"SELECT uid, {', '.join(POKEMON_COLUMNS)} FROM pokemon WHERE uid IN ({placeholders})",
            requested,
        ).fetchall()
        return {int(row["uid"]): dict(row) for row in rows}
    finally:
        conn.close()


def move_active_to_inactive(conn: sqlite3.Connection, uid: int) -> None:
    """Move one active row into the recovery table without changing its UID."""
    row = conn.execute(
        f"SELECT uid, {', '.join(POKEMON_COLUMNS)} FROM pokemon WHERE uid = ?",
        (int(uid),),
    ).fetchone()
    if row is None:
        raise ValueError(f"Pokémon uid {uid} is no longer active")
    cols = "uid, " + ", ".join(POKEMON_COLUMNS)
    placeholders = ", ".join("?" for _ in range(len(POKEMON_COLUMNS) + 1))
    conn.execute(
        f"INSERT INTO inactive_pokemon ({cols}) VALUES ({placeholders})",
        tuple(row[col] for col in ("uid", *POKEMON_COLUMNS)),
    )
    conn.execute("DELETE FROM pokemon WHERE uid = ?", (int(uid),))
