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
