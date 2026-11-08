"""Container sessions must survive recreation without embedding secrets in images."""
import importlib.util
from pathlib import Path

import pytest


@pytest.fixture
def entrypoint(monkeypatch, tmp_path):
    path = Path(__file__).resolve().parents[1] / "docker" / "entrypoint.py"
    spec = importlib.util.spec_from_file_location("container_entrypoint", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setenv("CHEMSPC_INSTANCE_PATH", str(tmp_path / "instance"))
    monkeypatch.delenv("CHEMSPC_SECRET_KEY", raising=False)
    monkeypatch.setattr(module.sys, "argv", ["entrypoint.py", "gunicorn", "main:app"])
    calls = []
    monkeypatch.setattr(module.os, "execvp", lambda *args: calls.append(args))
    return module, tmp_path / "instance" / ".session-secret", calls


def test_generated_secret_is_private_and_reused(entrypoint, monkeypatch):
    module, path, calls = entrypoint
    module.main()
    secret = path.read_text()
    assert len(bytes.fromhex(secret)) == 32
    assert path.stat().st_mode & 0o777 == 0o600
    assert module.os.environ["CHEMSPC_SECRET_KEY"] == secret
    assert calls == [("gunicorn", ["gunicorn", "main:app"])]

    monkeypatch.delenv("CHEMSPC_SECRET_KEY")
    module.main()
    assert module.os.environ["CHEMSPC_SECRET_KEY"] == secret
    assert path.read_text() == secret


def test_explicit_secret_takes_precedence(entrypoint, monkeypatch):
    module, path, _ = entrypoint
    monkeypatch.setenv("CHEMSPC_SECRET_KEY", "explicit-test-secret")
    module.main()
    assert module.os.environ["CHEMSPC_SECRET_KEY"] == "explicit-test-secret"
    assert not path.exists()


def test_empty_saved_secret_prevents_startup(entrypoint):
    module, path, calls = entrypoint
    path.parent.mkdir()
    path.write_text("")
    with pytest.raises(RuntimeError, match="Session secret file is empty"):
        module.main()
    assert calls == []
