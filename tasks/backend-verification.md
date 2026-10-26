# Backend verification

## Implemented scope

Backend only: user-private Cognito-authenticated projects/runs, native JSON storage,
idempotent registration/completion, ready-only history, download, recoverable
deletion/cleanup, SAM infrastructure and OpenAPI. CLI cloud commands and dashboard
remain separate integrations as agreed. No existing scanner code was changed.

## Local evidence (2026-10-21)

- Linux/WSL, backend Python 3.12.13, SAM CLI 1.169.0, uv 0.11.6.
- `uv run --project backend pytest -q backend/tests`: **72 passed**.
- `uv run --locked pytest -q`: **176 passed, 1 Windows-only skipped, 12 integration/
  Docker tests deselected**. Existing scanner regression suite remains green.
- Ruff check and format check pass for backend and repository.
- OpenAPI 3.1 validated, request/response contract checked by API integration tests,
  generated contract and hashed runtime requirements match their sources.
- `cfn-lint infra/template.yaml` and `sam validate --lint` pass.
- Offline SAM transformation for both dev/prod verifies all 10 rendered HTTP
  routes, JWT scope requirements, only-config public access, payload format 2.0,
  merged Lambda logging/environment and absence of function URLs/VPC/provisioned
  concurrency. Verification blocks AWS client creation and uses a static managed
  policy map. The same check is part of backend CI.
- `sam build` succeeds for API and cleanup Lambda. Source bytes match both built
  artifacts. Each handler executes from its built artifact using Python `-S`,
  with no development site-packages; public config and unauthorized request checked.
- Backend wheel and sdist build successfully under `backend/dist/`.
- Audit of the complete locked backend runtime/dev export: no known vulnerabilities.
- Actionlint 1.7.12 accepts backend workflow. Tool archive verified against official
  release checksums before execution.
- Mutation experiment: removing client-ID authorization check causes the malformed
  identity test group to fail. Source restored byte-for-byte afterward; focused
  authorization tests rerun on original source.
- Actual Trivy 0.76.0 scan of `tests/fixtures/unsafe` exported **16,022-byte JSON**,
  accepted by the streamed native-envelope validator and metadata validator. Counts:
  3 findings, HIGH=1, LOW=2. Only public fixture source was scanned.
- Streaming parser stress check: **52,410,032 bytes**, **4.08 seconds**, peak RSS
  **38.7 MiB** for the standalone parser process. This does not measure a deployed
  Lambda or include the entire SDK process overhead.

## Review and regression cases

Independent read-only review found and the implementation/tests resolved:

- Upload renewal is capped at the fixed pending deadline, including advertised expiry.
- Concurrent completions return the same ready record when one conditional write wins.
- Checksum-valid non-JSON or invalid native envelopes never become ready.
- Generation-scoped S3 keys and revision+generation conditions isolate old workers
  from a new registration reusing the same run UUID after deletion.
- Stale GSI entries must match the current generation and index keys, preventing
  wrong-project/date history or duplicate results after UUID reuse.

Other covered behavior: cross-user denial, forged cursors, UTF-8/base64 input,
duplicate/oversized/malformed JSON, filtered-versus-total counts, protected upload
headers, missing/mismatched objects, late uploads, partial dependency failure,
scheduled retry, deletion/completion races, browser callback state and PKCE.

## AWS verification (2026-10-21)

User authorized the existing AWS account and requested tags for cleanup. Deployed
`infralens-dev` and `infralens-dev-artifacts` to account **695650811791**, profile
`default`, region **ap-southeast-1**. Both stacks completed successfully. API:
`https://8maelv4bic.execute-api.ap-southeast-1.amazonaws.com`.

- Four common tags on both stacks and all **13 taggable resources** verified using
  each service's live tag API: Project=infralens, Environment=dev,
  ManagedBy=cloudformation, Deployment=infralens-dev.
- All **29 resources** (including children without tag support) recorded in
  `infra/deployments/infralens-dev.json`. Cleanup and Retain/deletion-protection
  instructions are in `infra/README.md`; the artifact bucket uses its own tagged
  stack, not an untracked SAM managed default bucket.
- Both Lambda functions Active; API config 200 and missing access token 401.
- Cognito hosted sign-in form, cookie/CSRF flow, PKCE exchange and localhost callback
  tested against the real service with two temporary users. The existing browser
  smoke login function was driven by an isolated HTTP form client; browser rendering
  and dashboard UI are outside this backend verification. Tokens stayed in memory.
- Missing JWT, forged signature and ID token rejected at the API boundary.
- Native Trivy fixture report uploaded directly through the signed URL. Wrong
  checksum rejected; correct PUT succeeded; overwrite returned 412. Registration
  retry, completion retry, history and byte-identical download passed.
- User B could not read user A's project/run, complete it, download it or delete it,
  for both pending and ready runs. User B's project/history lists remained empty.
- Missing S3 object and checksum-valid JSON with an invalid native envelope were
  rejected and never published as ready.
- The deployed cleanup Lambda deleted an expired-pending fixture from DynamoDB
  and S3. Verified enabled hourly EventBridge schedule, Lambda invoke permission,
  bucket public-access blocking and seven-day pending-object lifecycle.
- Refresh token exchange succeeded; the same refresh token was rejected after
  revocation. Temporary Cognito users and project items were removed without email
  invitations. Deleted runs retain safety tombstones until signed URLs expire;
  the scheduled worker then removes them. All test report objects were removed.
- Live verification results: `infra/deployments/infralens-dev-verification.json`.

Real-AWS testing found global S3 endpoint URLs returning 307 for a new regional
bucket. Lambda now signs regional virtual-host URLs. Regression tests fail before
the fix and pass afterward for PUT/GET in Singapore and us-east-1. Account Lambda
quota is 10: dev uses shared concurrency, with optional reservation only when the
account has sufficient quota. API throttling remains unchanged.

Review also found missing S3 tags raise NoSuchTagSet; inventory now records an
empty tag set so it can save the cleanup inventory and report missing tags.
Regression tests distinguish this from AccessDenied, which still surfaces.

GitHub workflow is present but has not been pushed or executed remotely. No commits,
pushes or messages to other people were performed. CLI cloud commands and dashboard
are still separate integrations; this deployment does not enable them.
