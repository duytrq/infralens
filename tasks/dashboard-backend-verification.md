# Dashboard backend verification

Implementation and AWS dev deployment completed on 2026-10-22 (local timezone).
Scope is backend only; the dashboard frontend and CLI cloud commands remain
separate work. API contract: `contracts/openapi.json`; integration guide:
`backend/DASHBOARD.md`.

## Local checks

- Backend: **104 passed**. Covers normalization/suppression, bounded source
  excerpts, pending/ready/failed indexing, retry, duplicate stream deliveries,
  owner isolation, filters, sparse pages, cursor owner/filter/build binding and
  long filters, latest-scan budget, active deletion and reused run generations.
- CLI regression: **176 passed**, one Windows-only skip, 12 optional integration
  tests deselected. CLI source unchanged.
- Ruff check/format, cfn-lint for both templates, OpenAPI export/validation and
  offline SAM transformation pass. All14 API routes match the contract; only
  CLI/dashboard config routes are public. Worker/queue/mapping tags checked.
- SAM build and isolated Python3.12 runtime imports pass for all three functions.
  Pinned runtime requirements match the backend lockfile. Wheel/sdist build passes.
- Locked runtime/development dependency audit: no known vulnerabilities.
- Mutation experiment: inverting the access-token condition causes the focused
  auth regression test to fail; original file restored.
- Streaming benchmark: 51,487,311-byte native JSON, 1,000 findings, validation and
  normalization11.439s, peak RSS120,408KiB on this Linux machine. This excludes
  AWS upload/DynamoDB writes and is not an end-to-end latency guarantee.

## AWS dev checks

Account695650811791, profiledefault, regionap-southeast-1, stackinfralens-dev
UPDATE_COMPLETE. Existing bucket/table/pool were updated without replacement.
Inventory: `infra/deployments/infralens-dev.json` (40 stack resources, 19taggable
resources verified across backend and deployment-artifact stacks).
Evidence: `infra/deployments/infralens-dev-dashboard-verification.json`.

- Real Cognito hosted-login HTTP flow + state/PKCE token exchange for CLI and
  dashboard clients; same user sees the same project. This verifies the auth
  protocol, not browser rendering or a dashboard UI.
- Missing/invalid/ID tokens rejected; two-user project/run/findings/download/
  retry/delete isolation verified.
- Exact-origin CORS preflight works; an untrusted origin receives no allow header.
- Actual presigned HTTPS PUT, immutable overwrite rejection, complete, DynamoDB
  stream delivery and deployed analysis worker publish correct derived counts.
- Actual findings pagination, severity/rule/file filters, cursor rejection,
  plain source excerpt, project latest scan/history and JSON download pass.
- Delete immediately hides findings and latest-scan summary.
- Malformed native finding fails analysis while preserving JSON; retry creates
  another build. Legacy report backfill is dry-run by default and applying it
  invokes the real stream worker. Deployed cleanup removes an isolated orphan
  findings partition/job using its actual IAM role.
- Dashboard refresh-token revocation tested.
- Post-check: zero temporary test users, report objects, failure-queue messages
  or ERROR logs in API/analysis/cleanup groups over the verification hour.

Three test-run deletion tombstones remain protected until their signed-upload/
worker windows expire; their derived partitions/jobs are removed by scheduled
cleanup. This is expected deletion behavior. No real user account was changed;
synthetic accounts were created with invitations suppressed and removed afterward.

## Review fixes

Read-only independent review identified and confirmed fixes for unbounded nested
finding materialization and unbounded latest-scan lookups. Follow-up targeted
tests passed with no remaining required issue. A vanished cleanup job cannot be
recreated by UpdateItem; cursor filter hashes keep long-path cursors bounded.

## Remaining product work

Build the three dashboard screens against these APIs and set DashboardOrigin to
the deployed HTTPS origin. No frontend hosting resources were provisioned here.

## Internal-tool simplification

The initial verification above included an SQS failure destination. Following
user feedback, remove that queue and its permission/destination. Recovery uses
run metadata, existing CloudWatch logs and manual retry/backfill. The refreshed
resource inventory describes the simplified deployment.

Removal verified on AWS dev: stack UPDATE_COMPLETE; old queue no longer exists,
stream remains Enabled with no failure destination, and the worker role has no
SQS permission. API config200/protected route401, seven focused tests, lint,
SAM transform/build and three isolated artifacts pass. See
`infra/deployments/infralens-dev-sqs-removal-verification.json`.
