"""SQLite persistence for Pokémon records."""

import sqlite3
from typing import Iterable

from pokemon import Pokemon

DATABASE_NAME = "chemspc.db"

CREATE_POKEMON_TABLE = """CREATE TABLE IF NOT EXISTS pokemon (
    uid INTEGER PRIMARY KEY AUTOINCREMENT,
    generation INTEGER, source_game TEXT, gen1_internal_species INTEGER, personality INTEGER, ability INTEGER,
    language INTEGER, gender INTEGER, nature INTEGER, is_egg INTEGER, is_shiny INTEGER,
    game_of_origin INTEGER, met_location INTEGER, egg_location INTEGER, met_level INTEGER,
    pokeball INTEGER, encounter_type INTEGER, egg_date INTEGER, met_date INTEGER,
    original_trainer_gender INTEGER,
    name TEXT, species INTEGER, held_item INTEGER,
    move1 INTEGER, move2 INTEGER, move3 INTEGER, move4 INTEGER,
    original_trainer INTEGER, original_trainer_name TEXT, exp INTEGER,
    hp_ev INTEGER, attack_ev INTEGER, defense_ev INTEGER, speed_ev INTEGER,
    special_ev INTEGER, special_attack_ev INTEGER, special_defense_ev INTEGER,
    iv INTEGER, move1_pp INTEGER, move2_pp INTEGER,
    move3_pp INTEGER, move4_pp INTEGER, friendship INTEGER, pokerus INTEGER,
    caught INTEGER, level INTEGER, status_condition INTEGER, current_hp INTEGER,
    max_hp INTEGER, attack INTEGER, defense INTEGER, speed INTEGER,
    special_attack INTEGER, special_defense INTEGER
)"""

CREATE_INACTIVE_TABLE = """CREATE TABLE IF NOT EXISTS inactive_pokemon (
    uid INTEGER, generation INTEGER, source_game TEXT, gen1_internal_species INTEGER, personality INTEGER, ability INTEGER,
    language INTEGER, gender INTEGER, nature INTEGER, is_egg INTEGER, is_shiny INTEGER,
    game_of_origin INTEGER, met_location INTEGER, egg_location INTEGER, met_level INTEGER,
    pokeball INTEGER, encounter_type INTEGER, egg_date INTEGER, met_date INTEGER,
    original_trainer_gender INTEGER,
    name TEXT, species INTEGER, held_item INTEGER,
    move1 INTEGER, move2 INTEGER, move3 INTEGER, move4 INTEGER,
    original_trainer INTEGER, original_trainer_name TEXT, exp INTEGER,
    hp_ev INTEGER, attack_ev INTEGER, defense_ev INTEGER, speed_ev INTEGER,
    special_ev INTEGER, special_attack_ev INTEGER, special_defense_ev INTEGER,
    iv INTEGER, move1_pp INTEGER, move2_pp INTEGER,
    move3_pp INTEGER, move4_pp INTEGER, friendship INTEGER, pokerus INTEGER,
    caught INTEGER, level INTEGER, status_condition INTEGER, current_hp INTEGER,
    max_hp INTEGER, attack INTEGER, defense INTEGER, speed INTEGER,
    special_attack INTEGER, special_defense INTEGER
)"""

INSERT_POKEMON_SQL = """INSERT INTO pokemon (
    generation, source_game, gen1_internal_species, personality, ability, language, gender, nature, is_egg, is_shiny,
    game_of_origin, met_location, egg_location, met_level, pokeball, encounter_type, egg_date, met_date, original_trainer_gender,
    name, species, held_item, move1, move2, move3, move4,
    original_trainer, original_trainer_name, exp, hp_ev, attack_ev,
    defense_ev, speed_ev, special_ev, special_attack_ev, special_defense_ev,
    iv, move1_pp, move2_pp, move3_pp, move4_pp, friendship, pokerus, caught,
    level, status_condition, current_hp, max_hp, attack, defense, speed,
    special_attack, special_defense
) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"""


def _pokemon_values(pokemon: Pokemon) -> tuple:
    return (
        pokemon.generation, getattr(pokemon, "game_name", None),
        getattr(pokemon, "gen1_internal_species", None),
        getattr(pokemon, "personality", None), getattr(pokemon, "ability", None),
        getattr(pokemon, "language", None), getattr(pokemon, "gender", None),
        getattr(pokemon, "nature", None), getattr(pokemon, "is_egg", None),
        getattr(pokemon, "is_shiny", None),
        getattr(pokemon, "game_of_origin", None), getattr(pokemon, "met_location", None),
        getattr(pokemon, "egg_location", None), getattr(pokemon, "met_level", None),
        getattr(pokemon, "pokeball", None), getattr(pokemon, "encounter_type", None),
        getattr(pokemon, "egg_date", None), getattr(pokemon, "met_date", None),
        getattr(pokemon, "original_trainer_gender", None),
        pokemon.name, pokemon.species, pokemon.held_item,
        pokemon.move1, pokemon.move2, pokemon.move3, pokemon.move4,
        pokemon.original_trainer, pokemon.original_trainer_name, pokemon.exp,
        pokemon.hp_ev, pokemon.attack_ev, pokemon.defense_ev, pokemon.speed_ev,
        pokemon.special_ev, getattr(pokemon, "special_attack_ev", None),
        getattr(pokemon, "special_defense_ev", None), pokemon.iv,
        pokemon.move1_pp, pokemon.move2_pp, pokemon.move3_pp, pokemon.move4_pp,
        pokemon.friendship, pokemon.pokerus, pokemon.caught, pokemon.level,
        pokemon.status_condition, pokemon.current_hp, pokemon.max_hp,
        pokemon.attack, pokemon.defense, pokemon.speed, pokemon.special_attack,
        pokemon.special_defense,
    )


def _run_transaction(callback) -> None:
    conn = sqlite3.connect(DATABASE_NAME)
    try:
        with conn:
            callback(conn)
    finally:
        conn.close()


_MIGRATED_COLUMNS = {
    "pokemon": {
        "source_game": "TEXT",
        "gen1_internal_species": "INTEGER",
        "personality": "INTEGER",
        "ability": "INTEGER",
        "language": "INTEGER",
        "gender": "INTEGER",
        "nature": "INTEGER",
        "is_egg": "INTEGER",
        "is_shiny": "INTEGER",
        "game_of_origin": "INTEGER",
        "met_location": "INTEGER",
        "egg_location": "INTEGER",
        "met_level": "INTEGER",
        "pokeball": "INTEGER",
        "encounter_type": "INTEGER",
        "egg_date": "INTEGER",
        "met_date": "INTEGER",
        "original_trainer_gender": "INTEGER",
        "special_attack_ev": "INTEGER",
        "special_defense_ev": "INTEGER",
    },
    "inactive_pokemon": {
        "source_game": "TEXT",
        "gen1_internal_species": "INTEGER",
        "personality": "INTEGER",
        "ability": "INTEGER",
        "language": "INTEGER",
        "gender": "INTEGER",
        "nature": "INTEGER",
        "is_egg": "INTEGER",
        "is_shiny": "INTEGER",
        "game_of_origin": "INTEGER",
        "met_location": "INTEGER",
        "egg_location": "INTEGER",
        "met_level": "INTEGER",
        "pokeball": "INTEGER",
        "encounter_type": "INTEGER",
        "egg_date": "INTEGER",
        "met_date": "INTEGER",
        "original_trainer_gender": "INTEGER",
        "special_attack_ev": "INTEGER",
        "special_defense_ev": "INTEGER",
    },
}


def _ensure_schema_columns(conn: sqlite3.Connection) -> None:
    """Add nullable metadata columns required by the supported generations."""
    for table_name, columns in _MIGRATED_COLUMNS.items():
        existing = {
            row[1] for row in conn.execute(f"PRAGMA table_info({table_name})")
        }
        for column_name, column_type in columns.items():
            if column_name not in existing:
                conn.execute(
                    f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"
                )


def init_tables() -> bool:
    def create(conn):
        conn.execute(CREATE_POKEMON_TABLE)
        conn.execute(CREATE_INACTIVE_TABLE)
        _ensure_schema_columns(conn)

    _run_transaction(create)
    return True


def add_pokemon(pokemon: Pokemon) -> bool:
    """Insert one Pokémon and commit it before returning."""
    values = _pokemon_values(pokemon)
    _run_transaction(lambda conn: conn.execute(INSERT_POKEMON_SQL, values))
    return True


def add_pokemon_batch(pokemon: Iterable[Pokemon]) -> bool:
    """Insert a whole extraction in one transaction, or insert none of it."""
    values = [_pokemon_values(item) for item in pokemon]
    _run_transaction(lambda conn: conn.executemany(INSERT_POKEMON_SQL, values))
    return True
