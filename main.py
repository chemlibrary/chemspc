from gen2 import Gen2_Save
from db import add_pokemon, init_tables



def import_gen2(path:str):
    init_tables()

    save = Gen2_Save(path=path)
    save.print_all_pokemon()

    ### TODO: This eventually should selectively add pokemon using a UI !!!
    for pokemon in save.get_all_pokemon():
        add_pokemon(pokemon)

    ### TODO: Get the rest of the save data (boxes, items, money, etc...) !!!

    ### TODO: Remove imported pokemon from the save file !!!





if __name__ == '__main__':
    
    import_gen2('/home/user/Desktop/pokemon-gold-test.srm')