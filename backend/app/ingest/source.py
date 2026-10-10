"""Download and fingerprint nflverse release files."""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import httpx

from app.config import get_settings


@dataclass(frozen=True)
class SourceFile:
    url: str
    path: Path
    sha256: str
    version: str | None


def sha256_file(path: Path, chunk_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, dest: Path, *, force: bool = False) -> Path:
    """Download ``url`` to ``dest`` unless it is already cached."""
    if dest.exists() and dest.stat().st_size > 0 and not force:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with (
        httpx.stream("GET", url, follow_redirects=True, timeout=120.0) as resp,
        tmp.open("wb") as fh,
    ):
        resp.raise_for_status()
        for chunk in resp.iter_bytes():
            fh.write(chunk)
    tmp.replace(dest)
    return dest


def pbp_url(season: int) -> str:
    return f"{get_settings().nflverse_pbp_base_url}/play_by_play_{season}.parquet"


def fetch_release_version(cache_dir: Path, *, force: bool = False) -> str | None:
    """Return the ``last_updated`` value from the pbp release ``timestamp.json``."""
    url = f"{get_settings().nflverse_pbp_base_url}/timestamp.json"
    try:
        path = download(url, cache_dir / "pbp_timestamp.json", force=force)
        value = json.loads(path.read_text()).get("last_updated")
    except (httpx.HTTPError, ValueError, OSError):
        return None
    return str(value) if value is not None else None


def fetch_pbp(season: int, cache_dir: Path | None = None, *, force: bool = False) -> SourceFile:
    cache = cache_dir or get_settings().data_cache_dir
    url = pbp_url(season)
    path = download(url, cache / f"play_by_play_{season}.parquet", force=force)
    return SourceFile(
        url=url,
        path=path,
        sha256=sha256_file(path),
        version=fetch_release_version(cache, force=force),
    )
