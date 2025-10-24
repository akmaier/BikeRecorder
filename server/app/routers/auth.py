import datetime as dt
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from .. import schemas
from ..auth import create_access_token
from ..config import settings
from ..database import get_session
from ..models import User, UserRole

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/token", response_model=schemas.TokenResponse)
def issue_token(payload: schemas.TokenRequest, session: Session = Depends(get_session)) -> schemas.TokenResponse:
    statement = select(User).where(User.email == payload.email)
    user = session.exec(statement).first()
    if not user:
        if not settings.allow_registration:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Registration disabled")
        user = User(email=payload.email, name=payload.name, role=UserRole.USER)
        session.add(user)
        session.commit()
        session.refresh(user)
    token = create_access_token(subject=user.id, email=user.email, role=user.role)
    return schemas.TokenResponse(access_token=token, user_id=user.id)
