# Carrier Unlock Pro — initial source package

## Implemented
- FastAPI backend: `/health`, `/eligibility` (self-reported precheck only), `/requests` (draft tracking), `/requests/{id}`.
- SQLite local draft storage; only last four IMEI digits stored.
- Windows-compatible Tkinter GUI that lists *authorized* Android devices using ADB.
- Android `MainActivity.kt` source displaying manufacturer, model, and Android version (not a complete Android project).
- Basic backend unit tests.

## NOT implemented / carrier-dependent
- Actual carrier unlock, carrier eligibility API integrations, IMEI blacklist verification, iOS USB detection, iPhone unlock activation, SIM/eSIM unlock status, cloud auth, payments, production encryption, or a signed Windows/Android installer.
- No carrier request is submitted. Backend status remains `draft`.
- Device owner consent and approved carrier integrations are prerequisites for live workflows.

## Run backend
```sh
cd backend
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r ../requirements.txt
uvicorn app:app --reload --host 127.0.0.1 --port 8000
```
Open http://127.0.0.1:8000/docs . The development server is local-only.

## Run tests
```sh
cd backend
python -m pytest -q
```

## Run Windows desktop diagnostics
Install Google Android SDK Platform Tools (`adb` on PATH). Enable USB debugging on a device you own or are authorized to service, accept the phone's authorization dialog, then:
```sh
python desktop/main.py
```

## Android build status
`android/MainActivity.kt` is a starter source file, not a buildable Android Studio project or APK. To build, create an Android Studio Empty Views Activity project with package `com.carrierunlockpro`, then replace its `MainActivity.kt` with this file. No dangerous permissions required. This displays basic public device metadata only.

## Architecture direction
- Local clients: Tkinter Windows diagnostics; native Kotlin Android diagnostics.
- Backend: FastAPI service, SQLite for development; PostgreSQL for production.
- Carrier adapters: future explicit authorized integrations; policies and approvals per carrier.
- Privacy/security: verify ownership, encrypt sensitive data, audit access, never bypass account/activation locks or blacklist controls.
