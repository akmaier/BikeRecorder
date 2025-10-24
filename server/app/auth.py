import datetime as dt
import uuid
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import Session, select

from .config import settings
from .database import get_session
from .models import User, UserRole


bearer_scheme = HTTPBearer()


class AuthError(HTTPException):
    def __init__(self, detail: str, status_code: int = status.HTTP_401_UNAUTHORIZED):
        super().__init__(status_code=status_code, detail=detail)


def create_access_token(*, subject: uuid.UUID, email: str, role: UserRole) -> str:
    now = dt.datetime.now(dt.timezone.utc)
    payload = {
        "sub": str(subject),
        "email": email,
        "role": role.value,
        "iat": int(now.timestamp()),
        "exp": int((now + dt.timedelta(minutes=settings.access_token_ttl_minutes)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def _get_user_by_id(session: Session, user_id: uuid.UUID) -> User:
    statement = select(User).where(User.id == user_id)
    user = session.exec(statement).first()
    if not user:
        raise AuthError("User not found")
    return user


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    session: Session = Depends(get_session),
) -> User:
    if credentials.scheme.lower() != "bearer":
        raise AuthError("Invalid authentication scheme")
    try:
        payload = jwt.decode(credentials.credentials, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as exc:  # pragma: no cover - best effort logging path
        raise AuthError("Invalid token") from exc
    subject = payload.get("sub")
    if subject is None:
        raise AuthError("Token missing subject")
    try:
        user_id = uuid.UUID(subject)
    except ValueError as exc:  # pragma: no cover - guard
        raise AuthError("Invalid subject") from exc
    return _get_user_by_id(session, user_id)


CurrentSession = Annotated[Session, Depends(get_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]
