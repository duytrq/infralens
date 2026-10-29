# Frontend operations

Published dev dashboard: **https://ddsw2osqv2rj2.cloudfront.net**.
Security and Drift are published together as release
`20261027T100344Z-d9e3b434ac36` (2026-10-27). Real Cognito/API/S3 browser smoke
passed on CloudFront and localhost; see the
[Drift rollout evidence](../tasks/drift-integration-verification.md#dev-deployment-2026-10-27).
Distribution `E3L2AM9X65Z1OP`; bucket
`infralens-dev-frontend-frontendbucket-vhzky2sdozev` remains private.
Real browser smoke, CDN cache/security checks and release rollback have passed;
see [verification](../tasks/frontend-verification.md).

The `infralens-dev-frontend` stack serves the dashboard using CloudFront's default
HTTPS hostname, OAC and a private S3 REST origin in ap-southeast-1. It is separate
from `infralens-dev` (backend) and `infralens-dev-artifacts` (release/code archives).
All three share `Deployment=infralens-dev`; no report is stored in the frontend
bucket. The operator workflow refuses production stacks or a mismatched account.

## Prepare and publish dev

Run from repository root after the backend dependencies and frontend browser
dependencies have been installed. AWS profile `default` must identify the intended
operator. Each command verifies account 695650811791 before mutation.

```bash
backend/.venv/bin/python infra/frontend_release.py prepare --account 695650811791
backend/.venv/bin/python infra/frontend_release.py configure-backend --account 695650811791
backend/.venv/bin/python infra/frontend_release.py publish --account 695650811791
```

`prepare` reads backend outputs to constrain CSP and creates/updates the frontend
stack. It reports the stack state while CloudFront is deploying. If interrupted,
inspect CloudFormation's current state before repeating the command.

`configure-backend` builds using the pinned SAM CLI, then deploys to the existing
backend stack using its existing artifacts bucket, tags and parameter values.
Only DashboardOrigin and EnableLocalDashboard are selected for the dashboard;
the new application code adds the allowed-origins config field. CLI client/callback
and all retained reports/tables/user pools are preserved.

`publish` verifies the live dashboard config, performs a frozen install with
dependency scripts disabled, checks generated types, lint, types, unit tests,
browser E2E, dependency audit and build. It uses the API endpoint from stack
outputs rather than accepting an arbitrary destination. Failed checks stop upload.
Run publishes serially; the workflow is for one operator, not concurrent CI jobs.

When CloudFront creation is blocked by AWS account verification, the frontend
stack can end in ROLLBACK_COMPLETE while retaining an empty private bucket.
`prepare` refuses to overwrite that state. Preserve the failure events and
inventory, have AWS Support enable CloudFront, then deliberately delete the failed
stack before re-running prepare. The retained bucket is recorded separately and
must be checked and explicitly cleaned up; it is not reused or silently deleted.
To deploy additive backend changes while this is pending, preserve its current
primary origin:

```bash
backend/.venv/bin/python infra/frontend_release.py configure-backend --keep-origin --account 695650811791
```

This permits localhost verification but does not complete the CloudFront rollout.

The artifacts bucket stores `frontend-releases/<stack>/<release>/bundle.tar.gz`
and a manifest with account, region, stack names, API/frontend origins, git
revision/dirty marker and SHA-256 for the archive and every file. Release IDs also
appear in an HTML meta tag. Build artifacts contain public configuration only.

Upload writes assets first and HTML last. HTML uses `no-store` and an uncached
CloudFront behavior; hashed assets use one-year immutable caching. Old assets
remain available to open tabs. A successful HTML read-back advances `current.json`.
No whole-bucket deletion or blanket CDN error-to-HTML mapping is used.

## Rollback

```bash
backend/.venv/bin/python infra/frontend_release.py rollback --account 695650811791
# Or select an archived release explicitly:
backend/.venv/bin/python infra/frontend_release.py rollback --account 695650811791 --release RELEASE_ID
```

The default is `previous_release` from the current manifest. Rollback checks
deployment identity and all checksums before writing. It rejects traversal, links,
unexpected files and oversized archives without extracting them to the filesystem.
Assets are restored first and HTML last. This rolls back frontend code only;
an API contract change needs a separately reviewed backend rollback.

## Post-deploy checks

- Open CloudFront root, project/history/scan/finding deep links and callback.
- Sign in/out on both CloudFront and localhost:5173. Confirm an unregistered
  origin receives no CORS permission and another account cannot access the run.
- Confirm direct S3 GET is denied; missing assets return 403/404, not HTML.
- Check CSP, HSTS, nosniff, Referrer-Policy, HTML no-store and asset immutable cache.
- Exercise JSON download, analysis retry and scan deletion on a test account.
- Publish a second release and exercise rollback; verify the selected HTML hash.
- Refresh inventory and record evidence, excluding passwords/tokens/signed URLs.

The repeatable browser/API smoke creates two temporary users with invitations
suppressed, sends their credentials only through stdin to an isolated Chromium
process, and removes their accounts/project rows afterward. Run tombstones are
left for the backend's protected cleanup. Use `--local-only` while hosting is
blocked; omit it to exercise both CloudFront and localhost after publication:

```bash
backend/.venv/bin/python infra/frontend_smoke.py --account 695650811791 --local-only \
  --output infra/deployments/infralens-dev-frontend-local-verification.json
```

To include CLI API configuration, project create/list/use and a real Security
scan/upload using the saved defaults, supply the installed CLI executable. Trivy
0.76.x must be available for the scan (or bundled in that CLI). The checks also
verify the threshold gate, indexing, source display and downloaded bytes:

```bash
backend/.venv/bin/python infra/frontend_smoke.py --account 695650811791 \
  --security-cli /absolute/path/to/infralens \
  --output infra/deployments/infralens-dev-security-upload-browser-verification.json
```

The CLI signs in through its own real browser PKCE callback and saves its session
in an isolated temporary directory. The smoke forces access-token expiry, checks
refresh across separate commands, then verifies logout rejects future refreshes.
Config/reports stay isolated, no upload sidecar is created, and temporary users,
projects and files are removed after verification. This CLI PTY smoke runs on POSIX;
native Windows storage/headless behavior is covered by CLI and wheel tests.

```bash
backend/.venv/bin/python infra/inventory.py \
  --account 695650811791 --region ap-southeast-1 \
  --stack infralens-dev infralens-dev-artifacts infralens-dev-frontend \
  --output infra/deployments/infralens-dev.json
```

## Monitoring and cleanup

Monitor CloudFront Requests/4xxErrorRate/5xxErrorRate in AWS/CloudFront
(region us-east-1, Region=Global), plus the existing API Gateway/Lambda metrics in
ap-southeast-1. CloudFront access logging is off to avoid retaining OAuth callback
query parameters. Application code does not log report content or auth material.
Use browser console/network and backend safe error codes to investigate failures.

Rollback if sign-in, API access, source rendering or asset loading breaks; preserve
the archived release and deployment evidence. No production rollout is included.

For deliberate teardown: export inventory, disable/delete the distribution through
CloudFormation, then explicitly empty and delete the retained frontend bucket.
CloudFront policies/function/OAC are stack-managed. Release archives remain in the
retained artifacts bucket and require separate deliberate retention management.
