"""Retain browser sessions across container restarts using the data volume."""
import os
from pathlib import Path
import secrets
import sys


def main() -> None:
    if not os.environ.get("CHEMSPC_SECRET_KEY"):
        secret_path = Path(os.environ["CHEMSPC_INSTANCE_PATH"]) / ".session-secret"
        secret_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(secret_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(fd, "w") as secret_file:
                secret_file.write(secrets.token_hex(32))
        secret = secret_path.read_text().strip()
        if not secret:
            raise RuntimeError(f"Session secret file is empty: {secret_path}")
        os.environ["CHEMSPC_SECRET_KEY"] = secret
    os.execvp(sys.argv[1], sys.argv[1:])


if __name__ == "__main__":
    main()
