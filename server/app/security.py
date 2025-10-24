import datetime as dt
import uuid

import jwt

from .config import settings


def create_download_token(file_id: uuid.UUID, expires_in: int = 600) -> tuple[str, dt.datetime]:
    now = dt.datetime.now(dt.timezone.utc)
    expires_at = now + dt.timedelta(seconds=expires_in)
    payload = {
        "file_id": str(file_id),
        "exp": int(expires_at.timestamp()),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, expires_at


def verify_download_token(token: str) -> uuid.UUID:
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    file_id = payload.get("file_id")
    if not file_id:
        raise ValueError("Invalid token")
    return uuid.UUID(file_id)
