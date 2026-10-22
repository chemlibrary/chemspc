"""Database persistence, schema compatibility, and retained record metadata."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from pokemon import Pokemon


def test_database_exposes_batch_insert_required_by_main(db_module) -> None:
    """The CLI depends on one transaction for an entire save extraction."""
    assert callable(getattr(db_module, "add_pokemon_batch", None)), (
        "main.py imports db.add_pokemon_batch, but db.py does not expose it"
    )


def test_table_initialization_is_idempotent(db_module) -> None:
    assert db_module.init_tables() is True
    assert db_module.init_tables() is True

    active = db_module.list_pokemon(active=True)
    inactive = db_module.list_pokemon(active=False)
    assert active == []
    assert inactive == []


def test_init_tables_adds_record_payload_to_older_tables(db_module) -> None:
    database_path = Path(db_module.DATABASE_NAME)
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "CREATE TABLE pokemon (uid INTEGER PRIMARY KEY, generation INTEGER)"
        )
        connection.execute("CREATE TABLE inactive_pokemon (uid INTEGER, generation INTEGER)")
        connection.execute("INSERT INTO pokemon (uid, generation) VALUES (7, 2)")

    assert db_module.init_tables() is True

    with sqlite3.connect(database_path) as connection:
        active_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(pokemon)")
        }
        inactive_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(inactive_pokemon)")
        }
        row = connection.execute(
            "SELECT uid, generation FROM pokemon WHERE uid = 7"
        ).fetchone()

    assert "record_payload" in active_columns
    assert "record_payload" in inactive_columns
    assert row == (7, 2)


def test_record_payload_round_trips_bytes_tuples_and_nested_values(db_module) -> None:
    pokemon = Pokemon(generation=3, name="Treecko", species=252)
    pokemon.native_record = b"\x00\x01\xff"
    pokemon.substructure_order = ("growth", "attacks", "evs", "misc")
    pokemon.native_metadata = {"slots": [1, 2], "valid": True}

    payload = db_module.encode_record_payload(pokemon)
    restored = db_module.restore_record_payload(Pokemon(), payload)

    assert restored.native_record == pokemon.native_record
    assert restored.substructure_order == pokemon.substructure_order
    assert restored.native_metadata == pokemon.native_metadata


def test_record_payload_rejects_unknown_metadata_objects(db_module) -> None:
    pokemon = Pokemon(name="Bulbasaur")
    pokemon.unsupported_metadata = object()

    with pytest.raises(TypeError, match="Unsupported Pokémon metadata value"):
        db_module.encode_record_payload(pokemon)


def test_restore_record_payload_rejects_damaged_json(db_module) -> None:
    with pytest.raises(ValueError, match="retained save-record metadata is damaged"):
        db_module.restore_record_payload(Pokemon(), "{not-json")


def test_restore_record_payload_rejects_non_object_json(db_module) -> None:
    with pytest.raises(ValueError, match="retained save-record metadata is damaged"):
        db_module.restore_record_payload(Pokemon(), json.dumps(["not", "an", "object"]))


def test_add_list_get_and_restore_pokemon(db_module) -> None:
    db_module.init_tables()
    original = Pokemon(
        generation=2,
        name="Pikachu",
        species=25,
        level=20,
        original_trainer_name="ASH",
    )
    original.native_record = b"retained bytes"

    assert db_module.add_pokemon(original) is True
    rows = db_module.list_pokemon()

    assert len(rows) == 1
    assert rows[0]["name"] == "Pikachu"
    assert rows[0]["species"] == 25
    assert rows[0]["record_payload"]

    selected = db_module.get_active_pokemon([rows[0]["uid"], rows[0]["uid"]])
    assert set(selected) == {rows[0]["uid"]}

    restored = db_module.row_to_pokemon(rows[0])
    assert restored.name == "Pikachu"
    assert restored.native_record == b"retained bytes"


def test_get_active_pokemon_handles_empty_input(db_module) -> None:
    db_module.init_tables()
    assert db_module.get_active_pokemon([]) == {}


def test_move_active_pokemon_to_inactive_preserves_payload(db_module) -> None:
    db_module.init_tables()
    pokemon = Pokemon(generation=3, name="Torchic", species=255)
    pokemon.native_record = b"PK3 raw record"
    db_module.add_pokemon(pokemon)
    uid = db_module.list_pokemon()[0]["uid"]

    connection = db_module.connect()
    try:
        db_module.move_active_to_inactive(connection, uid)
        connection.commit()
    finally:
        connection.close()

    assert db_module.list_pokemon(active=True) == []
    inactive = db_module.list_pokemon(active=False)
    assert len(inactive) == 1
    restored = db_module.row_to_pokemon(inactive[0])
    assert restored.name == "Torchic"
    assert restored.native_record == b"PK3 raw record"


def test_move_unknown_uid_raises_clear_error(db_module) -> None:
    db_module.init_tables()
    connection = db_module.connect()
    try:
        with pytest.raises(ValueError, match="no longer active"):
            db_module.move_active_to_inactive(connection, 99999)
    finally:
        connection.close()


def test_add_pokemon_batch_inserts_the_full_batch(db_module) -> None:
    """A successful import stores every Pokémon in the single supplied batch."""
    db_module.init_tables()
    batch = [
        Pokemon(generation=1, name="Bulbasaur", species=1),
        Pokemon(generation=2, name="Cyndaquil", species=155),
        Pokemon(generation=3, name="Mudkip", species=258),
    ]

    batch_insert = getattr(db_module, "add_pokemon_batch", None)
    if not callable(batch_insert):
        pytest.skip("add_pokemon_batch is missing; see the API contract test above")
    batch_insert(batch)

    assert [row["name"] for row in db_module.list_pokemon()] == [
        "Bulbasaur", "Cyndaquil", "Mudkip"
    ]


def test_add_pokemon_batch_rolls_back_if_one_record_cannot_be_encoded(db_module) -> None:
    """A bad later record must not leave a partially inserted extraction."""
    db_module.init_tables()
    first = Pokemon(generation=1, name="Bulbasaur", species=1)
    second = Pokemon(generation=2, name="Cyndaquil", species=155)
    second.unsupported_metadata = object()

    batch_insert = getattr(db_module, "add_pokemon_batch", None)
    if not callable(batch_insert):
        pytest.skip("add_pokemon_batch is missing; see the API contract test above")

    with pytest.raises(TypeError, match="Unsupported Pokémon metadata value"):
        batch_insert([first, second])

    assert db_module.list_pokemon() == []
