"""Format-boundary tests for all supported generation save handlers."""
from __future__ import annotations

from pathlib import Path

import pytest

from gen1 import Gen1_Save, _checksum as gen1_checksum, decode_gen1_text
from gen2 import Crystal_Save, Gen2_Save
from gen3 import Gen3_Save, _decode_gen3_record, _serialize_gen3_record
from gen4 import Gen4_Save
from gen5 import Gen5_Save
from gen6 import Gen6_Save
from gen7 import Gen7_Save
from save_formats import GAME_SPECS


@pytest.mark.parametrize(
    ("builder", "label"),
    [
        (lambda label: Gen1_Save(path="does-not-exist.sav", game=label), "nope"),
        (lambda label: Gen3_Save(game=label), "nope"),
        (lambda label: Gen4_Save(game=label), "nope"),
        (lambda label: Gen5_Save(game=label), "nope"),
        (lambda label: Gen6_Save(game=label), "nope"),
        (lambda label: Gen7_Save(game=label), "nope"),
    ],
    ids=["gen1", "gen3", "gen4", "gen5", "gen6", "gen7"],
)
def test_handlers_reject_unsupported_game_labels(builder, label: str) -> None:
    with pytest.raises(ValueError):
        builder(label)


@pytest.mark.parametrize(
    "builder",
    [
        pytest.param(lambda path: Gen1_Save(path=path, game="red"), id="gen1"),
        pytest.param(lambda path: Gen2_Save(path=path), id="gen2-gold-silver"),
        pytest.param(lambda path: Crystal_Save(path=path), id="gen2-crystal"),
        pytest.param(lambda path: Gen3_Save(path=path, game="auto"), id="gen3"),
        pytest.param(lambda path: Gen4_Save(path=path, game="diamond"), id="gen4"),
        pytest.param(lambda path: Gen5_Save(path=path, game="black"), id="gen5"),
        pytest.param(lambda path: Gen6_Save(path=path, game="x"), id="gen6"),
        pytest.param(lambda path: Gen7_Save(path=path, game="sun"), id="gen7"),
    ],
)
def test_handlers_reject_truncated_save_files(
    builder, tmp_path: Path
) -> None:
    save_path = tmp_path / "truncated-save.sav"
    save_path.write_bytes(b"not a valid save")

    with pytest.raises((ValueError, OSError)):
        builder(save_path)


def test_gen1_text_decoder_stops_at_terminator() -> None:
    # 0x80 and 0x81 encode A and B; 0x50 ends the field.
    assert decode_gen1_text(bytes([0x80, 0x81, 0x50, 0x82])) == "AB"


def test_gen1_checksum_is_complemented_byte_sum() -> None:
    assert gen1_checksum(bytes([0x01, 0x02, 0x03])) == ((~6) & 0xFF)
    assert gen1_checksum(b"") == 0xFF


@pytest.mark.parametrize('handler', [Gen2_Save, Crystal_Save], ids=['gold-silver', 'crystal'])
def test_gen2_writer_updates_checksums_and_preserves_source(handler, tmp_path) -> None:
    source = tmp_path / 'source.sav'
    # An empty synthetic save is accepted by the current Gen II readers.
    source.write_bytes(bytes(0x8000))
    save = handler(path=source)
    save.save_bytes[0x2100:0x2104] = b'ABCD'
    output = Path(save.write_save())
    data = output.read_bytes()

    assert output != source
    assert source.read_bytes() == bytes(0x8000)
    assert len(data) == 0x8000
    assert handler(path=output).party_pokemon == []
    if handler is Crystal_Save:
        expected = sum(data[0x2009:0x2B83]) & 0xFFFF
        assert int.from_bytes(data[0x2D0D:0x2D0F], 'little') == expected
        assert int.from_bytes(data[0x1F0D:0x1F0F], 'little') == expected
        assert data[0x2009:0x2B83] == data[0x1209:0x1D83]
    else:
        assert int.from_bytes(data[0x2D69:0x2D6B], 'little') == sum(data[0x2009:0x2D69]) & 0xFFFF
        backup_sum = sum(data[0x0C6B:0x17ED]) + sum(data[0x3D96:0x3F40]) + sum(data[0x7E39:0x7E6D])
        assert int.from_bytes(data[0x7E6D:0x7E6F], 'little') == backup_sum & 0xFFFF


@pytest.mark.parametrize('game', GAME_SPECS)
def test_registry_routes_each_game_to_its_native_handler(game, tmp_path, monkeypatch):
    from importlib import import_module
    from unittest.mock import Mock
    from save_formats import get_game_spec, open_save

    spec = get_game_spec(game)
    constructor = Mock()
    monkeypatch.setattr(import_module(spec.parser_module), spec.parser_class, constructor)
    path = tmp_path / 'save.sav'
    assert open_save(path, game) is constructor.return_value
    if spec.generation == 2:
        constructor.assert_called_once_with(path=path)
    else:
        constructor.assert_called_once_with(path=path, game=game)


def test_gen1_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        Gen1_Save(path=tmp_path / "missing.sav", game="red")


def test_gen1_catch_rate_is_preserved_without_displaying_it_as_an_item():
    from pokemon_names import item_name
    import db

    raw = bytearray(33)
    raw[0] = 0x54  # Pikachu's native Gen I species index.
    raw[3] = 7
    raw[7] = 45  # Catch rate, not an item ID.
    names = b'\x50' * 11
    handler = object.__new__(Gen1_Save)
    pokemon = handler._parse_pokemon(bytes(raw), names, names, party=False)
    restored = db.restore_record_payload(type(pokemon)(), db.encode_record_payload(pokemon))
    assert item_name(restored.held_item, 1) == 'None'
    assert restored.held_item == 45
    assert restored._gen1_box_record == bytes(raw)
    # The serializer retains the same record inside the box container.
    assert handler._serialize_box([restored])[22:55] == bytes(raw)


@pytest.mark.parametrize(('species', 'supported'), [
    (0, False), (251, True), (252, False), (276, False),
    (277, True), (386, True), (387, True), (411, True), (412, False),
])
@pytest.mark.parametrize('game', ['ruby', 'sapphire', 'emerald', 'firered', 'leafgreen'])
def test_gen3_export_validation_uses_native_species_ids(species, supported, game):
    from main import compatibility_issues

    # PID/OT=0 uses ABCD substructure ordering with XOR key 0.
    raw = bytearray(80)
    raw[0x13] = 2
    raw[32:34] = species.to_bytes(2, 'little')
    raw[28:30] = species.to_bytes(2, 'little')  # Pokémon checksum.
    pokemon = _decode_gen3_record(bytes(raw), party_record=False)
    if species == 0:
        # Empty native records are not Pokémon; exercise invalid legacy DB rows.
        from pokemon import Pokemon
        pokemon = Pokemon(generation=3, species=species)
    issues = compatibility_issues(pokemon, game)
    assert (not issues) == supported
    if supported:
        assert _serialize_gen3_record(pokemon, party_record=False) == bytes(raw)
