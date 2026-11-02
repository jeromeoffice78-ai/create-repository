# Studio media worker

Private Python/FFmpeg service for the Bubble studio. No secrets or user media are committed.

## Verified scope

Assembly accepts ordered, contiguous video shots and actual audio files. It normalizes FPS and resolution, applies source trims, cut edits, per-shot captions, audio start offsets and gain, then produces H.264/AAC MP4. It rejects missing footage, duration mismatch, invalid trims, and unsupported transitions. Completion requires measured frame count, FPS, resolution, duration, and expected audio to pass.

The worker accepts the studio's current `Target / SHOTS / AUDIO` text manifest and a structured JSON manifest. `Video` and `Lip Sync` operations call public Hugging Face Gradio services. Their quota, model availability, identity preservation, and execution time are external limitations. Failed GPU requests are recorded as Failed, never as finished output.

## API

- `GET /health`: operational flags, no credentials.
- `POST /jobs`: bearer-authenticated `{job, kind, payload, callback?, model?}`; returns provider `job_id` and status.
- `GET /jobs/{job_id}`: bearer-authenticated status, measured properties, error and temporary signed output URL.
- `GET /files/{job_id}?expires=...&signature=...`: expiring, signed MP4 download.

Supported kinds are `Assembly`, `MP4`, `Video`, and `Lip Sync`. Image-to-video payloads use `{image_url,prompt,duration,seed}`; lip-sync uses `{video_url,audio_url,seed}`. A text prompt alone cannot stand in for approved references.

## Configuration

- `STUDIO_ADAPTER_TOKEN`: required secret. Missing token stops startup.
- `RENDER_EXTERNAL_URL` or `STUDIO_PUBLIC_URL`: service origin for signed output URLs.
- `STUDIO_DATA_DIR`: scratch job/output directory; default `/tmp/studio-media`.
- `BUBBLE_CALLBACK_URL`: optional fixed studio webhook URL.
- `BUBBLE_API_TOKEN`: optional private Bubble callback bearer token. Never accepted from a request.
- `HF_TOKEN`: optional server-side Hugging Face token for the GPU provider. Not required for local assembly.

Callbacks are sent only to the fixed configured Bubble host, never to arbitrary request URLs. When callback authentication is missing or a callback fails, the job exposes `callback_error` and remains available through authenticated polling.

## Limits

Free Render compute is suitable for limited serial assembly tests, not a guarantee of production render throughput. No paid plan is activated by this repository. Workload is bounded to four queued/running jobs, 80 shots, 100 audio tracks, 600 seconds, 1080p, and 256 MB per source. The service uses an ephemeral filesystem; jobs are not durable across instance replacement. An interrupted job is marked Failed on restart if its job database survives. Outputs must be downloaded into durable storage before release. Temporary provider URLs and this worker's signed files are not a release archive.

## Run and test

Python 3.12, FFmpeg/ffprobe with libx264 and drawtext, and DejaVu Sans are required. The Dockerfile supplies them.

```sh
python -m unittest -v test_worker.py
python worker.py
```

The test suite actually renders and decodes a two-shot captioned video with a mixed audio track. It also verifies frame counts and rejects gaps, missing footage, short sources, unsupported transitions, malformed durations and unsafe download URLs.

## Restart and delivery repair (v1.1)

Accepted requests are saved with their job IDs in SQLite. Startup resumes interrupted requests under the same ID when the data directory survives. Legacy interrupted jobs without a saved manifest and completed jobs whose files are missing are marked Failed explicitly. This cannot recover files lost when an ephemeral Render instance is replaced.

Failed fixed-destination callbacks retry up to five total attempts with backoff, once credentials are configured. The existing authenticated polling API remains available. Callback attempts and actual durable storage status are returned by the API; health includes version and restart-recovery support. Logs record sanitized job events and FFmpeg exit codes, without media URLs or credentials.

The H.264 encoder is explicitly limited to one output thread, in addition to existing decoder/filter limits, to reduce memory pressure on the small instance. User request objects are copied before normalization. Eight tests pass, including a real 1080p, 24-frame audio/video export, recovery retaining the job ID, legacy DB migration, missing-output detection, callback retry/clear behavior, and the existing two-shot captioned render.

For persistent storage, mount a disk exactly at `/data` and keep `STUDIO_DATA_DIR=/data`. Mounted storage defaults to no automatic expiration; ephemeral storage defaults to the prior 24-hour cleanup. `STUDIO_RETENTION_SECONDS` can override this (0 disables expiration). Disk capacity and the existing 2 GB worker storage guard still require archiving/space management. No recurring plan charge or disk was activated by the code change. See STORAGE_PLAN.md.
