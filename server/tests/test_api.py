import datetime as dt
import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.database import init_db, reset_engine
from app.main import create_app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    storage_dir = tmp_path / "storage"
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{db_path}")
    monkeypatch.setattr(settings, "storage_dir", storage_dir)
    storage_dir.mkdir(parents=True, exist_ok=True)
    reset_engine(settings.database_url)
    init_db()
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


def _auth_headers(client: TestClient, email: str = "test@example.com") -> dict[str, str]:
    response = client.post("/auth/token", json={"email": email, "password": "secret"})
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_trip_upload_flow(client: TestClient, tmp_path: Path):
    headers = _auth_headers(client)
    # register device
    response = client.post(
        "/devices/register",
        json={"platform": "android", "model": "Pixel", "os_version": "14", "app_version": "1.0"},
        headers=headers,
    )
    device = response.json()
    # create trip
    start_time = dt.datetime.now(dt.timezone.utc).isoformat()
    response = client.post(
        "/trips",
        json={"device_id": device["id"], "start_time_utc": start_time},
        headers=headers,
    )
    trip = response.json()
    # create segment
    response = client.post(
        f"/trips/{trip['id']}/segments",
        json={"index": 0, "video_codec": "h264", "expected_bytes": 13},
        headers=headers,
    )
    segment = response.json()
    # create upload session
    fake_content = b"bike recorder"
    sha = hashlib.sha256(fake_content).hexdigest()
    upload_resp = client.post(
        "/uploads",
        json={
            "trip_id": trip["id"],
            "segment_id": segment["id"],
            "filename": "segment.mp4",
            "file_type": "video_mp4",
            "sha256": sha,
            "upload_length": len(fake_content),
        },
        headers=headers,
    )
    upload = upload_resp.json()
    # patch upload
    patch_resp = client.patch(
        f"/uploads/{upload['id']}",
        data=fake_content,
        headers={"Upload-Offset": "0", **headers, "Content-Type": "application/offset+octet-stream"},
    )
    assert patch_resp.status_code == 204
    # finalize segment
    complete = client.patch(
        f"/trips/{trip['id']}/segments/{segment['id']}",
        json={"file_size_bytes": len(fake_content), "sha256": sha, "status": "complete"},
        headers=headers,
    )
    assert complete.status_code == 200
    # attach metadata
    metadata_resp = client.post(
        f"/segments/{segment['id']}/metadata",
        json={"type": "gps_jsonl", "content": json.dumps({"ts": start_time, "lat": 0, "lon": 0})},
        headers=headers,
    )
    assert metadata_resp.status_code == 201
    # list trips
    trips_resp = client.get("/trips", headers=headers)
    assert trips_resp.status_code == 200
    trips = trips_resp.json()["trips"]
    assert trips
    # request file metadata
    stored_file = metadata_resp.json()
    file_meta = client.get(f"/files/{stored_file['id']}", headers=headers)
    assert file_meta.status_code == 200
