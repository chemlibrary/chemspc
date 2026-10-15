from gen2 import Gen2_Save
from db import add_pokemon, init_tables


### TODO: Create table of all pokemon with sprites for UI
### TODO: Create flask UI
### TODO: Create pokedex table
### TODO: Create items table (use UID 0 for money) [qty, gen1_item#, gen2_item#, etc...]


def import_gen2(path:str):
    init_tables()

    save = Gen2_Save(path=path)
    save.print_all_pokemon()

    ### TODO: This eventually should selectively add pokemon using a UI !!!
    for pokemon in save.get_all_pokemon():
        add_pokemon(pokemon)

    ### TODO: Get the rest of the save data (items, money, etc...) !!!

    ### TODO: Remove imported pokemon from the save file !!!


if __name__ == '__main__':
    
    import_gen2('/home/user/Desktop/pokemon-gold-test.srm')