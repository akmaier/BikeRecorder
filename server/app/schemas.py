import datetime as dt
import uuid
from typing import Optional

from pydantic import BaseModel, Field

from .models import DevicePlatform, FileType, TripStatus, UploadStatus, UserRole


class TokenRequest(BaseModel):
    email: str
    password: str
    name: Optional[str] = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: uuid.UUID


class UserRead(BaseModel):
    id: uuid.UUID
    email: str
    name: Optional[str]
    role: UserRole


class DeviceRegisterRequest(BaseModel):
    platform: DevicePlatform
    model: str
    os_version: str
    app_version: Optional[str] = None


class DeviceRead(BaseModel):
    id: uuid.UUID
    platform: DevicePlatform
    model: str
    os_version: str
    app_version: Optional[str]


class TripCreateRequest(BaseModel):
    device_id: uuid.UUID
    start_time_utc: dt.datetime
    capture_profile: Optional[str] = None


class TripUpdateRequest(BaseModel):
    end_time_utc: Optional[dt.datetime] = None
    duration_s: Optional[int] = None
    distance_m: Optional[float] = None
    status: Optional[TripStatus] = None


class TripRead(BaseModel):
    id: uuid.UUID
    device_id: uuid.UUID
    start_time_utc: dt.datetime
    end_time_utc: Optional[dt.datetime]
    duration_s: Optional[int]
    distance_m: Optional[float]
    status: TripStatus


class SegmentCreateRequest(BaseModel):
    index: int = 0
    video_codec: Optional[str] = None
    audio_codec: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    fps: Optional[float] = None
    expected_bytes: int


class SegmentCompleteRequest(BaseModel):
    file_size_bytes: Optional[int] = None
    duration_s: Optional[float] = None
    sha256: Optional[str] = None
    status: Optional[TripStatus] = None


class SegmentRead(BaseModel):
    id: uuid.UUID
    trip_id: uuid.UUID
    index: int
    file_size_bytes: Optional[int]
    duration_s: Optional[float]
    sha256: Optional[str]
    created_at: dt.datetime


class UploadCreateRequest(BaseModel):
    trip_id: uuid.UUID
    segment_id: uuid.UUID
    filename: str
    file_type: FileType
    sha256: str
    upload_length: int = Field(gt=0)


class UploadRead(BaseModel):
    id: uuid.UUID
    trip_id: uuid.UUID
    segment_id: uuid.UUID
    filename: str
    file_type: FileType
    sha256: str
    upload_length: int
    offset: int
    status: UploadStatus


class StoredFileRead(BaseModel):
    id: uuid.UUID
    type: FileType
    sha256: Optional[str]
    bytes: int
    storage_uri: str


class SegmentMetadataRequest(BaseModel):
    type: FileType
    content: str
    filename: Optional[str] = None


class DownloadToken(BaseModel):
    token: str
    expires_at: dt.datetime


class TripDetail(TripRead):
    segments: list[SegmentRead]


class TripsResponse(BaseModel):
    trips: list[TripDetail]
