# Repo project binding only — 2026-10-29

At the user's request, removed --local and machine-wide selected projects.
Setup and project use/create bind API/project to .infralens.toml automatically.
When called below an existing binding, update that binding instead of writing
another nested config. No repo binding and no explicit flag/env project fails
upload validation before the engine runs. Local scans stay offline.

Machine config v2 stores only API URL; legacy v1 API is readable, but project_id
is discarded. Configure rewrites the file to v2. Existing sessions are unchanged.
Explicit --project/INFRALENS_PROJECT remain per-run choices for CI, never stored
as a global default. Repo project is only reused for its matching API.

- 684 CLI tests passed; 2 existing Windows-only skips, 17 opt-in deselected.
- 27 focused config/setup tests passed after final help/status text changes.
- Ruff lint/format and frontend ESLint passed.
- 26 real AWS/browser checks passed using an isolated copied Terraform fixture:
  CLI project binding, PKCE session/refresh/logout, upload, indexing and dashboard.
  Temporary users/projects were removed. See the machine evidence under
  infra/deployments/infralens-dev-repo-project-browser-verification.json.
- Both platform wheels rebuilt and all 28 Python sources match the checkout.
- Linux installed-wheel verifier covers minimal repo-based upload/report retention,
  JSON/SARIF, default SDK, bundled scanner integrity and process/atomic-I/O tests.
- Windows wheel was rebuilt and source-checked; native Windows tests were not
  rerun for this change. Earlier Windows/ACL evidence is in cli-workflow-verification.md.

Current local development artifacts (replace earlier same-named snapshots):

- `infralens-0.1.0-py3-none-linux_x86_64.whl`: 51,504,149 bytes; SHA-256 `e7d983cbbcc56f8bd738401d4ff65eaf59344deb9fba21616203184393324d97`.
- `infralens-0.1.0-py3-none-win_amd64.whl`: 52,485,472 bytes; SHA-256 `435c536768888ea63df4be4a34c6b3d51d1dbcb4fab2498a93ea71f9e17d154d`.
