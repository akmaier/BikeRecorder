import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from ..auth import CurrentUser
from ..config import settings
from ..database import get_session
from ..models import FileType, Segment, StoredFile, Trip, UserRole
from ..schemas import SegmentMetadataRequest, StoredFileRead
from ..services.storage import compute_sha256

router = APIRouter(prefix="/segments", tags=["segments"])


@router.post("/{segment_id}/metadata", response_model=StoredFileRead, status_code=status.HTTP_201_CREATED)
def attach_metadata(
    segment_id: uuid.UUID,
    payload: SegmentMetadataRequest,
    current_user: CurrentUser,
    session: Session = Depends(get_session),
) -> StoredFileRead:
    segment = session.get(Segment, segment_id)
    if not segment:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Segment not found")
    trip = session.get(Trip, segment.trip_id)
    if not trip:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Trip not found")
    if trip.user_id != current_user.id and current_user.role != UserRole.ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Forbidden")
    if payload.type not in {FileType.GPS_GPX, FileType.GPS_JSONL, FileType.METADATA_JSON}:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Unsupported metadata type")
    filename = payload.filename or f"metadata_{payload.type.value}.txt"
    dest_dir = settings.storage_dir / "segments" / str(segment.id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / filename
    dest_path.write_text(payload.content)
    sha = compute_sha256(dest_path)
    stored = StoredFile(
        segment_id=segment.id,
        type=payload.type,
        storage_uri=str(dest_path.relative_to(settings.storage_dir)),
        sha256=sha,
        bytes=dest_path.stat().st_size,
    )
    session.add(stored)
    session.commit()
    session.refresh(stored)
    return StoredFileRead(
        id=stored.id,
        type=stored.type,
        sha256=stored.sha256,
        bytes=stored.bytes,
        storage_uri=stored.storage_uri,
    )
