class Pokemon:
    def __init__(
            self,
            generation:int=0,
            name:str='',
            species:int=0,
            held_item:int=0,
            move1:int=0,
            move2:int=0,
            move3:int=0,
            move4:int=0,
            original_trainer:int=0,
            original_trainer_name:str='',
            exp:int=0,
            hp_ev:int=0,
            attack_ev:int=0,
            defense_ev:int=0,
            speed_ev:int=0,
            special_ev:int=0,
            iv:int=0,
            move1_pp:int=0, 
            move2_pp:int=0,
            move3_pp:int=0,
            move4_pp:int=0,
            friendship:int=0,
            pokerus:int=0,
            caught:int=0,
            level:int=0,
            status_condition:int=0,
            current_hp:int=0,
            max_hp:int=0,
            attack:int=0,
            defense:int=0,
            speed:int=0,
            special_attack:int=0,
            special_defense:int=0
            ):
        self.generation=generation,
        self.name=name,
        self.species=species,
        self.held_item=held_item,
        self.move1=move1,
        self.move2=move2,
        self.move3=move3,
        self.move4=move4,
        self.original_trainer=original_trainer,
        self.original_trainer_name=original_trainer_name,
        self.exp=exp,
        self.hp_ev=hp_ev,
        self.attack_ev=attack_ev,
        self.defense_ev=defense_ev,
        self.speed_ev=speed_ev,
        self.special_ev=special_ev,
        self.iv=iv,
        self.move1_pp=move1_pp, 
        self.move2_pp=move2_pp,
        self.move3_pp=move3_pp,
        self.move4_pp=move4_pp,
        self.friendship=friendship,
        self.pokerus=pokerus,
        self.caught=caught,
        self.level=level,
        self.status_condition=status_condition,
        self.current_hp=current_hp,
        self.max_hp=max_hp,
        self.attack=attack,
        self.defense=defense,
        self.speed=speed,
        self.special_attack=special_attack,
        self.special_defense=special_defense



    def init_gen2(self, data, party_pokemon:bool=False):
        ## Gen 2 Pokemon in the party list consist of 48 bytes each
        self.generation=2
        self.species=int.from_bytes(data[0:1], byteorder='big')
        self.held_item=int.from_bytes(data[1:2], byteorder='big')
        self.move1=int.from_bytes(data[2:3], byteorder='big')
        self.move2=int.from_bytes(data[3:4], byteorder='big')
        self.move3=int.from_bytes(data[4:5], byteorder='big')
        self.move4=int.from_bytes(data[5:6], byteorder='big')
        self.original_trainer=int.from_bytes(data[6:8], byteorder='big')
        self.exp=int.from_bytes(data[8:11], byteorder='big')
        self.hp_ev=int.from_bytes(data[11:13], byteorder='big')
        self.attack_ev=int.from_bytes(data[13:15], byteorder='big')
        self.defense_ev=int.from_bytes(data[15:17], byteorder='big')
        self.speed_ev=int.from_bytes(data[17:19], byteorder='big')
        self.special_ev=int.from_bytes(data[19:21], byteorder='big')
        self.iv=int.from_bytes(data[21:23], byteorder='big')
        self.move1_pp=int.from_bytes(data[23:24], byteorder='big')
        self.move2_pp=int.from_bytes(data[24:25], byteorder='big')
        self.move3_pp=int.from_bytes(data[25:26], byteorder='big')
        self.move4_pp=int.from_bytes(data[26:27], byteorder='big')
        self.friendship=int.from_bytes(data[27:28], byteorder='big')
        self.pokerus=int.from_bytes(data[28:29], byteorder='big')
        self.caught=int.from_bytes(data[29:31], byteorder='big')
        self.level=int.from_bytes(data[31:32], byteorder='big')
        self.status_condition=int.from_bytes(data[32:33], byteorder='big')
        if party_pokemon:
            self.current_hp=int.from_bytes(data[34:36], byteorder='big')
            self.max_hp=int.from_bytes(data[36:38], byteorder='big')
            self.attack=int.from_bytes(data[38:40], byteorder='big')
            self.defense=int.from_bytes(data[40:42], byteorder='big')
            self.speed=int.from_bytes(data[42:44], byteorder='big')
            self.special_attack=int.from_bytes(data[44:46], byteorder='big')
            self.special_defense=int.from_bytes(data[46:48], byteorder='big')
        else:
            self.current_hp=0
            self.max_hp=0
            self.attack=0
            self.defense=0
            self.speed=0
            self.special_attack=0
            self.special_defense=0


