# API-key-only CLI authentication verification

## Implemented behavior

- `cloud login` prompts for a hidden dashboard-issued key, verifies the entered
  key with `/v1/cli/projects?limit=1`, then saves it. Verification or cancellation
  preserves the previous credential. Environment keys retain priority.
- `cloud logout` removes the selected origin's saved key and legacy Cognito
  session locally. Revocation remains in the dashboard; environment keys persist.
- Ordinary commands require an environment/saved key without prompting. Guided
  setup can prompt for a missing key before project selection.
- Credential reads/status do not create storage or modify permissions. Writers
  serialize atomic replacement; private temporary-file ACLs precede secret writes.
- API-scoped saved-key paths remain compatible. Symlinks/unsafe permissions are
  rejected; concurrent logout is treated as a missing credential.
- CLI OAuth/session code and `cloud api-key` subcommands are removed. Server
  CLI Cognito client, callback, settings, `/v1/config`, contract and generated
  frontend types are removed. Dashboard Cognito and its response shape remain.
- Backfill, backend smoke, browser/CLI smoke and installed-wheel checks migrated.

## Verification (2026-11-03)

- Final CLI suite: 750 passed, 2 skipped, 17 deselected by existing integration
  gates, including guided setup with missing-key login.
- Backend full suite: 165 passed, including rejection of the old CLI JWT client
  and the backfill entrypoint regression.
- Frontend: 14 unit tests; typecheck, lint, production build, generated-type check;
  Chromium API-key create/show-once/revoke test passed.
- Ruff checks and formatting, exported OpenAPI check, cfn-lint and offline SAM
  transform verification pass. Dev/prod each expose 32 matching contract routes.
- SAM build succeeded; isolated runtime verification passed for API, cleanup,
  analysis and API-key-authorizer artifacts.
- Linux bundled wheel built and passed isolated install verification (including
  scanner execution without PATH Trivy, cloud failures, and 10 lifecycle/I/O tests).
- Exact smoke login helper passed an offline delayed getpass prompt check using
  a controlling PTY. Input is sent after the hidden prompt and never logged.
- Independent review found ACL, concurrent-read, backfill and PTY issues; fixes
  are covered and the final review found no remaining issue in those fixes.

## Release boundary

At implementation time, no AWS deployment or live AWS smoke was performed.
The subsequent dev deployment is recorded below. Native Windows runtime checks
remain a CI responsibility; ACL branches have deterministic unit coverage here.
Publish/upgrade the API-key CLI and migrate CI secrets first; then deploy removal
of server-side CLI Cognito support. Existing dashboard accounts/data and saved
API keys remain usable; old CLI Cognito sessions/access-token scripts do not.


## AWS dev deployment (2026-11-03)

- Stack `infralens-dev` updated successfully using reviewed CloudFormation changeset.
- Deleted the obsolete CLI Cognito client and `/v1/config`; 32 API routes remain.
- Dashboard client/User Pool and all storage physical IDs are unchanged.
- Live CloudFront and localhost smoke passed 26 checks, including actual CLI
  login, project operations, Trivy security upload, dashboard indexing/download,
  local logout and API-key revocation. Temporary accounts/projects were removed;
  run deletion uses the existing scheduled cleanup.
- API Gateway metrics showed zero 5xx across 55 requests in the sampled window.
- Corrected smoke helper timing: Click prints its caption before getpass disables
  echo/flushes input. Wait for the terminal ECHO flag before sending the key.
  Regression test and all 15 frontend tests, lint and typecheck pass.
- Evidence: [AWS cleanup verification](../infra/deployments/infralens-dev-api-key-cleanup-verification.json).
