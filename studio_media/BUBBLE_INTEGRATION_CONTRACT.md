# The Last Repair Studio — Bubble integration contract

Scope: **existing Bubble app**, `the-last-repair-studio`, with its existing database, characters, scripts and designs retained. This file describes the steps still required inside the authenticated Bubble editor. It does **not** assert that any Bubble workflow is already connected. Worker implementation: `studio_media/worker.py` on branch `studio-media-worker`.

## Acceptance target
- Support arbitrary drama projects, episodes, new characters and editable scripts.
- The Last Repair S1: **20 episodes**. Each release candidate must be **180.000 s at 24 FPS = 4,320 frames**, with verified dialogue/audio; Episode 2 is **The Signature**.
- Do not replace user-approved character reference photos with generic AI placeholders. Store approved references and review likeness on every generated shot. The worker can check *media format*, not biometric likeness or acting.
- Never label a scene or episode ready merely because a GPU call returned. Review shot identity, movement, lip-sync, audio, MP4 frame count, and archived asset durability separately.

## Bubble data mapping
Use existing fields if equivalent; do not create duplicate types without inspecting the editor.

- `Project`: title, owner, episodes.
- `Episode`: project, season_number, episode_number, title, target_duration_seconds, target_fps, release_state.
- `Character`: project, name, role, approved_reference_image, approval_state, wardrobe_notes. Approval is user-controlled, not inferred from a video model response.
- `Shot`: episode, sequence, scene, character_refs, source_video, requested_duration_seconds, actual_duration_seconds, start_seconds, review_state.
- `AudioTrack`: episode, source_audio, start_seconds, trim_in, trim_out, gain, speaker_character.
- `ProductionJob`: owner, episode, source_job_id (Bubble unique id), worker_job_id, status, stage, progress, error, viewer_url, output_url, output_expires_at, durable_storage, archived_mp4, last_polled_at.

Keep Project/Episode/Character/Shot/ProductionJob privacy rules scoped to their authenticated owner/editor. Avoid making private reference photos public. Only issue render jobs from Bubble backend workflows, not page JavaScript.

## API Connector calls (private/server-side)

Configure a reusable API connection named `Drama Studio Media Worker` with base URL:
`https://drama-studio-media-worker.onrender.com`

Header: `Authorization: Bearer <STUDIO_ADAPTER_TOKEN>` as a **private value**, never dynamic client data. `Content-Type: application/json`.

**A. Submit render** — `POST /jobs` (Action; private)
Body example (replace all sample sources with *real, user-authorized uploaded clips*):

```json
{
  "job": "<Bubble ProductionJob unique id>",
  "kind": "Assembly",
  "payload": {
    "duration": 180,
    "fps": 24,
    "resolution": "1920x1080",
    "shots": [
      {"source": "<real accessible video URL>", "duration": 180, "start": 0, "transition": "cut"}
    ],
    "audio": [
      {"source": "<real accessible audio URL>", "start": 0, "trim_in": 0, "trim_out": 180, "gain": 1}
    ]
  }
}
```

The example illustrates required keys; one 180-second video is **not** an available AI clip. Actual Assembly jobs must use all approved, contiguous, real shot clips and legitimate audio assets. The worker supports at most 80 shots per job, so a 180-second episode assembled from 5-second clips must be grouped as needed. Verify source durations before submission.

Successful response is HTTP 202 with `job_id`, `source_job`, `viewer_url`, `status`, `stage`, `progress`, `output`, and `error`. Store returned identifiers on the same ProductionJob.

**B. Recover status** — `GET /jobs/latest?source_job=<ProductionJob unique id>` (Data; private), every ~5 seconds *only while* status is `Queued` or `Processing`. This avoids losing the worker ID on a page reload. Read `job_id`, `viewer_url`, `status`, `progress`, `stage`, `error`, `output`, `output_expires_at`, `durable_storage`, `frames`, `fps`, `duration`, and `has_audio`. Stop polling at `Completed` or `Failed`. Do not allow arbitrary `source_job` from another user to display private job status.

**C. Viewer** — Only embed/open the returned `viewer_url` from a trusted **server-side** API response. It is a one-hour scoped URL and does *not* contain the private bearer token. The worker already restricts iframe framing to `the-last-repair-studio.bubbleapps.io`. Do not use the worker `/files` URL as your permanent episode library.

**D. Archive** — On `Completed`, Bubble's backend must download and persist MP4 output to durable project-controlled storage **before** the signed URL expires or the ephemeral worker restarts. Store that archival URL only after verifying the upload, and never mark a project `Released` simply because `status=Completed`.

**E. Failure** — On `Failed`, show the safe worker `error` and a Retry action that creates a new attempt linked to the same ProductionJob. Do not overwrite approved references or delete source assets.

## Bubble editor workflows to wire
1. **Assemble Episode** button → validate ownership, approved shots, user-confirmed releases of reference images, real media and audio, target seconds/FPS. Create ProductionJob with `Queued`.
2. Call private `POST /jobs` using that ProductionJob unique id; persist `job_id` and `viewer_url`.
3. **Episode Render Monitor** → poll private `GET /jobs/latest` while active; show exact `stage`, `progress`, and error. On browser reload recover by `source_job`.
4. **Preview** → open returned scoped `viewer_url` only to authenticated owners/editors. The worker can preview MP4 but cannot enforce Bubble data rules.
5. **Archive** → store completed MP4 in persistent storage; verify readable video and measured duration/FPS/frame count and audio. Perform user review of faces, wardrobe, acting, and lip-sync.
6. **Publish** → require archived verified MP4, required approvals and explicit user publishing action. Configure social-platform integrations separately and obtain platform authorization as necessary.

## Provider boundaries (do not mark ready without proof)
- Wan2.2 video generation is a *short clip* service (previous integration documented five seconds max at 16 FPS), not a 180-second 24-FPS episode generator.
- Lip Forcing is limited to short audio segments (previous integration documented eight seconds); check each segment before submission.
- Model credentials, quotas, callback authentication, and durable storage have not been verified through this contract. No secrets belong in this repository.
- Source clips must be licensed or otherwise authorized. Use the approved user reference assets; do not generate unauthorized replacements.
- Backend `Video`/`Lip Sync` endpoints do not prove character identity or release quality.

## Acceptance test in authenticated Bubble editor
- Use a signed-in Studio owner and an existing project; confirm privacy on another account.
- Submit a small **real** approved clip+audio, receive a worker ID and non-empty signed viewer URL.
- Watch stages move; verify playable frame-accurate MP4; reload and recover by Bubble ID.
- Verify failed job error display, expired viewer rejection, missing output handling, and durable archive link.
- Run the full Episode 2 gate: exactly 180 seconds × 24 FPS = 4,320 actual output frames; synced speech for every speaking character; approved cast likeness and costumes; archived MP4.
- Test on REVVL Tab 2 Chrome and Android packaging. An Android APK is not verified until installed and exercised on device.

**Status when authored:** Existing backend supports the status/viewer contract; the Bubble editor was not accessible in the current tool session. This integration plan is implementation-ready guidance, **not** a claim of completed Bubble editing or final rendering.
