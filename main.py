from pokemon import Pokemon



def import_gen2(path:str):
    save_bytes = read_gen_2_save(path)
    party_pokemon = get_gen2_party_list(save_bytes)
        
    ### DEBUG!!!
    #for pokemon in party_pokemon: print(f'{pokemon}')



def read_gen_2_save(path:str) -> dict:
    with open(path, "rb") as file:
        length = 32768 # Length in bytes of a gen 2 save file (ensure emulator data is stripped) 
        save_bytes = file.read(length) # EN party list has a length of 428 bytes
        return save_bytes



def get_gen2_party_list(save_bytes):
    """
    Pokemon Party List (Gen 2):
    The total length of the segment is 428 bytes.
    The first byte is the party capacity.
    The next bytes are each party species index followed my a terminator byte (max 7 bytes).
    Next, each pokemon in the party segement is 48 bytes long.
    Finally, there are 11 bytes for each name, and 11 for each OT name (10 each plus terminators)
    """
    party_list_start_byte = 10378
    party_list_bytes = save_bytes[party_list_start_byte:(party_list_start_byte+428)] # Length of party list is 428 bytes
    party_pokemon = []
    for i in range(6):
        pokemon = Pokemon()
        ### TODO: Need to check in first 8 bytes for species 0xFD which indicates an egg!
        ### TODO: This doesn't pull the names or OT names yet!
        pokemon.init_gen2(data=party_list_bytes[(8 + (i * 48)):(8 + (i * 48) + 48)])
        party_pokemon.append(pokemon)
    return party_pokemon



"""def get_gen2_boxes(save_bytes):
    #
"""


if __name__ == '__main__':
    
    import_gen2('/home/user/Desktop/pokemon-gold-test.srm')