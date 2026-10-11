"""File storage for private uploads and generated exports.

Files are stored under random UUID names, never under user-supplied names, in a
directory that no web server serves. Content is only ever parsed as data. The
``Storage`` protocol keeps callers independent of the backend so an object store
(S3, in the cloud milestone) can replace the shared local volume without touching
upload or export code.
"""

import os
import shutil
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from typing import BinaryIO, Literal, Protocol

from app.config import get_settings

Area = Literal["uploads", "exports"]
COPY_CHUNK = 1024 * 1024


class FileTooLargeError(Exception):
    def __init__(self, limit: int) -> None:
        super().__init__(f"File exceeds the {limit // (1024 * 1024)} MB limit")
        self.limit = limit


class Storage(Protocol):
    def save(self, area: Area, stream: BinaryIO, *, suffix: str, max_bytes: int) -> tuple[str, int]:
        """Store a stream; returns (key, size). Raises FileTooLargeError past max_bytes."""
        ...

    def write_bytes(self, area: Area, data: bytes, *, suffix: str) -> str: ...

    def open(self, key: str) -> BinaryIO: ...

    def delete(self, key: str) -> None: ...

    def exists(self, key: str) -> bool: ...


class LocalStorage:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def _path(self, key: str) -> Path:
        area, _, name = key.partition("/")
        if area not in ("uploads", "exports") or not name or "/" in name or name.startswith("."):
            raise ValueError(f"invalid storage key {key!r}")
        return self.root / area / name

    def _new_key(self, area: Area, suffix: str) -> str:
        return f"{area}/{uuid.uuid4().hex}{suffix}"

    def save(self, area: Area, stream: BinaryIO, *, suffix: str, max_bytes: int) -> tuple[str, int]:
        key = self._new_key(area, suffix)
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".part")
        size = 0
        try:
            with tmp.open("wb") as out:
                while chunk := stream.read(COPY_CHUNK):
                    size += len(chunk)
                    if size > max_bytes:
                        raise FileTooLargeError(max_bytes)
                    out.write(chunk)
            os.replace(tmp, path)
        finally:
            tmp.unlink(missing_ok=True)
        return key, size

    def write_bytes(self, area: Area, data: bytes, *, suffix: str) -> str:
        key = self._new_key(area, suffix)
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".part")
        tmp.write_bytes(data)
        os.replace(tmp, path)
        return key

    def open(self, key: str) -> BinaryIO:
        return self._path(key).open("rb")

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def clear(self) -> None:
        """Test helper: remove everything under the root."""
        shutil.rmtree(self.root, ignore_errors=True)


@contextmanager
def opened(storage: Storage, key: str) -> Iterator[BinaryIO]:
    handle = storage.open(key)
    try:
        yield handle
    finally:
        handle.close()


@lru_cache
def get_storage() -> LocalStorage:
    return LocalStorage(get_settings().storage_dir)
