"""CLI routing and extraction workflow tests for main.py."""
from __future__ import annotations

import importlib
import sys
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import Mock

import pytest


@pytest.fixture
def main_module(monkeypatch: pytest.MonkeyPatch):
    """Import main even on snapshots missing its required batch DB helper.

    There is a separate database contract test that reports the missing helper.
    This compatibility shim lets the rest of the CLI/workflow tests run so one
    missing symbol does not mask unrelated behavior.
    """
    import db

    if not callable(getattr(db, "add_pokemon_batch", None)):
        monkeypatch.setattr(db, "add_pokemon_batch", lambda _records: None, raising=False)

    sys.modules.pop("main", None)
    module = importlib.import_module("main")
    yield module
    sys.modules.pop("main", None)


IMPORT_CASES = [
    pytest.param("import_gen1", "Gen1_Save", "yellow", 12, "yellow", id="gen1-yellow"),
    pytest.param("import_gen2", "Gen2_Save", "crystal", 14, "crystal", id="gen2-crystal"),
    pytest.param("import_gen3", "Gen3_Save", "emerald", 14, "emerald", id="gen3-emerald"),
    pytest.param("import_gen4", "Gen4_Save", "diamond", 18, "diamond", id="gen4-diamond"),
    pytest.param("import_gen5", "Gen5_Save", "black2", 24, "black2", id="gen5-black2"),
    pytest.param("import_gen6", "Gen6_Save", "x", 31, "x", id="gen6-x"),
    pytest.param("import_gen7", "Gen7_Save", "sun", 32, "sun", id="gen7-sun"),
]


@pytest.fixture
def fake_save_factory():
    """Build controllable save classes and retain the instances for assertions."""
    instances = []

    def factory(expected_box_count: int, default_game: str):
        class FakeSave:
            def __init__(self, path, game=None):
                self.path = str(path)
                self.game_name = game or default_game
                self.party_pokemon = [SimpleNamespace(name="PartyMon", species=1)]
                self.box_pokemon = [[SimpleNamespace(name="BoxMon", species=2)]]
                self.expected_box_count = expected_box_count
                self.write_count = 0
                self.print_count = 0
                instances.append(self)

            def print_all_pokemon(self):
                self.print_count += 1

            def write_save(self):
                self.write_count += 1
                # The orchestration must clear in-memory Pokémon only after the
                # database batch succeeds and before writing the new save copy.
                assert self.party_pokemon == []
                assert len(self.box_pokemon) == self.expected_box_count
                assert all(not box for box in self.box_pokemon)
                return self.path + ".new"

        return FakeSave

    factory.instances = instances
    return factory


@pytest.mark.parametrize(
    ("import_name", "class_name", "game", "box_count", "expected_source"),
    IMPORT_CASES,
)
def test_import_flow_commits_batch_then_clears_and_writes(
    main_module,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    fake_save_factory,
    import_name: str,
    class_name: str,
    game: str,
    box_count: int,
    expected_source: str,
) -> None:
    source_path = tmp_path / "input.sav"
    source_path.write_bytes(b"placeholder")
    events = []
    batches = []

    monkeypatch.setattr(main_module, "init_tables", lambda: events.append("init"))

    def save_batch(records):
        events.append("database-commit")
        batches.append(list(records))

    monkeypatch.setattr(main_module, "add_pokemon_batch", save_batch)
    fake_class = fake_save_factory(box_count, expected_source)
    monkeypatch.setattr(main_module, class_name, fake_class)

    importer = getattr(main_module, import_name)
    result = importer(str(source_path), game)

    save = fake_save_factory.instances[-1]
    assert result == str(source_path) + ".new"
    assert save.print_count == 1
    assert save.write_count == 1
    assert events.index("init") < events.index("database-commit")
    assert len(batches) == 1
    assert [mon.name for mon in batches[0]] == ["PartyMon", "BoxMon"]
    assert all(mon.game_name == expected_source for mon in batches[0])


@pytest.mark.parametrize(
    ("import_name", "class_name", "game", "box_count", "default_source", "expected_source"),
    [
        pytest.param("import_gen1", "Gen1_Save", "red", 12, "red", "generation-1", id="gen1-source-override"),
        pytest.param("import_gen3", "Gen3_Save", "ruby", 14, "ruby", "generation-3", id="gen3-source-override"),
        pytest.param("import_gen5", "Gen5_Save", "black", 24, "black", "generation-5", id="gen5-source-override"),
        pytest.param("import_gen7", "Gen7_Save", "moon", 32, "moon", "generation-7", id="gen7-source-override"),
    ],
)
def test_import_respects_explicit_source_game(
    main_module,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    fake_save_factory,
    import_name: str,
    class_name: str,
    game: str,
    box_count: int,
    default_source: str,
    expected_source: str,
) -> None:
    path = tmp_path / "input.sav"
    path.write_bytes(b"placeholder")
    captured = []
    monkeypatch.setattr(main_module, "init_tables", Mock())
    monkeypatch.setattr(main_module, "add_pokemon_batch", lambda records: captured.extend(records))
    monkeypatch.setattr(main_module, class_name, fake_save_factory(box_count, default_source))

    getattr(main_module, import_name)(str(path), game, source_game=expected_source)

    assert captured
    assert all(pokemon.game_name == expected_source for pokemon in captured)


@pytest.mark.parametrize(
    ("import_name", "game"),
    [
        ("import_gen1", "not-a-game"),
        ("import_gen2", "not-a-game"),
        ("import_gen3", "not-a-game"),
        ("import_gen5", "not-a-game"),
        ("import_gen6", "not-a-game"),
        ("import_gen7", "not-a-game"),
    ],
)
def test_invalid_game_is_rejected_before_database_initialization(
    main_module, monkeypatch: pytest.MonkeyPatch, import_name: str, game: str
) -> None:
    initialize = Mock()
    monkeypatch.setattr(main_module, "init_tables", initialize)

    with pytest.raises(ValueError):
        getattr(main_module, import_name)("unused.sav", game)

    initialize.assert_not_called()


def test_database_batch_failure_does_not_clear_or_write_save(
    main_module,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    fake_save_factory,
) -> None:
    path = tmp_path / "input.sav"
    path.write_bytes(b"placeholder")
    FakeSave = fake_save_factory(12, "red")
    monkeypatch.setattr(main_module, "Gen1_Save", FakeSave)
    monkeypatch.setattr(main_module, "init_tables", Mock())

    def fail_batch(_records):
        raise RuntimeError("simulated SQLite failure")

    monkeypatch.setattr(main_module, "add_pokemon_batch", fail_batch)

    with pytest.raises(RuntimeError, match="simulated SQLite failure"):
        main_module.import_gen1(str(path), "red")

    save = fake_save_factory.instances[-1]
    assert len(save.party_pokemon) == 1
    assert len(save.box_pokemon) == 1
    assert len(save.box_pokemon[0]) == 1
    assert save.write_count == 0


@pytest.mark.parametrize(
    ("game", "target"),
    [
        pytest.param("red", "import_gen1", id="gen1"),
        pytest.param("silver", "import_gen2", id="gen2"),
        pytest.param("emerald", "import_gen3", id="gen3"),
        pytest.param("heartgold", "import_gen4", id="gen4"),
        pytest.param("white2", "import_gen5", id="gen5"),
        pytest.param("alphasapphire", "import_gen6", id="gen6"),
        pytest.param("ultramoon", "import_gen7", id="gen7"),
    ],
)
def test_cli_routes_explicit_game_to_correct_importer(
    main_module, monkeypatch: pytest.MonkeyPatch, game: str, target: str
) -> None:
    spies = {
        name: Mock()
        for name in (
            "import_gen1", "import_gen2", "import_gen3", "import_gen4",
            "import_gen5", "import_gen6", "import_gen7",
        )
    }
    for name, spy in spies.items():
        monkeypatch.setattr(main_module, name, spy)
    monkeypatch.setattr(sys, "argv", ["main.py", "sample.sav", "--game", game])

    main_module.main()

    spies[target].assert_called_once_with("sample.sav", game=game)
    for name, spy in spies.items():
        if name != target:
            spy.assert_not_called()


def test_cli_auto_mode_uses_detected_generation_layout(
    main_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "argv", ["main.py", "sample.sav"])
    monkeypatch.setattr(
        main_module, "detect_save_game", lambda _path: (6, "x", "generation-6")
    )
    importer = Mock()
    monkeypatch.setattr(main_module, "import_gen6", importer)

    main_module.main()

    importer.assert_called_once_with(
        "sample.sav", game="x", source_game="generation-6"
    )


def test_cli_help_exits_successfully(main_module, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.setattr(sys, "argv", ["main.py", "--help"])

    with pytest.raises(SystemExit) as exc:
        main_module.main()

    assert exc.value.code == 0
    output = capsys.readouterr().out
    assert "--game" in output
    assert "save_file" in output
