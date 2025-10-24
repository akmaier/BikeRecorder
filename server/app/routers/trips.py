import datetime as dt
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, select

from ..auth import CurrentUser
from ..database import get_session
from ..models import Device, Segment, Trip, TripStatus, UserRole
from ..schemas import (
    SegmentCreateRequest,
    SegmentRead,
    SegmentCompleteRequest,
    TripCreateRequest,
    TripDetail,
    TripRead,
    TripUpdateRequest,
    TripsResponse,
)

router = APIRouter(prefix="/trips", tags=["trips"])


def _ensure_trip_access(trip: Trip, current_user: CurrentUser) -> None:
    if trip.user_id != current_user.id and current_user.role != UserRole.ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Forbidden")


@router.post("", response_model=TripRead, status_code=status.HTTP_201_CREATED)
def create_trip(
    payload: TripCreateRequest,
    current_user: CurrentUser,
    session: Session = Depends(get_session),
) -> TripRead:
    device = session.get(Device, payload.device_id)
    if not device or device.user_id != current_user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Device not found")
    trip = Trip(
        user_id=current_user.id,
        device_id=device.id,
        start_time_utc=payload.start_time_utc,
        status=TripStatus.RECORDING,
    )
    session.add(trip)
    session.commit()
    session.refresh(trip)
    return TripRead(
        id=trip.id,
        device_id=trip.device_id,
        start_time_utc=trip.start_time_utc,
        end_time_utc=trip.end_time_utc,
        duration_s=trip.duration_s,
        distance_m=trip.distance_m,
        status=trip.status,
    )


@router.get("", response_model=TripsResponse)
def list_trips(
    current_user: CurrentUser,
    session: Session = Depends(get_session),
    user_id: uuid.UUID | None = Query(default=None),
) -> TripsResponse:
    statement = select(Trip).order_by(Trip.start_time_utc.desc())
    if user_id and current_user.role == UserRole.ADMIN:
        statement = statement.where(Trip.user_id == user_id)
    else:
        statement = statement.where(Trip.user_id == current_user.id)
    trips = session.exec(statement).all()
    result = []
    for trip in trips:
        segments = session.exec(select(Segment).where(Segment.trip_id == trip.id).order_by(Segment.index)).all()
        result.append(
            TripDetail(
                id=trip.id,
                device_id=trip.device_id,
                start_time_utc=trip.start_time_utc,
                end_time_utc=trip.end_time_utc,
                duration_s=trip.duration_s,
                distance_m=trip.distance_m,
                status=trip.status,
                segments=[
                    SegmentRead(
                        id=segment.id,
                        trip_id=segment.trip_id,
                        index=segment.index,
                        file_size_bytes=segment.file_size_bytes,
                        duration_s=segment.duration_s,
                        sha256=segment.sha256,
                        created_at=segment.created_at,
                    )
                    for segment in segments
                ],
            )
        )
    return TripsResponse(trips=result)


@router.get("/{trip_id}", response_model=TripDetail)
def get_trip(
    trip_id: uuid.UUID,
    current_user: CurrentUser,
    session: Session = Depends(get_session),
) -> TripDetail:
    trip = session.get(Trip, trip_id)
    if not trip:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Trip not found")
    _ensure_trip_access(trip, current_user)
    segments = session.exec(select(Segment).where(Segment.trip_id == trip.id).order_by(Segment.index)).all()
    return TripDetail(
        id=trip.id,
        device_id=trip.device_id,
        start_time_utc=trip.start_time_utc,
        end_time_utc=trip.end_time_utc,
        duration_s=trip.duration_s,
        distance_m=trip.distance_m,
        status=trip.status,
        segments=[
            SegmentRead(
                id=segment.id,
                trip_id=segment.trip_id,
                index=segment.index,
                file_size_bytes=segment.file_size_bytes,
                duration_s=segment.duration_s,
                sha256=segment.sha256,
                created_at=segment.created_at,
            )
            for segment in segments
        ],
    )


@router.patch("/{trip_id}", response_model=TripRead)
def update_trip(
    trip_id: uuid.UUID,
    payload: TripUpdateRequest,
    current_user: CurrentUser,
    session: Session = Depends(get_session),
) -> TripRead:
    trip = session.get(Trip, trip_id)
    if not trip:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Trip not found")
    _ensure_trip_access(trip, current_user)
    if payload.end_time_utc:
        trip.end_time_utc = payload.end_time_utc
    if payload.duration_s is not None:
        trip.duration_s = payload.duration_s
    if payload.distance_m is not None:
        trip.distance_m = payload.distance_m
    if payload.status is not None:
        trip.status = payload.status
    session.add(trip)
    session.commit()
    session.refresh(trip)
    return TripRead(
        id=trip.id,
        device_id=trip.device_id,
        start_time_utc=trip.start_time_utc,
        end_time_utc=trip.end_time_utc,
        duration_s=trip.duration_s,
        distance_m=trip.distance_m,
        status=trip.status,
    )


@router.post("/{trip_id}/segments", response_model=SegmentRead, status_code=status.HTTP_201_CREATED)
def create_segment(
    trip_id: uuid.UUID,
    payload: SegmentCreateRequest,
    current_user: CurrentUser,
    session: Session = Depends(get_session),
) -> SegmentRead:
    trip = session.get(Trip, trip_id)
    if not trip:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Trip not found")
    _ensure_trip_access(trip, current_user)
    segment = Segment(
        trip_id=trip.id,
        index=payload.index,
        video_codec=payload.video_codec,
        audio_codec=payload.audio_codec,
        width=payload.width,
        height=payload.height,
        fps=payload.fps,
        file_size_bytes=payload.expected_bytes,
    )
    session.add(segment)
    session.commit()
    session.refresh(segment)
    if trip.status == TripStatus.RECORDING:
        trip.status = TripStatus.UPLOADING
        session.add(trip)
        session.commit()
    return SegmentRead(
        id=segment.id,
        trip_id=segment.trip_id,
        index=segment.index,
        file_size_bytes=segment.file_size_bytes,
        duration_s=segment.duration_s,
        sha256=segment.sha256,
        created_at=segment.created_at,
    )


@router.patch("/{trip_id}/segments/{segment_id}", response_model=SegmentRead)
def finalize_segment(
    trip_id: uuid.UUID,
    segment_id: uuid.UUID,
    payload: SegmentCompleteRequest,
    current_user: CurrentUser,
    session: Session = Depends(get_session),
) -> SegmentRead:
    trip = session.get(Trip, trip_id)
    if not trip:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Trip not found")
    _ensure_trip_access(trip, current_user)
    segment = session.get(Segment, segment_id)
    if not segment or segment.trip_id != trip.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Segment not found")
    if payload.file_size_bytes is not None:
        segment.file_size_bytes = payload.file_size_bytes
    if payload.duration_s is not None:
        segment.duration_s = payload.duration_s
    if payload.sha256 is not None:
        segment.sha256 = payload.sha256
    segment.completed_at = dt.datetime.now(dt.timezone.utc)
    if payload.status:
        trip.status = payload.status
    session.add(segment)
    session.add(trip)
    session.commit()
    session.refresh(segment)
    return SegmentRead(
        id=segment.id,
        trip_id=segment.trip_id,
        index=segment.index,
        file_size_bytes=segment.file_size_bytes,
        duration_s=segment.duration_s,
        sha256=segment.sha256,
        created_at=segment.created_at,
    )
