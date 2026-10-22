"""Format-boundary tests for all supported generation save handlers."""
from __future__ import annotations

from pathlib import Path

import pytest

from gen1 import Gen1_Save, _checksum as gen1_checksum, decode_gen1_text
from gen2 import Crystal_Save, Gen2_Save, is_valid_crystal_save, is_valid_gold_silver_save
from gen3 import Gen3_Save
from gen4 import Gen4_Save
from gen5 import Gen5_Save
from gen6 import Gen6_Save
from gen7 import Gen7_Save


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


def test_gen2_checksum_predicates_reject_uninitialized_bytes() -> None:
    blank_save = bytes(0x8000)

    assert is_valid_gold_silver_save(blank_save) is False
    assert is_valid_crystal_save(blank_save) is False


def test_gen1_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        Gen1_Save(path=tmp_path / "missing.sav", game="red")
