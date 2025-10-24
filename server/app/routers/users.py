from fastapi import APIRouter

from ..auth import CurrentUser
from ..schemas import UserRead

router = APIRouter(prefix="/me", tags=["users"])


@router.get("", response_model=UserRead)
def read_me(current_user: CurrentUser) -> UserRead:
    return UserRead(id=current_user.id, email=current_user.email, name=current_user.name, role=current_user.role)
