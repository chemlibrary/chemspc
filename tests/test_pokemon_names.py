"""Generation-aware labels in collection, save import, and database export views."""
from dataclasses import asdict
from types import SimpleNamespace

import pytest
from flask import render_template

from pokemon import Pokemon
from pokemon_names import item_name, move_name, move_names


@pytest.mark.parametrize(('generation', 'item_id', 'expected'), [
    (1, 45, 'No held item (Gen I catch rate: 45)'),
    (2, 146, 'Leftovers'),
    (3, 200, 'Leftovers'),
    (4, 234, 'Leftovers'),
    (5, 234, 'Leftovers'),
    (6, 234, 'Leftovers'),
    (7, 234, 'Leftovers'),
    (2, 13, 'Parlyz Heal'),
    (3, 13, 'Potion'),
    (4, 137, 'Grass Mail'),
    (5, 137, 'Greet Mail'),
])
def test_generation_specific_items(generation, item_id, expected):
    assert item_name(item_id, generation) == expected


@pytest.mark.parametrize(('generation', 'last_id', 'expected'), [
    (1, 165, 'Struggle'), (2, 251, 'Beat Up'), (3, 354, 'Psycho Boost'),
    (4, 467, 'Shadow Force'), (5, 559, 'Fusion Bolt'),
    (6, 621, 'Hyperspace Fury'), (7, 728, 'Clangorous Soulblaze'),
])
def test_moves_through_each_generation_limit(generation, last_id, expected):
    assert move_name(last_id, generation) == expected
    assert move_name(last_id + 1, generation) == f'Unknown move (ID {last_id + 1})'
    assert move_names([33, 0, 85, 33], generation) == ['Tackle', 'Thunderbolt', 'Tackle']


def test_empty_and_unknown_values():
    assert move_names([0, 0, 0, 0], 7) == []
    for generation in range(2, 8):
        assert item_name(0, generation) == 'None'
        for value in (-1, 65535, None):
            assert item_name(value, generation) == f'Unknown item (ID {value})'
            assert move_name(value, generation) == f'Unknown move (ID {value})'
    assert item_name(234, 3) == 'Unknown item (ID 234)'
    assert item_name(234, 0) == 'Unknown item (ID 234)'


@pytest.mark.parametrize('generation', range(1, 8))
def test_all_display_locations_use_names_without_changing_ids(generation, monkeypatch):
    import main

    item_id = {1: 45, 2: 146, 3: 200}.get(generation, 234)
    pokemon = Pokemon(generation=generation, name='Testmon', held_item=item_id,
                      move1=33, move2=0, move3=85, move4=0)
    row = dict(asdict(pokemon), uid=123)
    before = asdict(pokemon)
    monkeypatch.setattr(main.db, 'init_tables', lambda: None)
    monkeypatch.setattr(main.db, 'list_pokemon', lambda active=True: [row] if active else [])
    collection = main.app.test_client().get('/').get_data(as_text=True)
    label = item_name(item_id, generation)
    assert label in collection
    assert 'Tackle, Thunderbolt' in collection

    with main.app.test_request_context('/'):
        review = render_template(
            'manage.html', generation=7, display_name='test.sav', game_label='Sun',
            source_entries=[SimpleNamespace(pokemon=pokemon, locator='party:0', position='Party 1')],
            export_candidates=[dict(pokemon=pokemon, row=row, issues=[])],
        )
    # Both the save card and the database export row must use the Pokémon's own
    # generation, even when reviewing a save from a different generation.
    assert review.count(label) == 2
    assert review.count('Tackle, Thunderbolt') == 2
    assert asdict(pokemon) == before
    assert row['held_item'] == item_id
    assert row['move1'] == 33
