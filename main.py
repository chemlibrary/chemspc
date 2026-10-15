from gen2 import read_gen_2_save, get_gen2_party_list
from db import add_pokemon, init_tables



def import_gen2(path:str):
    save_bytes = read_gen_2_save(path)
    party_pokemon = get_gen2_party_list(save_bytes)
        
    ### DEBUG!!!
    for pokemon in party_pokemon: print(f'{pokemon.name} (#{pokemon.species}) - lvl {pokemon.level}')

    init_tables()
    for pokemon in party_pokemon:
        add_pokemon(pokemon)

    ### TODO: Get the rest of the save data (boxes, items, money, etc...) !!!

    ### TODO: Save imported data to file/db !!!





if __name__ == '__main__':
    
    import_gen2('/home/user/Desktop/pokemon-gold-test.srm')