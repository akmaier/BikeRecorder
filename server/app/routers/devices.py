from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from ..auth import CurrentUser
from ..database import get_session
from ..models import Device
from ..schemas import DeviceRead, DeviceRegisterRequest

router = APIRouter(prefix="/devices", tags=["devices"])


@router.post("/register", response_model=DeviceRead)
def register_device(
    payload: DeviceRegisterRequest,
    current_user: CurrentUser,
    session: Session = Depends(get_session),
) -> DeviceRead:
    device = Device(
        user_id=current_user.id,
        platform=payload.platform,
        model=payload.model,
        os_version=payload.os_version,
        app_version=payload.app_version,
    )
    session.add(device)
    session.commit()
    session.refresh(device)
    return DeviceRead(
        id=device.id,
        platform=device.platform,
        model=device.model,
        os_version=device.os_version,
        app_version=device.app_version,
    )
