# BikeRecorder

BikeRecorder is an end-to-end prototype that lets cyclists capture synchronized video and GPS data on their phone and push the recordings to a FastAPI backend for storage and later processing. The repository contains three main pieces:

- `docs/` — the product specification.
- `server/` — a FastAPI stack that implements authentication, device registration, trip/segment tracking, chunked uploads, and metadata storage.
- `mobile/` — an Expo (React Native) application that records video + GPS, uploads to the backend, and exposes a simple trip history UI for iOS and Android.

## Backend API

### Features
- OAuth-style token issuance (`POST /auth/token`) with signed JWTs.
- Authenticated user profile (`GET /me`).
- Device registration, trip creation, segment lifecycle, resumable uploads with integrity verification, and metadata sidecar handling.
- Download token generation for stored files.
- Health and readiness probes.

### Prerequisites
- Python 3.10+
- (Optional) A virtual environment, e.g. `python -m venv .venv` followed by `source .venv/bin/activate` (Unix/macOS) or `.venv\Scripts\Activate.ps1` (Windows PowerShell).

### Install dependencies
```bash
cd server
pip install -e .[dev]
```

> **Note:** The project depends on `fastapi`, `sqlmodel`, `uvicorn`, and `pyjwt`. In air-gapped environments you will need to pre-seed a local package mirror or vendor the wheels before running the install command.

### Environment configuration
Create a `.env` file in `server/` (the defaults work for local SQLite testing):

```env
BIKE_RECORDER_DATABASE_URL=sqlite:///bike_recorder.db
BIKE_RECORDER_STORAGE_DIR=./storage
BIKE_RECORDER_JWT_SECRET=dev-secret-change-me
BIKE_RECORDER_ACCESS_TOKEN_TTL_MINUTES=60
```

### Running the API locally
```bash
cd server
uvicorn app.main:app --reload
```

The API listens on `http://127.0.0.1:8000` by default. Open `http://127.0.0.1:8000/docs` for interactive Swagger UI.

### Running tests
```bash
cd server
pytest
```

If you see dependency resolution errors (e.g., when outbound network access is blocked), make sure you have installed the required packages from a local mirror before executing `pytest`.

## Mobile Apps (Expo React Native)

The Expo project in `mobile/` provides a cross-platform recorder with login, camera preview, GPS capture, chunked uploads, and trip history. It targets iOS 15+ and Android 8.0+.

### Prerequisites
- Node.js 18+
- `npm` or `yarn`
- Expo CLI (`npm install -g expo-cli`)
- Xcode (for iOS Simulator) or Android Studio (for Android Emulator) with at least one device image installed.

### Install dependencies
```bash
cd mobile
npm install
```

### Configure runtime
The mobile client needs to know how to reach your backend.

1. Make sure the API from the previous section is running and reachable on your LAN.
2. Update the default server URL in the login screen or hardcode a value by editing `mobile/App.tsx` (the default is `http://localhost:8000`).
3. For real devices, replace `localhost` with your machine's IP address that the phone can reach.

### Running on iOS
```bash
cd mobile
npx expo run:ios
```
- Ensure an iOS simulator is running (or a device is connected) before executing the command.
- Grant camera and location permissions when prompted.

### Running on Android
```bash
cd mobile
npx expo run:android
```
- Start an Android emulator (API level 26 or later) or connect a physical device with USB debugging enabled.
- Approve camera and location permission prompts.

### Recorder workflow
1. Launch the app and log in with an email/password. The backend automatically provisions the user and issues a JWT.
2. Tap **Start Recording** to begin video + GPS capture. The HUD shows elapsed time and GPS samples collected.
3. Tap **Stop Recording** to finalize the video. The app computes checksums, creates a trip and segment, uploads the file in tus-style chunks, sends GPS JSONL metadata, and marks the trip complete.
4. Navigate to **History** to review uploaded trips, segment sizes, and hashes.

## Repository layout
```
.
├── docs/
│   └── product_spec.md
├── mobile/
│   ├── App.tsx
│   ├── app.json
│   ├── assets/
│   ├── package.json
│   └── ...
├── server/
│   ├── app/
│   │   ├── main.py
│   │   ├── routers/
│   │   └── ...
│   ├── pyproject.toml
│   └── tests/
└── README.md
```

## Additional notes
- Change `BIKE_RECORDER_JWT_SECRET` before deploying anywhere beyond local testing.
- The backend stores files under `server/storage/segments/<segment_id>/`. Clean up this directory periodically if you run many local tests.
- The Expo app is a prototype; production deployment should migrate to native modules for long-running recording and background uploads.
