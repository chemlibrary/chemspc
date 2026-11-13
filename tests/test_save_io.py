"""Save output stays atomic and leaves no temporary files after failures."""
import pytest

import save_io


def test_atomic_writer_replaces_complete_output(tmp_path):
    destination = tmp_path / 'output' / 'test.sav'
    save_io.bytes_safe_write(path=destination, contents=b'first save')
    save_io.bytes_safe_write(path=destination, contents=bytearray(b'replacement save'))
    assert destination.read_bytes() == b'replacement save'
    assert list(destination.parent.iterdir()) == [destination]


@pytest.mark.parametrize('operation', ['fsync', 'replace'])
def test_failed_writer_preserves_destination_and_cleans_temporary_files(tmp_path, monkeypatch, operation):
    destination = tmp_path / 'test.sav'
    destination.write_bytes(b'existing output')

    def fail(*args):
        raise OSError('simulated I/O failure')

    monkeypatch.setattr(save_io.os, operation, fail)
    with pytest.raises(OSError, match='simulated I/O failure'):
        save_io.bytes_safe_write(path=destination, contents=b'incomplete replacement')
    assert destination.read_bytes() == b'existing output'
    assert list(tmp_path.iterdir()) == [destination]
