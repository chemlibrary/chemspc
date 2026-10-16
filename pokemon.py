from chempy.primitives import get_int, get_bytes

class Pokemon:
    def __init__(
            self,
            generation:int = 0,
            name:str = '',
            species:int = 0,
            held_item:int = 0,
            move1:int = 0,
            move2:int = 0,
            move3:int = 0,
            move4:int = 0,
            original_trainer:int = 0,
            original_trainer_name:str = '',
            exp:int = 0,
            hp_ev:int = 0,
            attack_ev:int = 0,
            defense_ev:int = 0,
            speed_ev:int = 0,
            special_ev:int = 0,
            iv:int = 0,
            move1_pp:int = 0, 
            move2_pp:int = 0,
            move3_pp:int = 0,
            move4_pp:int = 0,
            friendship:int = 0,
            pokerus:int = 0,
            caught:int = 0,
            level:int = 0,
            status_condition:int = 0,
            current_hp:int = 0,
            max_hp:int = 0,
            attack:int = 0,
            defense:int = 0,
            speed:int = 0,
            special_attack:int = 0,
            special_defense:int = 0
            ):
        self.generation = generation,
        self.name = name,
        self.species = species,
        self.held_item = held_item,
        self.move1 = move1,
        self.move2 = move2,
        self.move3 = move3,
        self.move4 = move4,
        self.original_trainer = original_trainer,
        self.original_trainer_name = original_trainer_name,
        self.exp = exp,
        self.hp_ev = hp_ev,
        self.attack_ev = attack_ev,
        self.defense_ev = defense_ev,
        self.speed_ev = speed_ev,
        self.special_ev = special_ev,
        self.iv = iv,
        self.move1_pp = move1_pp, 
        self.move2_pp = move2_pp,
        self.move3_pp = move3_pp,
        self.move4_pp = move4_pp,
        self.friendship = friendship,
        self.pokerus = pokerus,
        self.caught = caught,
        self.level = level,
        self.status_condition = status_condition,
        self.current_hp = current_hp,
        self.max_hp = max_hp,
        self.attack = attack,
        self.defense = defense,
        self.speed = speed,
        self.special_attack = special_attack,
        self.special_defense = special_defense



    def init_gen2(self, data, party_pokemon:bool = False):
        ## Gen 2 Pokemon in the party list consist of 48 bytes each
        self.generation = 2
        self.species = get_int(data[0:1])
        self.held_item = get_int(data[1:2])
        self.move1 = get_int(data[2:3])
        self.move2 = get_int(data[3:4])
        self.move3 = get_int(data[4:5])
        self.move4 = get_int(data[5:6])
        self.original_trainer = get_int(data[6:8])
        self.exp = get_int(data[8:11])
        self.hp_ev = get_int(data[11:13])
        self.attack_ev = get_int(data[13:15])
        self.defense_ev = get_int(data[15:17])
        self.speed_ev = get_int(data[17:19])
        self.special_ev = get_int(data[19:21])
        self.iv = get_int(data[21:23])
        self.move1_pp = get_int(data[23:24])
        self.move2_pp = get_int(data[24:25])
        self.move3_pp = get_int(data[25:26])
        self.move4_pp = get_int(data[26:27])
        self.friendship = get_int(data[27:28])
        self.pokerus = get_int(data[28:29])
        self.caught = get_int(data[29:31])
        self.level = get_int(data[31:32])
        self.status_condition = get_int(data[32:33])
        if party_pokemon:
            self.current_hp = get_int(data[34:36])
            self.max_hp = get_int(data[36:38])
            self.attack = get_int(data[38:40])
            self.defense = get_int(data[40:42])
            self.speed = get_int(data[42:44])
            self.special_attack = get_int(data[44:46])
            self.special_defense = get_int(data[46:48])
        else:
            self.current_hp = 0
            self.max_hp = 0
            self.attack = 0
            self.defense = 0
            self.speed = 0
            self.special_attack = 0
            self.special_defense = 0


    def export_gen2(self, party_pokemon:bool = False):
        size = 32
        if party_pokemon:
            size = 48
        raw = bytearray()
        raw.append(get_bytes(self.species, 1))
        raw.append(get_bytes(self.held_item, 1))
        raw.append(get_bytes(self.move1, 1))
        raw.append(get_bytes(self.move2, 1))
        raw.append(get_bytes(self.move3, 1))
        raw.append(get_bytes(self.move4, 1))
        raw.append(get_bytes(self.original_trainer, 2))
        raw.append(get_bytes(self.exp, 2))
        raw.append(get_bytes(self.hp_ev, 2))
        raw.append(get_bytes(self.attack_ev, 2))
        raw.append(get_bytes(self.defense_ev, 2))
        raw.append(get_bytes(self.speed_ev, 2))
        raw.append(get_bytes(self.special_ev, 2))
        raw.append(get_bytes(self.iv, 2))
        raw.append(get_bytes(self.move1_pp, 1))
        raw.append(get_bytes(self.move2_pp, 1))
        raw.append(get_bytes(self.move3_pp, 1))
        raw.append(get_bytes(self.move4_pp, 1))
        raw.append(get_bytes(self.friendship, 1))
        raw.append(get_bytes(self.pokerus, 1))
        raw.append(get_bytes(self.caught, 2))
        raw.append(get_bytes(self.level, 1))
        raw.append(get_bytes(self.status_condition, 1))
        raw.append(get_bytes(0, 1)) # Unused byte
        if party_pokemon:
            raw.append(get_bytes(self.current_hp, 2))
            raw.append(get_bytes(self.max_hp, 2))
            raw.append(get_bytes(self.attack, 2))
            raw.append(get_bytes(self.defense, 2))
            raw.append(get_bytes(self.speed, 2))
            raw.append(get_bytes(self.special_attack, 2))
            raw.append(get_bytes(self.special_defense, 2))
        return bytes(raw)
