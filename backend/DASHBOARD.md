# Dashboard API

Backend contracts for the planned projects, history and scan-detail screens.
There is no frontend in this package. OpenAPI: `../contracts/openapi.json`.

## Authentication and browser setup

`GET /v1/dashboard-config` is public and returns the dashboard Cognito client,
authorization/token/revocation/logout endpoints, PKCE method S256, callback and
logout URL. `/v1/config` retains the CLI client and callback. Both clients use the
same User Pool; ownership is the authenticated user's `sub`, never the client ID.
Send an access token with scope `infralens/api` as `Authorization: Bearer ...`.
ID tokens and other app clients are rejected. The frontend should use an OIDC
client with state/nonce/PKCE validation and render report content as text.
Only make HTTP/HTTPS references clickable; never render report-provided HTML.

Deploy parameter `DashboardOrigin` defaults to `http://localhost:5173` and registers
`/auth/callback` and `/` for login/logout. Only that exact origin is allowed by
API Gateway CORS (GET, PUT, POST, DELETE, OPTIONS; authorization/content-type).
Change the parameter to the future dashboard HTTPS origin before publishing it.
S3 report downloads use browser navigation to the presigned attachment URL;
browser code does not fetch or parse the full JSON, so S3 CORS is unnecessary.
Presigned links expire after five minutes; request a new link when necessary.

## Screens and endpoints

| Screen/action | Request |
| --- | --- |
| Projects | `GET /v1/projects?include=latest_scan&limit=20` |
| Create project | `PUT /v1/projects/{project_id}` with `{"name":"My project"}` |
| Project header | `GET /v1/projects/{project_id}?include=latest_scan` |
| Project history | `GET /v1/runs?project_id=...&from=...&to=...&limit=20` |
| Scan metadata | `GET /v1/runs/{run_id}` |
| Findings | `GET /v1/runs/{run_id}/findings?severity=HIGH&rule_id=AVD-...&file=main.tf&limit=20` |
| Finding detail | `GET /v1/runs/{run_id}/findings/{finding_id}` |
| Retry failed/missing analysis | `POST /v1/runs/{run_id}/analysis/retry` |
| JSON download link | `GET /v1/runs/{run_id}/artifacts/json` |
| Delete scan | `DELETE /v1/runs/{run_id}` |

Lists return `items` and `next_cursor`; keep requesting while a cursor exists,
including when a filtered page has no items. Page sizes are 1–100, default20.
Findings filters are AND-combined, case-sensitive exact matches, one value each.
Findings sort CRITICAL, HIGH, MEDIUM, LOW, UNKNOWN, then stable finding ID. Cursors
are bound to owner/run/generation/build/filter; changing filters resets pagination.
File and rule indexes, and history/latest-scan summaries, are eventually
consistent. The unfiltered finding list and detail use strong reads. If a filtered
list briefly lags a ready analysis, retry it; never replace the scan's total with
the number of items on a page. No numeric page count or full-text search exists.

`latest_scan` is optional and only included on request; null means no visible
ready upload. It summarizes run ID, start/finish times and caller-reported result.
Lookups share a 120-page/eight-second budget per request and return retryable503
`latest_scan_unavailable` if exhausted. Do not interpret that error as no scans.
History is ordered by scan start time, not upload completion time.

## Upload state, analysis state and threshold

These are separate concepts. `upload_status=ready` means the original JSON is
stored and downloadable. Its `result.threshold_status` can still be `failed`.
After completion, optional `analysis` contains:

- `status`: pending, ready or failed.
- `version`, `build_id`, `requested_at`, `completed_at`.
- `findings`: server-derived total/by_severity, available when ready.
- `counts_match`: whether derived counts agree with the CLI manifest.
- `error_code`: safe diagnostic code on failure.

The immutable caller-reported `result` is preserved. These derived counts verify
the supplied report's contents, not whether Trivy actually scanned a real source.
Findings endpoints return409 `analysis_pending`, `analysis_failed` or
`analysis_unavailable` until ready. Read metadata for the actual state. A pending
retry returns202 without creating another attempt; ready returns200; failed or
legacy unindexed runs start a fresh build and return202. Frontends can poll run
metadata with a bounded backoff and stop once ready or failed.

Findings include only Trivy misconfigurations with status FAIL (missing Status
also means FAIL); PASS/EXCEPTION are excluded. Detail includes message,
description, resolution, references and plain source excerpt if provided by
`CauseMetadata.Code.Lines`. Missing locations remain null. `Target="."` is not
presented as a concrete file. Highlighted HTML from reports is never retained.
`truncated_fields` identifies clipped fields; the JSON download remains complete.

## Processing, limits and deletion

Metadata changes trigger a DynamoDB Stream mapping filtered to ready uploads
with pending analysis. It uses batches of one, three retries, maximum record age
15minutes and an encrypted SQS on-failure queue (14days). A durable cleanup job
precedes derived writes. Findings are isolated by owner/run generation/build and
remain private until the complete build is published conditionally.

The worker parses/spools the native JSON incrementally, with limits of100,000
native entries, 8,192 events and512KiB text per finding, 4KiB target paths and1KiB
rule IDs. Detail fields are bounded (text16KiB each, title1KiB, resource4KiB,
20references of2KiB each, 40source lines of1KiB each). Oversized/unsupported
findings fail analysis without losing the original JSON. Lambda timeout is600s;
work stops normally after500s of processing. Deliveries must start within5minutes
of request; expired pending jobs become failed, allowing explicit retry.

Hourly cleanup marks abandoned pending builds failed after20minutes, deletes
failed/orphan partitions in batches of500 and rechecks ready builds hourly.
An active ready build is never expired. A scan delete immediately hides its
metadata/findings;202 means physical cleanup is pending. Tombstones cover signed
PUT expiry and the possible worker lifetime. Derived data is removed by the
hourly cleanup job, including abandoned earlier attempts. Never display pending
uploads or failed indexing as zero findings.

## Existing reports and failure recovery

The migration is additive. Existing ready uploads keep their metadata/downloads;
they need indexing before findings endpoints can serve them. The operator script
uses the existing AWS profile, validates the account and defaults to read-only:

```bash
uv run --project backend python backend/scripts/backfill_analysis.py \
  --account 695650811791 --stack infralens-dev --maximum 100
```

Add `--apply` to queue missing indexes, and `--include-failed` to retry failures.
The script changes metadata; the deployed stream runs analysis asynchronously.
It never replaces already-ready indexes or duplicates pending work. Review worker
logs and SQS failures if builds stop processing; once20minutes have passed,
invoke/schedule cleanup and retry through the API or backfill script. Clear only
failure-queue messages whose corresponding runs have been recovered or removed.

New resources retain the deployment tags. FindingsTable is retained and deletion
protected like StorageTable: export inventory, disable protection and explicitly
delete both tables when tearing down the environment. The stream mapping, worker,
role, logs, failure queue and dashboard app client are stack-managed.
