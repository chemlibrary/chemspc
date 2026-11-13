"""Flask upload, selective transfer, transaction, and download regressions.

Native parsing/writing is replaced at the format boundary. Routes, sessions,
CSRF checks, selection validation, storage placement, and SQLite are real.
"""
from copy import deepcopy
from io import BytesIO
from pathlib import Path
import sqlite3
from types import SimpleNamespace

import pytest
from werkzeug.datastructures import MultiDict

from pokemon import Pokemon
from save_formats import GAME_SPECS, SAVE_SIZES


def native_pokemon(generation, name):
    pokemon = Pokemon(generation=generation, name=name, species=25, level=20,
                      move1=33, original_trainer_name='ASH')
    if generation == 1:
        pokemon._gen1_box_record = bytes(33)
        pokemon._gen1_species_index = 0x54
        pokemon._gen1_ot_name_bytes = b'\x50' * 11
        pokemon._gen1_nickname_bytes = b'\x50' * 11
    elif generation == 3:
        pokemon.gen3_box_record = bytes(80)
        pokemon._gen3_original_snapshot_box = {'species': 25}
    elif generation in (4, 5):
        setattr(pokemon, f'gen{generation}_box_record', bytes(136))
    elif generation in (6, 7):
        setattr(pokemon, f'gen{generation}_record', bytes(232))
    return pokemon


@pytest.fixture
def web_app(tmp_path, monkeypatch, db_module):
    import main

    upload_dir = tmp_path / 'staging'
    export_dir = tmp_path / 'exports'
    upload_dir.mkdir()
    export_dir.mkdir()
    monkeypatch.setitem(main.app.config, 'TESTING', True)
    monkeypatch.setitem(main.app.config, 'SECRET_KEY', 'test-session-key')
    monkeypatch.setitem(main.app.config, 'UPLOAD_FOLDER', str(upload_dir))
    monkeypatch.setitem(main.app.config, 'EXPORT_FOLDER', str(export_dir))
    db_module.init_tables()
    opened = []
    written = []

    class FakeSave:
        def __init__(self, path, game):
            self.path = Path(path)
            self.game_name = game
            spec = GAME_SPECS[game]
            self.party_pokemon = [native_pokemon(spec.generation, 'PartyMon'),
                                  native_pokemon(spec.generation, 'KeepParty')]
            self.box_pokemon = [[] for _ in range(spec.box_count)]
            self.box_pokemon[0] = [native_pokemon(spec.generation, 'BoxMon'),
                                   native_pokemon(spec.generation, 'KeepBox')]
            # Gen VI/VII placement also updates the retained native box bytes.
            self.save_bytes = bytearray(SAVE_SIZES[game])
            self.box_offset = 0
            self._original_box_records = {}
            for slot, pokemon in enumerate(self.box_pokemon[0]):
                for attr in (f'gen{spec.generation}_box_index', f'gen{spec.generation}_box_number'):
                    setattr(pokemon, attr, 0)
                setattr(pokemon, f'gen{spec.generation}_box_slot', slot)
            opened.append(self)

        def write_save(self):
            written.append(deepcopy(self))
            output = Path(str(self.path) + '.new')
            output.write_bytes(b'generated save')
            return str(output)

    monkeypatch.setattr(main, 'open_save', FakeSave)
    client = main.app.test_client()
    client.get('/')  # Establish a real CSRF token in the session.
    with client.session_transaction() as session:
        csrf = session['csrf_token']

    def post(url, **fields):
        data = MultiDict({'csrf_token': csrf})
        for key, value in fields.items():
            data.setlist(key, value if isinstance(value, list) else [value])
        return client.post(url, data=data)

    def upload(game='crystal', payload=None):
        if payload is None:
            payload = bytes(SAVE_SIZES[game])
        return post('/open-save', game=game, save_file=(BytesIO(payload), 'original.sav'))

    return SimpleNamespace(main=main, db=db_module, client=client, post=post,
                           upload=upload, opened=opened, written=written,
                           upload_dir=upload_dir, export_dir=export_dir)


@pytest.mark.parametrize('game', GAME_SPECS)
def test_selective_import_export_workflow_for_every_game(web_app, game):
    web = web_app
    generation = GAME_SPECS[game].generation
    exported = native_pokemon(generation, 'ExportMon')
    web.db.add_pokemon(exported)
    uid = web.db.list_pokemon()[0]['uid']

    response = web.upload(game)
    assert response.status_code == 302
    assert response.location.endswith('/manage')
    assert web.opened[-1].game_name == game
    source = web.opened[-1].path
    original = source.read_bytes()
    assert len(original) == SAVE_SIZES[game]
    # Upload/review stage nothing in the database and do not invoke the writer.
    assert web.client.get('/manage').status_code == 200
    assert [row['name'] for row in web.db.list_pokemon()] == ['ExportMon']
    assert not web.written

    response = web.post('/finalize', import_slot=['party:0', 'box:0:0'], export_uid=str(uid))
    assert response.status_code == 302
    assert '/result/' in response.location
    assert 'imported=2' in response.location and 'exported=1' in response.location
    assert len(web.written) == 1
    result = web.written[0]
    assert [p.name for p in result.party_pokemon] == ['KeepParty']
    assert [p.name for p in result.box_pokemon[0]] == ['KeepBox', 'ExportMon']
    assert all(not box for box in result.box_pokemon[1:])

    rows = web.db.list_pokemon()
    assert [row['name'] for row in rows] == ['PartyMon', 'BoxMon']
    for row in rows:
        restored = web.db.row_to_pokemon(row)
        assert restored.source_game == game
        assert restored.game_name == game
        assert web.main.has_native_export_record(restored, generation)
    inactive = web.db.list_pokemon(active=False)
    assert [(row['uid'], row['name']) for row in inactive] == [(uid, 'ExportMon')]
    assert web.main.has_native_export_record(web.db.row_to_pokemon(inactive[0]), generation)

    assert web.client.get(response.location).status_code == 200
    with web.client.session_transaction() as session:
        token = session['last_export_token']
        assert 'workflow_id' not in session
    downloaded = web.client.get(f'/download/{token}')
    assert downloaded.status_code == 200
    assert downloaded.data == b'generated save'
    assert 'original_chemspc.sav' in downloaded.headers['Content-Disposition']
    assert not source.parent.exists()
    assert [p.name for p in web.export_dir.iterdir()] == [f'{token}.sav']
    # Generated outputs are restricted to the originating session.
    other_client = web.main.app.test_client()
    assert other_client.get(f'/download/{token}').status_code == 404
    assert other_client.get(f'/result/{token}').status_code == 404


@pytest.mark.parametrize('game', GAME_SPECS)
def test_upload_trims_trailer_before_parser_without_changing_input(web_app, game, tmp_path):
    web = web_app
    payload = b'A' * SAVE_SIZES[game] + b'emulator trailer'
    original_file = tmp_path / 'original.sav'
    original_file.write_bytes(payload)
    with original_file.open('rb') as incoming:
        response = web.post('/open-save', game=game, save_file=(incoming, 'test.sav'))
    assert response.location.endswith('/manage')
    assert web.opened[-1].path.read_bytes() == payload[:SAVE_SIZES[game]]
    assert original_file.read_bytes() == payload
    with web.client.session_transaction() as session:
        assert any('trailing bytes' in message for _, message in session['_flashes'])


@pytest.mark.parametrize('fields', [
    {}, {'game': 'not-a-game'}, {'game': 'crystal'},
])
def test_invalid_upload_does_not_activate_workflow(web_app, fields):
    response = web_app.post('/open-save', **fields)
    assert response.location.endswith('/')
    assert not web_app.opened
    assert list(web_app.upload_dir.iterdir()) == []
    with web_app.client.session_transaction() as session:
        assert 'workflow_id' not in session


@pytest.mark.parametrize('failure', ['short', 'parser'])
def test_failed_upload_is_cleaned_up(web_app, monkeypatch, failure):
    if failure == 'parser':
        def reject(*args):
            raise ValueError('Invalid save checksum')
        monkeypatch.setattr(web_app.main, 'open_save', reject)
    response = web_app.upload(payload=b'short' if failure == 'short' else None)
    assert response.location.endswith('/')
    assert list(web_app.upload_dir.iterdir()) == []
    assert not web_app.db.list_pokemon()


@pytest.mark.parametrize('route', ['/open-save', '/finalize', '/cancel'])
@pytest.mark.parametrize('token', [None, 'wrong-token'])
def test_mutating_routes_require_session_csrf(web_app, route, token):
    data = {} if token is None else {'csrf_token': token}
    assert web_app.client.post(route, data=data).status_code == 400
    assert not web_app.written
    assert not web_app.db.list_pokemon()


@pytest.mark.parametrize(('fields', 'message'), [
    ({}, 'Select at least one'),
    ({'import_slot': ['party:0', 'party:0']}, 'duplicate'),
    ({'import_slot': 'box:99:0'}, 'no longer exist'),
    ({'export_uid': 'not-an-integer'}, 'invalid database'),
    ({'export_uid': '99999'}, 'no longer active'),
])
def test_invalid_selections_leave_save_and_database_unchanged(web_app, fields, message):
    web = web_app
    web.upload()
    source = web.opened[-1].path
    original = source.read_bytes()
    response = web.post('/finalize', **fields)
    assert response.location.endswith('/manage')
    with web.client.session_transaction() as session:
        assert any(message in text for _, text in session['_flashes'])
        assert 'workflow_id' in session
    assert source.read_bytes() == original
    assert not web.db.list_pokemon()
    assert not web.written
    assert list(web.export_dir.iterdir()) == []


def test_cross_generation_export_is_rejected_before_writing(web_app):
    web = web_app
    web.db.add_pokemon(native_pokemon(3, 'WrongGen'))
    uid = web.db.list_pokemon()[0]['uid']
    web.upload('crystal')
    response = web.post('/finalize', import_slot='party:0', export_uid=str(uid))
    assert response.location.endswith('/manage')
    assert [row['uid'] for row in web.db.list_pokemon()] == [uid]
    assert not web.db.list_pokemon(active=False)
    assert not web.written


@pytest.mark.parametrize('failure', ['database', 'publish', 'writer'])
def test_failed_finalization_rolls_back_and_retains_staged_source(web_app, monkeypatch, failure):
    web = web_app
    web.db.add_pokemon(native_pokemon(2, 'ExportMon'))
    uid = web.db.list_pokemon()[0]['uid']
    web.upload()
    source = web.opened[-1].path
    original = source.read_bytes()
    if failure == 'database':
        # Fail after imports and the export move have executed, so rollback
        # must undo changes to both tables.
        real_move = web.db.move_active_to_inactive
        def fail_move(connection, selected_uid):
            real_move(connection, selected_uid)
            raise sqlite3.IntegrityError('simulated database failure')
        monkeypatch.setattr(web.db, 'move_active_to_inactive', fail_move)
    elif failure == 'publish':
        def fail_publish(*args):
            raise OSError('simulated publish failure')
        monkeypatch.setattr(web.main.os, 'replace', fail_publish)
    else:
        def fail_write(*args):
            raise OSError('simulated writer failure')
        monkeypatch.setattr(type(web.opened[-1]), 'write_save', fail_write)

    response = web.post('/finalize', import_slot=['party:0', 'box:0:0'], export_uid=str(uid))
    assert response.location.endswith('/manage')
    assert [(row['uid'], row['name']) for row in web.db.list_pokemon()] == [(uid, 'ExportMon')]
    assert not web.db.list_pokemon(active=False)
    assert source.read_bytes() == original
    assert not Path(str(source) + '.new').exists()
    assert list(web.export_dir.iterdir()) == []
    with web.client.session_transaction() as session:
        assert 'workflow_id' in session
        assert 'last_export_token' not in session


def test_cancel_discards_only_staged_workflow(web_app):
    web = web_app
    web.db.add_pokemon(native_pokemon(2, 'Stored'))
    web.upload()
    source = web.opened[-1].path
    response = web.post('/cancel')
    assert response.location.endswith('/')
    assert not source.parent.exists()
    assert [row['name'] for row in web.db.list_pokemon()] == ['Stored']
    assert not web.written
    assert web.client.get('/manage').location.endswith('/')


@pytest.mark.parametrize('route', ['/result/not-a-token', '/download/not-a-token',
                                   '/result/' + 'a' * 32, '/download/' + 'a' * 32])
def test_unknown_downloads_and_results_are_not_found(web_app, route):
    assert web_app.client.get(route).status_code == 404
