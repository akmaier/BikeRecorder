import datetime as dt
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from sqlmodel import Session

from ..auth import CurrentUser
from ..config import settings
from ..database import get_session
from ..models import FileType, Segment, StoredFile, Trip, UploadSession, UploadStatus
from ..schemas import UploadCreateRequest, UploadRead
from ..services.storage import finalize_upload, get_upload_path, write_chunk

router = APIRouter(prefix="/uploads", tags=["uploads"])


@router.post("", response_model=UploadRead, status_code=status.HTTP_201_CREATED)
def create_upload(
    payload: UploadCreateRequest,
    current_user: CurrentUser,
    session: Session = Depends(get_session),
) -> UploadRead:
    trip = session.get(Trip, payload.trip_id)
    segment = session.get(Segment, payload.segment_id)
    if not trip or not segment or segment.trip_id != trip.id or trip.user_id != current_user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Trip or segment not found")
    upload = UploadSession(
        trip_id=payload.trip_id,
        segment_id=payload.segment_id,
        filename=payload.filename,
        file_type=payload.file_type,
        sha256=payload.sha256,
        upload_length=payload.upload_length,
        status=UploadStatus.PENDING,
    )
    session.add(upload)
    session.commit()
    session.refresh(upload)
    return UploadRead(
        id=upload.id,
        trip_id=upload.trip_id,
        segment_id=upload.segment_id,
        filename=upload.filename,
        file_type=upload.file_type,
        sha256=upload.sha256,
        upload_length=upload.upload_length,
        offset=upload.offset,
        status=upload.status,
    )


@router.head("/{upload_id}")
def head_upload(
    upload_id: uuid.UUID,
    current_user: CurrentUser,
    session: Session = Depends(get_session),
) -> Response:
    upload = session.get(UploadSession, upload_id)
    if not upload or upload.trip.user_id != current_user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Upload not found")
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.headers["Upload-Offset"] = str(upload.offset)
    response.headers["Upload-Length"] = str(upload.upload_length)
    return response


@router.patch("/{upload_id}", status_code=status.HTTP_204_NO_CONTENT)
async def patch_upload(
    upload_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser,
    session: Session = Depends(get_session),
    upload_offset: int = Header(alias="Upload-Offset"),
) -> Response:
    upload = session.get(UploadSession, upload_id)
    if not upload or upload.trip.user_id != current_user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Upload not found")
    if upload.status == UploadStatus.COMPLETE:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Upload already complete")
    if upload.offset != upload_offset:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Offset mismatch")
    body = await request.body()
    if not body:
        response = Response(status_code=status.HTTP_204_NO_CONTENT)
        response.headers["Upload-Offset"] = str(upload.offset)
        return response
    path = get_upload_path(str(upload.id))
    write_chunk(path, body, upload.offset)
    upload.offset += len(body)
    upload.status = UploadStatus.RECEIVING
    upload.updated_at = dt.datetime.now(dt.timezone.utc)
    session.add(upload)
    session.commit()
    if upload.offset >= upload.upload_length:
        dest_dir = settings.storage_dir / "segments" / str(upload.segment_id)
        dest_dir.mkdir(parents=True, exist_ok=True)
        final_path = dest_dir / upload.filename
        computed_sha, size = finalize_upload(path, final_path)
        if computed_sha != upload.sha256:
            final_path.unlink(missing_ok=True)
            upload.status = UploadStatus.FAILED
            session.add(upload)
            session.commit()
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Checksum mismatch")
        stored_file = StoredFile(
            segment_id=upload.segment_id,
            type=upload.file_type,
            storage_uri=str(final_path.relative_to(settings.storage_dir)),
            sha256=computed_sha,
            bytes=size,
        )
        session.add(stored_file)
        segment = session.get(Segment, upload.segment_id)
        if segment:
            if upload.file_type == FileType.VIDEO_MP4:
                segment.file_size_bytes = size
                segment.sha256 = computed_sha
            session.add(segment)
        upload.status = UploadStatus.COMPLETE
        session.add(upload)
        session.commit()
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.headers["Upload-Offset"] = str(upload.offset)
    return response
