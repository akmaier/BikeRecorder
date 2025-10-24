import hashlib
from pathlib import Path
from typing import Tuple

from ..config import settings


def get_upload_path(upload_id: str) -> Path:
    return settings.storage_dir / "uploads" / upload_id


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_chunk(path: Path, data: bytes, offset: int) -> int:
    ensure_parent(path)
    with path.open("r+b" if path.exists() else "wb") as fp:
        fp.seek(offset)
        fp.write(data)
    return len(data)


def compute_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fp:
        for chunk in iter(lambda: fp.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def finalize_upload(path: Path, dest: Path) -> Tuple[str, int]:
    ensure_parent(dest)
    path.replace(dest)
    size = dest.stat().st_size
    sha = compute_sha256(dest)
    return sha, size
