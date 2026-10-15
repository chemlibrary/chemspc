from pokemon import Pokemon
from chempy.files import bytes_safe_write
import os


class Gen2_Save:
    def __init__(self, path:str = None):
        self.save_bytes = b''
        self.party_pokemon = []
        self.box_pokemon = []
        
        ### TODO: Implement these:
        #self.money = 0
        #self.pokedex = []
        #self.items = []

        if path != None:
            self.path = path
            if os.path.isfile(self.path):
                try:
                    with open(self.path, "rb") as file:
                        length = 32768 # Length in bytes of a gen 2 save file (ensure emulator data is stripped) 
                        self.save_bytes = file.read(length) # EN party list has a length of 428 bytes
                        self.party_pokemon = self.get_gen2_party_pokemon()
                        self.box_pokemon = self.get_gen2_pokemon_boxes()
                except:
                    print('[FAIL] Could not read save file!')
                    exit(1)
            else:
                bytes_safe_write(path=path, contents=self.save_bytes)
        else:
            self.path = './gen2-save.save'


    #def update_checksums(self):
        #...


    def get_all_pokemon(self):
        return self.party_pokemon + self.box_pokemon



    def print_all_pokemon(self):
        for pokemon in self.party_pokemon: print(f'{pokemon.name} (#{pokemon.species}) - lvl {pokemon.level}')
        for pokemon in self.box_pokemon: print(f'{pokemon.name} (#{pokemon.species}) - lvl {pokemon.level}')

    

    def read_gen2_save(self, path:str) -> dict:
        with open(path, "rb") as file:
            length = 32768 # Length in bytes of a gen 2 save file (ensure emulator data is stripped) 
            save_bytes = file.read(length) # EN party list has a length of 428 bytes
            return save_bytes



    def get_gen2_party_pokemon(self):
        """
        Pokemon Party List (Gen 2):
        The total length of the segment is 428 bytes.
        The first byte is the party count.
        The next bytes are each party species index followed my a terminator byte (max 7 bytes).
        Next, each pokemon in the party segement is 48 bytes long.
        Finally, there are 11 bytes for each name, and 11 for each OT name (10 each plus terminators)
        """
        party_list_start_byte = 10378 # Start of party list in save file
        party_list_bytes = self.save_bytes[party_list_start_byte:(party_list_start_byte+428)] # Length of party list is 428 bytes
        party_count = int.from_bytes(party_list_bytes[0:1], byteorder='big') # Get the number of pokemon in the current party
        party_ots_start_byte = (8 + (6 * 48)) # Starts after the initial 8 bytes and 6 x 48 byte pokemon blocks
        party_names_start_byte = party_ots_start_byte + (11 * 6) # Starts after the original trainer names block
        ### TODO: Need to check in bytes 1 - 6 for species 0xFD which indicates an egg!
        party_pokemon = []
        for i in range(party_count):
            pokemon = Pokemon()
            pokemon.init_gen2(data=party_list_bytes[(8 + (i * 48)):(8 + (i * 48) + 48)], party_pokemon=True)
            pokemon.original_trainer_name = decode_gen2_text(party_list_bytes[(party_ots_start_byte + (i * 11)):(party_ots_start_byte + (i * 11) + 11)])
            pokemon.name = decode_gen2_text(party_list_bytes[(party_names_start_byte + (i * 11)):(party_names_start_byte + (i * 11) + 11)])
            party_pokemon.append(pokemon)
        return party_pokemon



    def get_gen2_pokemon_boxes(self):
        """
        Pokemon Storage Boxes (Gen 2):
        Stored as Pokémon lists with a capacity of 20 Pokémon in English save files, and an entry size of 32 bytes.
        The total length of the segment is 22080 bytes (20 boxes).

        capacity length = 1 byte
        species list = 21 bytes
        pokemon data length = 640 bytes
        names and OT names length = 440 bytes
        end bytes = 2
        
        """
        box_lists_start_byte = 16384
        list_len = 1104
        box_lists_bytes = self.save_bytes[box_lists_start_byte:(box_lists_start_byte+22080)] # Length of boxes is 22080 bytes
        box_pokemon = []
        for i in range(20):
            box = box_lists_bytes[(i * box_lists_start_byte):((i * box_lists_start_byte) + list_len)]
            box_contents_count = int.from_bytes(box[0:1], byteorder='big')
            box_ots_start_byte = (22 + (20 * 32)) # Starts after the initial 22 bytes and 20 x 32 byte pokemon blocks
            box_names_start_byte = box_ots_start_byte + (11 * 20) # Starts after the original trainer names block
            for x in range(box_contents_count):
                pokemon = Pokemon()
                try:
                    pokemon.init_gen2(data=box[(22 + (x * 32)):(22 + (x * 32) + 32)], party_pokemon=False)
                    if pokemon.species != 0:
                        pokemon.original_trainer_name = decode_gen2_text(box[(box_ots_start_byte + (x * 11)):(box_ots_start_byte + (x * 11) + 11)])
                        pokemon.name = decode_gen2_text(box[(box_names_start_byte + (x * 11)):(box_names_start_byte + (x * 11) + 11)])
                        box_pokemon.append(pokemon)
                except:
                    continue
        return box_pokemon



def decode_gen2_text(data: bytes, *, stop_at_terminator: bool = True) -> str:
    """Pokemon uses a custom encoding for text strings.
    This function will decode characters in English Pokémon Gen II text."""
    chars = {}
    chars.update({0x80 + i: chr(ord("A") + i) for i in range(26)}) # A–Z: 0x80–0x99
    chars.update({0xA0 + i: chr(ord("a") + i) for i in range(26)}) # a–z: 0xA0–0xB9
    chars.update({0xF6 + i: str(i) for i in range(10)}) # Digits: 0xF6–0xFF
    chars.update({
        0x7F: " ",
        0xE3: "-",
        0x9A: "(",
        0x9B: ")",
        0x9C: ":",
        0x9D: ";",
        0x9E: "[",
        0x9F: "]",
        0xE0: "'",
        0xE6: "?",
        0xE7: "!",
        0xE8: ".",
        0xE9: "&",
        0xEA: "é",
        0xF1: "×",
        0xF2: ".",
        0xF3: "/",
        0xF4: ",",
        0xF5: "♀",
        0xEF: "♂",
    })
    result = []
    for byte in data:
        if byte == 0x50: # End of string
            if stop_at_terminator:
                break
            continue
        if byte == 0x4F: # Line break
            result.append("\n")
        else:
            result.append(chars.get(byte, f"[{byte:02X}]"))
    return "".join(result)



def encode_gen2_text(text: str, *, add_terminator: bool = True) -> bytes:
    """Encode text using the same common English Gen II mappings as the decoder."""
    chars = {
        " ": 0x7F,
        "-": 0xE3,
        "(": 0x9A,
        ")": 0x9B,
        ":": 0x9C,
        ";": 0x9D,
        "[": 0x9E,
        "]": 0x9F,
        "'": 0xE0,
        "?": 0xE6,
        "!": 0xE7,
        ".": 0xE8,
        "&": 0xE9,
        "é": 0xEA,
        "♂": 0xEF,
        "×": 0xF1,
        "/": 0xF3,
        ",": 0xF4,
        "♀": 0xF5,
        "\n": 0x4F,
    }
    chars.update({chr(ord("A") + i): 0x80 + i for i in range(26)})
    chars.update({chr(ord("a") + i): 0xA0 + i for i in range(26)})
    chars.update({str(i): 0xF6 + i for i in range(10)})
    encoded = bytearray()
    for char in text:
        if char not in chars:
            raise ValueError(f"Character not supported: {char!r}")
        encoded.append(chars[char])
    if add_terminator:
        encoded.append(0x50)
    return bytes(encoded)

