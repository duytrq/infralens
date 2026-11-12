# Frontend verification

The approved frontend/deployment scope is complete. The dev dashboard is live at
**https://ddsw2osqv2rj2.cloudfront.net** using the simplified sign-in screen requested
by the user. Localhost:5173 remains registered and tested.

## Deployed state

- Account: `695650811791`; application region: `ap-southeast-1`.
- Frontend stack: `infralens-dev-frontend`, CREATE_COMPLETE.
- CloudFront: `E3L2AM9X65Z1OP`, Deployed, default HTTPS certificate and OAC.
- Frontend bucket: `infralens-dev-frontend-frontendbucket-vhzky2sdozev`, private.
- Backend stack: `infralens-dev`, UPDATE_COMPLETE. Primary DashboardOrigin is the
  CloudFront origin; EnableLocalDashboard=true retains localhost callbacks/CORS.
- Active release: `20261023T092153Z-1539682b62c4`; archived previous release:
  `20261023T091810Z-1539682b62c4`. Archives/manifests live in the existing artifacts
  bucket. SHA-256 covers the bundle and every published file.
- The previous AWS account-verification block was resolved. Its failed stack and
  verified empty retained bucket were removed before recreating the same stack.
  Original events/resources are preserved in the before-retry evidence.

## Runtime acceptance evidence

- [Final deployment state](../infra/deployments/infralens-dev-frontend-verification.json):
  actual stack states, HTTP-to-HTTPS 301, Cognito callbacks/logout URLs, zero
  remaining ephemeral smoke users and monitoring results.
- [CDN checks](../infra/deployments/infralens-dev-frontend-cdn-verification.json):
  root and five deep links return the selected HTML; HTML is no-store; three
  hashed assets use one-year immutable cache and match archived checksums.
  CSP, HSTS, nosniff, frame denial and no-referrer headers were checked on AWS.
  Missing assets return errors rather than HTML; anonymous S3 access returns 403.
  Exact CORS permits CloudFront/localhost and denies an untrusted origin. CLI client
  and loopback callback remain intact.
- [Real browser smoke](../infra/deployments/infralens-dev-frontend-browser-verification.json):
  twelve checks across CloudFront and localhost, covering Cognito PKCE login,
  streamed report indexing, project/history/finding detail and reloads,
  byte-identical JSON download, two-user ownership isolation, retry, deletion and
  refresh-token revocation. Temporary accounts/projects were removed; run
  tombstones/derived data use protected scheduled cleanup.
- [Real rollback](../infra/deployments/infralens-dev-frontend-rollback-verification.json):
  published two releases, rolled back to the first, verified its HTML SHA-256
  through CloudFront, restored the latest and verified its SHA-256. Previous
  hashed assets remain present with matching content.
- [Demo account verification](../infra/deployments/infralens-dev-frontend-demo-verification.json):
  `demo@infralens.test` signs in on CloudFront and sees its two projects, with zero
  browser console/JavaScript issues or Axe violations. This account is retained
  for the user. Credentials are kept outside the repository in a private 0600 file
  and were supplied directly to the user. It has no IAM/admin access.
- [Inventory](../infra/deployments/infralens-dev.json): three stacks, tags checked
  on 21 supported resources, with unsupported-tag resources explicitly recorded.
- Monitoring: API/analysis Lambda Errors sum 0 across available datapoints and
  CloudFront maximum 5xxErrorRate 0 for the last 20 minutes. Cleanup had no datapoints
  in that window; no zero-error inference is made for it.

## Local and build checks

- Node 22.22.2/npm 10.9.7; clean frozen installs with lifecycle scripts disabled.
- Generated OpenAPI types, ESLint and TypeScript checks passed.
- Vitest: 11 passed (API boundaries, origin/redirect safety, polling, references and
  execution of the actual CloudFront rewrite source).
- Playwright Chromium: 27 passed during both publication gates. Covers projects,
  history, filters/cursors, source excerpts, count mismatch/truncation, pending/
  failed analysis, retries, downloads, 202/204 deletion, auth failures/renewal,
  failed revocation and hiding cached data after deletion.
- Axe/responsive checks passed on login/projects/scan/finding screens at tested
  widths 320/768/1024/1440px, including keyboard/modal focus and table overflow.
- Production bundle approximately 414kB JavaScript /125kB gzip and 18kB CSS /4kB gzip.
- npm audit: 0 vulnerabilities. No skipped quality gates or added test suppressions.
- Backend 128 tests passed in implementation; the 18 focused infrastructure/release
  tests and cfn-lint passed again before this deployment. No backend application
  code changed during this retry.
- CLI regression 176 passed, one existing platform skip, 12 optional integration/
  Docker/network cases deselected; scanner behavior is unchanged.
- Ruff, OpenAPI, all three CloudFormation templates, offline SAM dev/prod transform
  and independent built Lambda artifact checks passed during implementation.
- Mutation check: changing dev-only origin registration to prod-only made tests
  fail; original source was restored.

## Resolved review findings

Explicit OIDC nonce; safe source text/references; bounded polling/retries;
account-isolated cache; multiple source lines laid out vertically; accessible
contrast/landmarks/focus; clearing expired sessions; hosted logout despite
revocation network failure; hiding externally deleted cached scans; correct
CloudFront function ARN inventory; identity/integrity checks before rollback;
resuming confirmed live stack operations instead of duplicate creation.

## Operations

Use infra/FRONTEND.md for publish/rollback/cleanup commands and metric locations.
CloudFront access logging remains off to avoid retaining OAuth callback query
parameters. App code does not log auth material, source reports or signed URLs.
Frontend writes preserve previous hashed assets; HTML is uploaded last.

All requested deployment work is verified. CI configuration was validated locally;
the runtime evidence above records the deployment checks rather than a GitHub
Actions run.

## Pre-commit verification (2026-10-26)

At the user's request, reviewed the pending backend, frontend, infrastructure and
documentation changes on `feature/frontend` before committing and pushing.

- Backend: all 128 tests passed; Ruff lint/format, exported OpenAPI and cfn-lint
  checks passed for all three templates.
- Frontend: all 11 unit tests and 27 Playwright Chromium tests passed, including
  accessibility and responsive layout checks. ESLint, TypeScript, generated
  contract types and production build passed.
- npm audit found zero vulnerabilities. The pending files were checked for
  credentials, signed URLs and private keys; none were found. Local environment,
  verification screenshots, dependencies and build output remain ignored.
- The localhost/browser tests required running outside the restricted sandbox;
  the first sandbox failures were permission errors and passed on the rerun.
- Fetched `origin` and confirmed the branch had no divergence before committing.
  Historical planning and deployment evidence are included alongside the feature.
