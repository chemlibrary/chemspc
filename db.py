import sqlite3
from pokemon import Pokemon



DATABASE_NAME = 'chemspc.db'



def init_tables():
    conn = sqlite3.connect(DATABASE_NAME)
    cur = conn.cursor()

    ## Create primary pokemon table
    cur.execute("CREATE TABLE IF NOT EXISTS pokemon (uid INTEGER PRIMARY KEY AUTOINCREMENT, generation INTEGER, name TEXT, species INTEGER, held_item INTEGER, move1 INTEGER, move2 INTEGER, move3 INTEGER, move4 INTEGER, original_trainer INTEGER, original_trainer_name TEXT, exp INTEGER, hp_ev INTEGER, attack_ev INTEGER, defense_ev INTEGER, speed_ev INTEGER, special_ev INTEGER, iv INTEGER, move1_pp INTEGER, move2_pp INTEGER, move3_pp INTEGER, move4_pp INTEGER, friendship INTEGER, pokerus INTEGER, caught INTEGER, level INTEGER, status_condition INTEGER, current_hp INTEGER, max_hp INTEGER, attack INTEGER, defense INTEGER, speed INTEGER, special_attack INTEGER, special_defense INTEGER)")

    ## Create recovery table for pokemon in games (no auto-incrementing uid, so it will share uids with the primary table)
    cur.execute("CREATE TABLE IF NOT EXISTS inactive_pokemon (uid INTEGER, generation INTEGER, name TEXT, species INTEGER, held_item INTEGER, move1 INTEGER, move2 INTEGER, move3 INTEGER, move4 INTEGER, original_trainer INTEGER, original_trainer_name TEXT, exp INTEGER, hp_ev INTEGER, attack_ev INTEGER, defense_ev INTEGER, speed_ev INTEGER, special_ev INTEGER, iv INTEGER, move1_pp INTEGER, move2_pp INTEGER, move3_pp INTEGER, move4_pp INTEGER, friendship INTEGER, pokerus INTEGER, caught INTEGER, level INTEGER, status_condition INTEGER, current_hp INTEGER, max_hp INTEGER, attack INTEGER, defense INTEGER, speed INTEGER, special_attack INTEGER, special_defense INTEGER)")
    
    conn.close()
    return True



def add_pokemon(pokemon:Pokemon) -> bool:
    conn = sqlite3.connect(DATABASE_NAME)
    cur = conn.cursor()

    ## Insert data ito pokemon table
    cur.execute("INSERT INTO pokemon (generation, name, species, held_item, move1, move2, move3, move4, original_trainer, original_trainer_name, exp, hp_ev, attack_ev, defense_ev, speed_ev, special_ev, iv, move1_pp, move2_pp, move3_pp, move4_pp, friendship, pokerus, caught, level, status_condition, current_hp, max_hp, attack, defense, speed, special_attack, special_defense) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (pokemon.generation, pokemon.name, pokemon.species, pokemon.held_item, pokemon.move1, pokemon.move2, pokemon.move3, pokemon.move4, pokemon.original_trainer, pokemon.original_trainer_name, pokemon.exp, pokemon.hp_ev, pokemon.attack_ev, pokemon.defense_ev, pokemon.speed_ev, pokemon.special_ev, pokemon.iv, pokemon.move1_pp, pokemon.move2_pp, pokemon.move3_pp, pokemon.move4_pp, pokemon.friendship, pokemon.pokerus, pokemon.caught, pokemon.level, pokemon.status_condition, pokemon.current_hp, pokemon.max_hp, pokemon.attack, pokemon.defense, pokemon.speed, pokemon.special_attack, pokemon.special_defense))

    conn.close()
    return True

# Query data
#cur.execute("SELECT * FROM users")
#rows = cur.fetchall()