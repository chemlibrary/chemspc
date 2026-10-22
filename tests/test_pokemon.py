"""Tests for the shared Pokémon model and Generation II record conversion."""
from __future__ import annotations

import pytest

from gen2 import decode_gen2_text, encode_gen2_name, encode_gen2_text
from pokemon import Pokemon


@pytest.fixture
def sample_gen2_pokemon() -> Pokemon:
    return Pokemon(
        generation=2,
        name="PIKA",
        species=25,
        held_item=2,
        move1=33,
        move2=45,
        move3=84,
        move4=98,
        original_trainer=0x1234,
        original_trainer_name="ASH",
        exp=0x010203,
        hp_ev=100,
        attack_ev=200,
        defense_ev=300,
        speed_ev=400,
        special_ev=500,
        iv=0xABCD,
        move1_pp=35,
        move2_pp=20,
        move3_pp=15,
        move4_pp=10,
        friendship=70,
        pokerus=0,
        caught=0x1234,
        level=37,
        status_condition=1,
        current_hp=42,
        max_hp=55,
        attack=30,
        defense=25,
        speed=40,
        special_attack=35,
        special_defense=36,
    )


@pytest.mark.parametrize(
    ("party_pokemon", "expected_length"),
    [(False, 32), (True, 48)],
    ids=["boxed-record", "party-record"],
)
def test_gen2_record_round_trip(
    sample_gen2_pokemon: Pokemon,
    party_pokemon: bool,
    expected_length: int,
) -> None:
    raw = sample_gen2_pokemon.export_gen2_bytes(party_pokemon=party_pokemon)

    assert len(raw) == expected_length
    restored = Pokemon()
    restored.init_gen2(raw, party_pokemon=party_pokemon)

    assert restored.generation == 2
    assert restored.species == sample_gen2_pokemon.species
    assert restored.held_item == sample_gen2_pokemon.held_item
    assert restored.move1 == sample_gen2_pokemon.move1
    assert restored.move2 == sample_gen2_pokemon.move2
    assert restored.move3 == sample_gen2_pokemon.move3
    assert restored.move4 == sample_gen2_pokemon.move4
    assert restored.original_trainer == sample_gen2_pokemon.original_trainer
    assert restored.exp == sample_gen2_pokemon.exp
    assert restored.level == sample_gen2_pokemon.level
    assert restored.export_gen2_bytes(party_pokemon=party_pokemon) == raw

    if party_pokemon:
        assert restored.current_hp == sample_gen2_pokemon.current_hp
        assert restored.max_hp == sample_gen2_pokemon.max_hp
        assert restored.status_condition == sample_gen2_pokemon.status_condition
    else:
        # Box records do not contain party-only battle stats.
        assert restored.current_hp == 0
        assert restored.max_hp == 0
        assert restored.status_condition == 0


@pytest.mark.parametrize(
    ("party_pokemon", "bad_length"),
    [(False, 31), (False, 33), (True, 47), (True, 49)],
)
def test_gen2_parser_rejects_wrong_record_size(
    party_pokemon: bool, bad_length: int
) -> None:
    with pytest.raises(ValueError, match="Generation II Pokémon data"):
        Pokemon().init_gen2(bytes(bad_length), party_pokemon=party_pokemon)


def test_gen2_text_encoding_round_trips_supported_characters() -> None:
    original = "Pika 123!"
    encoded = encode_gen2_text(original)

    assert encoded[-1] == 0x50
    assert decode_gen2_text(encoded) == original


def test_gen2_text_encoder_can_omit_terminator() -> None:
    encoded = encode_gen2_text("ABC", add_terminator=False)

    assert len(encoded) == 3
    assert decode_gen2_text(encoded, stop_at_terminator=False) == "ABC"


def test_gen2_text_rejects_unsupported_characters() -> None:
    with pytest.raises(ValueError, match="not supported"):
        encode_gen2_text("Pika🙂")


def test_gen2_fixed_width_name_is_padded_and_decodable() -> None:
    field = encode_gen2_name("ASH", width=11, max_chars=7)

    assert len(field) == 11
    assert decode_gen2_text(field) == "ASH"


@pytest.mark.parametrize(
    ("text", "width", "max_chars"),
    [("TOO-LONG", 11, 7), ("ASH", 2, 7)],
    ids=["over-character-limit", "over-byte-width"],
)
def test_gen2_fixed_width_name_rejects_overflow(
    text: str, width: int, max_chars: int
) -> None:
    with pytest.raises(ValueError):
        encode_gen2_name(text, width=width, max_chars=max_chars)
