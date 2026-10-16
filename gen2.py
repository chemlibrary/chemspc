from pokemon import Pokemon
from chempy.files import bytes_safe_write
from chempy.primitives import get_bytes
import os


class Gen2_Save:
    def __init__(self, path:str = None):
        self.save_size = 32768
        self.party_list_start_offset = 10378 # Offset from start of save file where the party list starts
        self.party_ots_start_offset = (8 + (6 * 48)) # Offset from start of party list where original trainer names start
        self.party_names_start_offset = self.party_ots_start_offset + (11 * 6) # Offset from start of party list where pokemon names start
        self.box_lists_start_offset = 16384 # Offset from start of save file where pokemon box lists start
        self.save_bytes = bytes(self.save_size)
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
                        self.save_bytes = file.read(self.save_size)
                        self.party_pokemon = self.get_gen2_party_pokemon()
                        self.box_pokemon = self.get_gen2_pokemon_boxes()
                except:
                    print('[FAIL] Could not read save file!')
                    exit(1)
            else:
                bytes_safe_write(path=path, contents=self.save_bytes)
        else:
            self.path = './gen2-save.save'


    """def update_checksums(self):
        #..."""




    def print_all_pokemon(self):
        for pokemon in self.party_pokemon: print(f'{pokemon.name} (#{pokemon.species}) - lvl {pokemon.level}')
        for box in self.box_pokemon:
            for pokemon in box:
                print(f'{pokemon.name} (#{pokemon.species}) - lvl {pokemon.level}')


    def export_gen2_party_list(self):
        party_list = bytearray()
        pokemon_list = bytearray()
        species = bytearray()
        names = bytearray()
        ots = bytearray()

        party_list.append(get_bytes(len(self.party_pokemon), 1)) # Append the count byte

        for pokemon in self.party_pokemon: # Append the species indecies to the species block
            species.append(get_bytes(pokemon.species, 1))
            names.append(encode_gen2_text(text=pokemon.name))
            ots.append(encode_gen2_text(text=pokemon.original_trainer_name))
            pokemon_list.append(pokemon.export_gen2(party_pokemon=True))

        party_list.append(0xFF) # Species list is followed by a terminator
        names.append(0xFF) # Names list is followed by a terminator
        ots.append(0xFF) # Original Trainers list is followed by a terminator

        if len(self.party_pokemon) < 6: # Blank the remaining space for species, pokemon list, names, and original trainers if the party is not full
            species.append(bytes(6 - len(self.party_pokemon)))
            names.append(bytes(11 * (6 - len(self.party_pokemon))))
            ots.append(bytes(11 * (6 - len(self.party_pokemon))))
            pokemon_list.append(bytes(48 * (6 - len(self.party_pokemon))))

        # Combine the pieces (the count is already added)
        party_list = party_list + species
        party_list = party_list + pokemon_list
        party_list = party_list + names
        party_list = party_list + ots

        ### DEBUG:
        print(f'party list export length: {len(party_list)}')

        return party_list



    def export_gen2_boxes(self):
        boxes = bytearray()
        for box in self.box_pokemon:
            pokemon_list = bytearray()
            species = bytearray()
            names = bytearray()
            ots = bytearray()

            boxes.append(get_bytes(len(box), 1)) # Append the count byte

            for pokemon in box: # Append the species indecies to the species block
                species.append(get_bytes(pokemon.species, 1))
                pokemon_list.append(pokemon.export_gen2(party_pokemon=False))
                names.append(encode_gen2_text(text=pokemon.name))
                ots.append(encode_gen2_text(text=pokemon.original_trainer_name))

            species.append(0xFF) # Species list is followed by a terminator
            names.append(0xFF) # Names list is followed by a terminator
            ots.append(0xFF) # Original Trainers list is followed by a terminator

            if len(box) < 20: # Blank the remaining space for species, pokemon list, names, and original trainers if the box is not full
                species.append(bytes(20 - len(box)))
                names.append(bytes(11 * (20 - len(box))))
                ots.append(bytes(11 * (20 - len(box))))
                pokemon_list.append(bytes(32 * (20 - len(box))))

            # Combine the pieces (the count is already added)
            boxes = boxes + species
            boxes = boxes + pokemon_list
            boxes = boxes + names
            boxes = boxes + ots

        ### DEBUG:
        print(f'boxes export length: {len(boxes)}')

        return boxes

    

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
        
        party_list_bytes = self.save_bytes[self.party_list_start_offset:(self.party_list_start_offset+428)] # Length of party list is 428 bytes
        party_count = int.from_bytes(party_list_bytes[0:1], byteorder='big') # Get the number of pokemon in the current party
        
        ### TODO: Need to check in bytes 1 - 6 for species 0xFD which indicates an egg!
        party_pokemon = []
        for i in range(party_count):
            pokemon = Pokemon()
            pokemon.init_gen2(data=party_list_bytes[(8 + (i * 48)):(8 + (i * 48) + 48)], party_pokemon=True)
            pokemon.original_trainer_name = decode_gen2_text(party_list_bytes[(self.party_ots_start_offset + (i * 11)):(self.party_ots_start_offset + (i * 11) + 11)])
            pokemon.name = decode_gen2_text(party_list_bytes[(self.party_names_start_offset + (i * 11)):(self.party_names_start_offset + (i * 11) + 11)])
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
        
        list_len = 1104
        box_lists_bytes = self.save_bytes[self.box_lists_start_offset:(self.box_lists_start_offset+22080)] # Length of boxes is 22080 bytes
        box_pokemon = []
        for i in range(20):
            box_contents = []
            box = box_lists_bytes[(i * self.box_lists_start_offset):((i * self.box_lists_start_offset) + list_len)]
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
                        box_contents.append(pokemon)
                except:
                    continue
            box_pokemon.append(box_contents)
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
