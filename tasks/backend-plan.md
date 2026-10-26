# Backend implementation plan

User decisions: shared Infralens service, Cognito authentication, private data per
account, local clients first, dashboard later, JSON-only cloud artifacts, retention
until explicit deletion. Existing CLI format/export behavior is unchanged.

## Deliverables

- Independent Python backend and lockfile; no backend dependencies in the CLI.
- Versioned API contract, projects and runs, user-scoped history and downloads.
- Presigned immutable S3 upload, SHA-256 verification, idempotent completion.
- Recoverable deletion and scheduled cleanup of abandoned uploads.
- SAM infrastructure: Cognito, HTTP API, Lambda, private S3, DynamoDB and IAM.
- Local integration tests, deployment/smoke instructions and backend-only CI.

## Security and consistency decisions

- Trust API Gateway's validated Cognito JWT claims, never a submitted owner ID.
- Ownership is part of every database key. No client-specified bucket/object key.
- Client run UUID is the idempotency key; a changed request under the same ID conflicts.
- Cloud stores the full native JSON report. Local SARIF remains a CLI concern.
- Upload URLs bind content length, type, SHA-256 and If-None-Match; completed
  objects cannot be replaced. Server verifies S3 metadata before publishing history.
- Pending runs expire after seven days. Cleanup first claims deletion conditionally,
  then deletes S3, and leaves a tombstone until every issued upload URL has expired.
  This prevents a delayed upload from recreating an untracked object after deletion.
- Generation-specific object keys and conditional revisions prevent old workers
  from modifying a new registration that reuses an already deleted run UUID.
- Stream-validate the native JSON envelope before retaining/publishing a report.
  Staging tags and S3 lifecycle also clean late-finishing abandoned PUT requests.
- Ready runs have no TTL. Removing infrastructure retains user data by default.
- Backend deployment creates shared resources once, never per user/project.

## Ordered checklist

- [x] 1. Contract, validation and user-scoped projects with integration tests.
- [x] 2. Idempotent run registration, constrained upload and completion.
- [x] 3. History, download, deletion and cleanup with failure/race tests.
- [x] 4. Cognito/SAM resources, least-privilege policies and template validation.
- [x] 5. API contract export, backend CI, deployment documentation and smoke tool.
- [x] 6. Full local checks, dependency audit, regression and implementation evidence.
- [x] 7. Confirm target AWS account, deploy dev and verify the real AWS service.

User authorized the existing AWS account on 2026-10-21 and requested deployment
tags for later cleanup. Dev is deployed in account 695650811791, ap-southeast-1,
using stacks infralens-dev and infralens-dev-artifacts. Live tag inventory and
real-service verification are in infra/deployments/. CLI integration/dashboard
remain outside this backend implementation scope.

Cloud provisioning is separate from implementing the backend. Build and validate
the complete deployable result before any deployment approval is needed.
