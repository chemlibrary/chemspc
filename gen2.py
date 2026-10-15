from pokemon import Pokemon



def read_gen_2_save(path:str) -> dict:
    with open(path, "rb") as file:
        length = 32768 # Length in bytes of a gen 2 save file (ensure emulator data is stripped) 
        save_bytes = file.read(length) # EN party list has a length of 428 bytes
        return save_bytes



def get_gen2_party_list(save_bytes):
    """
    Pokemon Party List (Gen 2):
    The total length of the segment is 428 bytes.
    The first byte is the party count.
    The next bytes are each party species index followed my a terminator byte (max 7 bytes).
    Next, each pokemon in the party segement is 48 bytes long.
    Finally, there are 11 bytes for each name, and 11 for each OT name (10 each plus terminators)
    """
    party_list_start_byte = 10378 # Start of party list in save file
    party_list_bytes = save_bytes[party_list_start_byte:(party_list_start_byte+428)] # Length of party list is 428 bytes
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



"""def get_gen2_boxes(save_bytes):
    #
"""
