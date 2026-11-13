"""Atomic binary output shared by the standalone generation handlers."""
import os
from pathlib import Path
import tempfile


def bytes_safe_write(*, path: str | os.PathLike, contents: bytes | bytearray) -> None:
    """Replace output only after a complete write; clean up on failure."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f'.{destination.name}.', suffix='.tmp', dir=destination.parent)
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(contents)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
