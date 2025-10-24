import datetime as dt
import uuid
from enum import Enum
from typing import Optional

from sqlmodel import Field, Relationship, SQLModel


class UserRole(str, Enum):
    USER = "user"
    ADMIN = "admin"


class User(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    email: str = Field(index=True, unique=True)
    name: Optional[str] = None
    role: UserRole = Field(default=UserRole.USER)
    created_at: dt.datetime = Field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))

    devices: list["Device"] = Relationship(back_populates="user")
    trips: list["Trip"] = Relationship(back_populates="user")


class DevicePlatform(str, Enum):
    ANDROID = "android"
    IOS = "ios"


class Device(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="user.id")
    platform: DevicePlatform
    model: str
    os_version: str
    app_version: Optional[str] = None
    created_at: dt.datetime = Field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))

    user: User = Relationship(back_populates="devices")


class TripStatus(str, Enum):
    RECORDING = "recording"
    QUEUED = "queued"
    UPLOADING = "uploading"
    COMPLETE = "complete"
    FAILED = "failed"


class Trip(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="user.id")
    device_id: uuid.UUID = Field(foreign_key="device.id")
    start_time_utc: dt.datetime
    end_time_utc: Optional[dt.datetime] = None
    duration_s: Optional[int] = None
    distance_m: Optional[float] = None
    status: TripStatus = Field(default=TripStatus.RECORDING)
    created_at: dt.datetime = Field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))

    user: User = Relationship(back_populates="trips")
    segments: list["Segment"] = Relationship(back_populates="trip")


class Segment(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    trip_id: uuid.UUID = Field(foreign_key="trip.id")
    index: int = Field(default=0)
    video_codec: Optional[str] = None
    audio_codec: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    fps: Optional[float] = None
    file_size_bytes: Optional[int] = None
    duration_s: Optional[float] = None
    sha256: Optional[str] = None
    created_at: dt.datetime = Field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))
    completed_at: Optional[dt.datetime] = None

    trip: Trip = Relationship(back_populates="segments")
    files: list["StoredFile"] = Relationship(back_populates="segment")


class FileType(str, Enum):
    VIDEO_MP4 = "video_mp4"
    GPS_GPX = "gps_gpx"
    GPS_JSONL = "gps_jsonl"
    THUMBNAIL_JPEG = "thumbnail_jpg"
    METADATA_JSON = "metadata_json"


class StoredFile(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    segment_id: uuid.UUID = Field(foreign_key="segment.id")
    type: FileType
    storage_uri: str
    sha256: Optional[str] = None
    bytes: int = 0
    created_at: dt.datetime = Field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))

    segment: Segment = Relationship(back_populates="files")


class UploadStatus(str, Enum):
    PENDING = "pending"
    RECEIVING = "receiving"
    COMPLETE = "complete"
    FAILED = "failed"


class UploadSession(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    trip_id: uuid.UUID = Field(foreign_key="trip.id")
    segment_id: uuid.UUID = Field(foreign_key="segment.id")
    filename: str
    file_type: FileType
    sha256: str
    upload_length: int
    offset: int = 0
    status: UploadStatus = Field(default=UploadStatus.PENDING)
    created_at: dt.datetime = Field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))
    updated_at: dt.datetime = Field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))

    trip: Trip = Relationship()
    segment: Segment = Relationship()
