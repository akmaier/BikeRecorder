import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import FileResponse
from sqlmodel import Session

from ..auth import CurrentUser
from ..config import settings
from ..database import get_session
from ..models import Segment, StoredFile, Trip, UserRole
from ..schemas import DownloadToken, StoredFileRead
from ..security import create_download_token, verify_download_token

router = APIRouter(prefix="/files", tags=["files"])


@router.get("/{file_id}", response_model=StoredFileRead)
def get_file_metadata(
    file_id: uuid.UUID,
    current_user: CurrentUser,
    session: Session = Depends(get_session),
) -> StoredFileRead:
    stored_file = session.get(StoredFile, file_id)
    if not stored_file:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="File not found")
    segment = session.get(Segment, stored_file.segment_id)
    trip = session.get(Trip, segment.trip_id) if segment else None
    if not segment or not trip:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Segment not found")
    if trip.user_id != current_user.id and current_user.role != UserRole.ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Forbidden")
    return StoredFileRead(
        id=stored_file.id,
        type=stored_file.type,
        sha256=stored_file.sha256,
        bytes=stored_file.bytes,
        storage_uri=stored_file.storage_uri,
    )


@router.get("/{file_id}/download", response_model=DownloadToken)
def get_download_token(
    file_id: uuid.UUID,
    current_user: CurrentUser,
    session: Session = Depends(get_session),
) -> DownloadToken:
    stored_file = session.get(StoredFile, file_id)
    if not stored_file:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="File not found")
    segment = session.get(Segment, stored_file.segment_id)
    trip = session.get(Trip, segment.trip_id) if segment else None
    if not segment or not trip:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Segment not found")
    if trip.user_id != current_user.id and current_user.role != UserRole.ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Forbidden")
    token, expires_at = create_download_token(file_id)
    return DownloadToken(token=token, expires_at=expires_at)


@router.get("/download")
def download_file(token: str, session: Session = Depends(get_session)) -> Response:
    try:
        file_id = verify_download_token(token)
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid token") from exc
    stored_file = session.get(StoredFile, file_id)
    if not stored_file:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="File not found")
    file_path = settings.storage_dir / stored_file.storage_uri
    if not file_path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="File missing from storage")
    return FileResponse(file_path)
