# Prepared persistent-storage setup

Target: the existing drama-studio-media-worker service in My Workspace. Reuse the existing service, repository and studio-media-worker branch. Do not create a duplicate service.

Proposed change, pending explicit billing authorization:

- Change only this service from Free to the lowest paid compute tier (currently $7/month, 512 MB).
- Attach a 5 GB disk mounted at /data (currently $0.25 per provisioned GB/month, $1.25/month).
- Keep STUDIO_DATA_DIR=/data, one service instance, and the existing private adapter token.
- Estimated base total: $8.25/month before any tax, bandwidth/build overage or separate AI provider charges. Verify the dashboard quote before purchase; do not approve a higher charge automatically.
- The current worker allows up to 512 MB sources per job, 1 GB per-job scratch, and checks a 2 GB existing-storage threshold before admitting new jobs. Five GB leaves room for a working job and retained output. This is limited operational capacity, not a season archive.
- A paid instance with a disk is single-instance and has a short deployment interruption. Previously lost ephemeral data cannot be restored by attaching the disk.

Verification after attachment: health must report durable_storage=true and storage=persistent_mount. Submit a public-fixture job, save its ID, await measured completion, download and decode the output, restart once, and verify the same job ID and output remain available.

Callback delivery remains a separate step. Set only the fixed BUBBLE_CALLBACK_URL and existing authorized BUBBLE_API_TOKEN in Render secret settings. Never copy that admin token into browser-facing records or client-supplied callback parameters. If there is no existing authorized Bubble token or its Workflow API cannot run on the current Bubble plan, use a properly initialized polling/download workflow instead; do not fake callback delivery.

This document is preparation only. No paid compute, disk, new token, or billing change has been activated.
