# BikeRecorder Product Specification

## 1. Product Overview

### 1.1 Goal
Enable authenticated users to mount a smartphone on a bicycle, record video with synchronized GPS coordinates, and upload the captured data to a backend once on Wi-Fi (or per user policy). Data will be stored, validated, and made available for downstream processing.

### 1.2 Primary Users & Roles
- **Rider (User):** Records, reviews, and uploads trips.
- **Admin:** Manages users, monitors ingestion, performs maintenance, exports data.

### 1.3 Platforms
- **Mobile:** Android (SDK 26+, Android 8.0+) and iOS (iOS 15+).
- **Server:** Ubuntu LTS (22.04+), x86_64 VM, public HTTPS endpoint.

---

## 2. Mobile App Requirements

### 2.1 Core User Flows
1. **Login/Onboarding**
   - Email + password or federated login (OpenID Connect/OAuth2).
   - Permissions walkthrough (Camera, Microphone if needed for video, Location "While Using the App" + "Precise", Motion activity (optional), Notifications).
   - Terms of Use & Privacy consent capture (timestamped).
2. **Recording**
   - Tap **Start Recording** → Begin **video** and **GPS** capture.
   - Live preview with basic HUD: timer, GPS fix quality, storage left, battery %, current speed.
   - Tap **Stop** → finalize segment, write metadata, enqueue upload.
   - Continue in **foreground** for iOS (prevent auto-lock); Android uses a foreground service with persistent notification.
3. **Upload**
   - Automatic background upload when on Wi-Fi by default (while charging configurable).
   - Resumable, chunked uploads with integrity checks.
   - Progress & status (Queued, Uploading, Paused (metered), Complete, Failed).
4. **History**
   - List "Trips" with date, duration, distance, status, size.
   - Detail view: map trace (polyline), per-segment info, quick playback.
5. **Settings**
   - Capture profile (e.g., 1080p/60, 1080p/30, 720p/30).
   - GPS rate (1 Hz default, 5 Hz optional if device supports).
   - Upload policy (Wi-Fi only default; Wi-Fi or cellular; only when charging).
   - Storage cap (e.g., auto-delete local after successful upload).
   - Privacy: blur faces/plates (if edge processing is added later), anonymize device ID in exports.

### 2.2 Functional Requirements (Mobile)

#### 2.2.1 Recording & Synchronization
- **Video container:** MP4 (H.264/AVC baseline or high profile). HEVC/H.265 optional toggle.
- **Audio:** Optional (default: Off). If On, record mono AAC; informs iOS background modes (see constraints).
- **GPS sampling:** Default 1 Hz (configurable 1–5 Hz). Capture lat, lon, altitude, speed, bearing, HDOP/accuracy, timestamp (UTC).
- **Time sync:** Use monotonic clock for inter-stream alignment. All samples in UTC with millisecond precision.
- **Metadata embedding:**
  - Option A (simple): Store GPS as separate JSON Lines file per segment and a GPX file for interoperability.
  - Option B (preferred long-term): Write GPS as MP4 timed metadata tracks (ISO BMFF) for frame-near alignment.
- **Segmenting:** Long recordings split into segments (e.g., 4 GB or 30 min) to avoid file corruption and ease retries.
- **Frame/time alignment:** Store mapping of video PTS ranges to GPS timestamps; ensure max drift ≤ 200 ms @1 Hz (interpolate for per-frame values).

#### 2.2.2 Reliability, Interruptions & Edge Cases
- **Foreground operation (iOS):** Keep screen awake while recording (disable auto-lock). iOS does not permit camera capture in background; app must remain foreground.
- **Android foreground service:** Show ongoing recording notification; continue with screen off.
- **Low storage:** Warn at <10% free; hard stop at <2% with graceful finalize.
- **Low battery:** Warn at 10%; allow continue; auto stop at 1–2% if OS signals imminent shutdown.
- **GPS loss (tunnels/urban canyons):** Continue recording video; mark GPS gaps; interpolate only for display (never for ground truth).
- **Phone calls/interruptions:** If camera session interrupted, auto-resume where supported; otherwise stop & finalize segment; notify user.
- **Crash safety:** Write metadata and index incrementally; fsync at safe intervals; automatic recovery next launch.
- **Corruption checks:** Compute SHA-256 for each file upon finalize.

#### 2.2.3 Uploads
- **Trigger conditions:** By policy (default Wi-Fi + charging). Manual override per trip.
- **Protocol:** Resumable, chunked (e.g., tus.io or custom with Range PUT). Chunk size 5–16 MB, exponential backoff with jitter.
- **Integrity:** Per-chunk checksum (e.g., MD5) and final SHA-256; server verifies before commit.
- **Encryption in transit:** TLS 1.2+; certificate pinning optional.
- **Content addressing:** Server deduplicates by SHA-256; mobile sends digest preflight.
- **Retry logic:** Network errors retry up to 10 times with increasing backoff; persist state across app restarts.

#### 2.2.4 UX & Accessibility
- Single large start/stop button; big numeric readouts; high-contrast theme for sunlight.
- Voice feedback toggles (e.g., “Recording started”, “GPS fix acquired”).
- Minimum touch targets 44×44 pt; Dynamic Type support; color-blind friendly map polyline.

#### 2.2.5 Permissions
- **Camera**, **Microphone** (if audio), **Location (Precise, While Using)**, **Motion & Fitness** (optional), **Photos/Media** (scoped storage on Android).
- Graceful degradation if permissions partially granted; clear rationale screens.

### 2.3 Non-Functional (Mobile)
- **Battery:** ≤ 10%/hour at 1080p30 + 1 Hz GPS on reference device (recent mid-range phone).
- **Performance:** Start recording ≤ 2 s; UI maintains ≥ 30 FPS preview on supported hardware.
- **Storage:** Record size estimates shown pre-start (e.g., 1080p30 H.264 ≈ 130–200 MB/5 min depending on scene).
- **Privacy:** No background location when not recording; no analytics by default; opt-in diagnostics.
- **Security:** Secure token storage (Android Keystore / iOS Keychain); JWT/OAuth tokens with refresh; pin sensitive settings behind OS auth optional.
- **Localization:** English initially; infrastructure for i18n.

### 2.4 Platform-Specific Constraints
- **iOS:** Must remain foreground to capture video; disable auto-lock while recording; use `AVAssetWriter` + `CoreLocation`. Background upload allowed with `BGProcessingTask` and `NSURLSession` background transfers when on Wi-Fi.
- **Android:** Use `CameraX`/`MediaRecorder` + `FusedLocationProviderClient`; foreground service for recording; WorkManager for uploads with network/charging constraints; scoped storage compliance.

---

## 3. Server Requirements (Ubuntu VM)

### 3.1 Architecture Overview
- **Ingress/API:** REST (and/or gRPC later) over HTTPS (NGINX or Caddy as reverse proxy).
- **Auth:** OAuth2/OIDC (e.g., Keycloak/Auth0) issuing JWT access tokens; roles: `user`, `admin`.
- **Upload Gateway:** Resumable upload endpoint (e.g., tusd or custom service).
- **Storage:**
  - **Object store:** S3-compatible (MinIO) or filesystem volume (ext4/xfs) with directory hashing by SHA-256.
  - **DB:** PostgreSQL 14+ for metadata (users, trips, segments, files, locations index).
- **Processing:** Asynchronous workers (Celery/RQ/Sidekiq-like) for validation, metadata extraction (ffprobe), optional map-matching, preview generation (thumbnails), and privacy transforms if enabled.
- **Queue:** Redis for jobs.
- **Observability:** Prometheus + Grafana; structured logs to Loki/ELK; alerts via Alertmanager.
- **Deployment:** Docker Compose (single VM) with .env; optional Terraform/Ansible bootstrap.
- **Backups:** Nightly Postgres dumps; object storage versioning and lifecycle rules.

### 3.2 REST API (minimal baseline)
- `POST /auth/token` (handled by IdP) → access/refresh tokens. Mobile stores refresh token securely; access token TTL ~60 min.
- `GET /me` → profile.
- `POST /devices/register` → register device model, OS, app version.
- `POST /trips` → create trip (start_time, device_id, capture_profile).
- `POST /trips/{trip_id}/segments` → declare a segment (expected bytes, codecs, checksums).
- `PATCH /trips/{trip_id}/segments/{segment_id}` → mark complete, submit final SHA-256, durations.
- `GET /trips?user_id=...` → list.
- `GET /trips/{trip_id}` → detail incl. files & statuses.
- **tus-style endpoints:**
  - `POST /uploads` → create (metadata includes trip_id, segment_id, filename, sha256).
  - `PATCH /uploads/{id}` with chunks (Content-Type: application/offset+octet-stream).
  - `HEAD /uploads/{id}` → query offset.
- On finalize, server verifies SHA-256, persists, and links file → segment.
- `POST /segments/{segment_id}/metadata` → attach sidecars (GPX, JSONL GPS).
- `GET /files/{file_id}` → signed URL (time-limited) for download.
- `GET /healthz`, `GET /readyz`.

### 3.3 Data Model (simplified)
- **User:** id (UUID), email, name, role, created_at
- **Device:** id, user_id, platform (android/ios), model, os_version, app_version, created_at
- **Trip:** id, user_id, device_id, start_time_utc, end_time_utc, duration_s, distance_m (optional computed), status {recording, queued, uploading, complete, failed}, created_at
- **Segment:** id, trip_id, index, video_codec, audio_codec, width, height, fps, file_size_bytes, duration_s, sha256, created_at
- **File:** id, segment_id, type {video_mp4, gps_gpx, gps_jsonl, thumbnail_jpg, metadata_json}, storage_uri, sha256, bytes, created_at
- **LocationSample:** segment_id, ts_utc, lat, lon, alt_m, speed_ms, bearing_deg, accuracy_m (optional if storing raw points server-side; can also remain only in files for scale)
- **UploadBatch:** id, trip_id, created_at, status, total_bytes, completed_bytes

### 3.4 Security
- TLS 1.2+ (Let’s Encrypt); HTTP → HTTPS redirect.
- JWT validation; scopes for `upload:write`, `trip:read`.
- Rate limiting on auth and uploads (per IP and per user).
- At-rest encryption: enable server disk encryption; MinIO SSE if used.
- Content validation: whitelist file types; ffprobe verify stream legality; reject >configured size (e.g., 15 GB).
- PII: GPS is personal data. Provide retention policy and access control. Optional built-in anonymization (coarsen coordinates on exports, or blur pipeline).

### 3.5 Operations
- **Scaling:** Start single VM; move object store to external S3 later. Horizontally scale API and workers with a load balancer.
- **Monitoring Dashboards:** API latency, error rates; upload throughput; pending jobs; disk capacity.
- **Alerting:** High 5xx, low disk (<15%), failing backups, job queue backlog.
- **Backups/Retention:** Daily Postgres dump (retain 30 days), weekly deep backup (retain 6 months). Object store lifecycle tiers (hot→warm).

---

## 4. Data & File Formats

### 4.1 Video
- MP4 container, H.264 (baseline/high), target bitrates per profile (e.g., 1080p30 ≈ 8–12 Mbps; 1080p60 ≈ 12–20 Mbps configurable).

### 4.2 GPS
- **Primary:** JSON Lines (`.jsonl`) with one object per sample:
  ```json
  {"ts":"2025-01-01T12:00:00.000Z","lat":49.476,"lon":11.05,"alt":312.4,"spd":5.2,"brg":185.0,"acc":3.1}
  ```
- **Interoperability:** GPX 1.1 file per segment.
- Optional **MP4 timed metadata** track for in-container sync.

### 4.3 Thumbnails & Index
- Poster frame jpeg every N seconds for quick browse.
- Index JSON summarizing segment boundaries, checksums.

---

## 5. Privacy, Legal, Ethics
- **User consent:** Explicit consent for recording and GPS; display local regulations reminder (e.g., filming in public spaces).
- **Data minimization:** No background location outside active recording.
- **Subject privacy:** Optional face/license-plate blurring (either edge or server job; if server: mark files as “restricted” until processed).
- **Retention:** Configurable default (e.g., 365 days) with per-project overrides; data deletion on user request (GDPR).
- **Research compliance:** Include a template for ethics board (IRB) wording in app About/Settings.

---

## 6. Quality & Acceptance Criteria

### 6.1 Functional Acceptance
- Start/stop reliably on both platforms for ≥ 2-hour continuous runs.
- Synchronized GPS and video timestamps with |Δ| ≤ 200 ms median (≤ 500 ms p95).
- Recover from app crash or power loss with at most the final 5 s lost.
- Upload resumes after connectivity loss with no data corruption (checksum verified).

### 6.2 Performance & Battery
- Battery drain ≤ 10%/h at 1080p30 + 1 Hz; ≤ 15%/h at 1080p60.
- Disk space estimate shown within ±15% of actual usage.

### 6.3 Security
- All endpoints require valid JWT except health checks.
- Transport encryption verified by SSL Labs A grade.

### 6.4 Usability
- A novice completes recording + upload without guidance in < 3 minutes.
- All critical text meets WCAG AA contrast.

---

## 7. Testing Strategy

### 7.1 Mobile
- Unit tests for recording controller, GPS sampler, synchronizer, uploader.
- Instrumentation tests: start/stop cycles; low-storage, low-battery, GPS loss, incoming call.
- Long-run soak tests (2–4 hours).
- Device matrix: sample of recent Android (mid/high), iPhone (A13+).
- **Acceptance tests:**
  1. Validate that starting a recording captures synchronized video and GPS samples at configured rates for at least 30 minutes without drift >200 ms.
  2. Confirm GPS sampling continues when video continues during temporary GPS loss and that gaps are flagged in metadata.
  3. Verify client gracefully queues uploads when offline and resumes once Wi-Fi becomes available, preserving chunk integrity.

### 7.2 Server
- API contract tests (OpenAPI).
- Upload protocol tests: out-of-order chunks, retries, checksum mismatch.
- ffprobe metadata extraction tests; corruption rejection.
- Load tests: sustained 10 concurrent users @ 10 Mbps each; ensure < 300 ms p95 API latencies (non-upload).
- **Integration acceptance tests (no login):**
  1. Simulate unauthenticated client attempting to open upload channel → server returns 401/403 while still serving health checks.
  2. Validate that unauthenticated GPS-only ping endpoint is unavailable, ensuring security posture before login.

---

## 8. Implementation Notes & Tech Choices (recommended)

### Mobile
- **Android:** Kotlin, CameraX `VideoCapture`, `FusedLocationProviderClient`, WorkManager, Room (local metadata cache).
- **iOS:** Swift, AVFoundation (`AVCaptureSession` + `AVAssetWriter`), CoreLocation, BackgroundTasks + background URLSession for uploads.
- **Common:** Wire with OpenAPI client; use protobuf/JSON for small metadata; Maps SDK optional in history view.

### Server
- **Reverse proxy:** Caddy or NGINX.
- **API:** FastAPI (Python) or Node (NestJS); OpenAPI docs.
- **Uploads:** tusd sidecar (battle-tested) or baked into API with S3 multipart upload if using S3/MinIO.
- **Storage:** MinIO (S3-compatible), Postgres, Redis, Celery/RQ workers, ffmpeg/ffprobe container for processing.
- **Containerization:** Docker Compose stack per service; one-command `make up`.

---

## 9. Milestones
1. **M0 — Prototype (2–3 weeks):** Foreground recording, 1080p30, 1 Hz GPS; local storage; manual upload; simple server that accepts single-shot uploads.
2. **M1 — Reliable Uploads:** Resumable uploads + integrity checks; Wi-Fi policy; trip history; server metadata DB.
3. **M2 — Hardening:** Crash recovery, segmenting, long-run stability, monitoring, dashboards, backups.
4. **M3 — Privacy & Admin:** Optional blurring pipeline; role-based access; exports.

---

## 10. Deliverables
- This specification (versioned).
- Mobile app binaries (TestFlight/internal track).
- Server repo (Docker-Compose) with:
  - API service, upload gateway, Postgres, MinIO, Redis, ffmpeg sidecar.
  - OpenAPI spec & Postman collection.
  - Grafana dashboards & alert rules.
  - Backup/restore scripts.
- Ops runbook (deployment, rotate TLS, DB migration, scaling, troubleshooting).

---

## Appendix A — Minimal OpenAPI Sketch (illustrative)
```yaml
openapi: 3.0.3
info: { title: Bike Capture API, version: 1.0.0 }
paths:
  /trips:
    post:
      security: [ bearerAuth: [] ]
      requestBody: { ... }
      responses: { "201": { ... } }
  /trips/{tripId}/segments:
    post: { ... }
  /uploads:
    post: { ... }   # tus create
  /uploads/{id}:
    head: { ... }   # tus query offset
    patch: { ... }  # tus chunk
  /files/{fileId}:
    get: { ... }    # signed download
components:
  securitySchemes:
    bearerAuth: { type: http, scheme: bearer, bearerFormat: JWT }
```
