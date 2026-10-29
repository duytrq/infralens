# CLI workflow verification — 2026-10-29

## Delivered behavior and evidence

| Requirement | Evidence |
| --- | --- |
| Login once, refresh, logout, local status | `test_cloud_session.py`, real CLI PKCE/refresh/revoke AWS browser smoke |
| Private session files, separate API identities, no credentials in repo | POSIX permission checks; native Windows protected DACL/one-user ACE assertion; cross-API tests |
| Concurrent refresh and logout serialization | Two real Python processes refresh exactly once; session writes use OS locks and atomic publication |
| Preserve session on network failure and old session on failed login | Refresh failure test; sign-in publishes only after validated successful exchange |
| Guided setup, project picker/create, rerun/cancel | `test_cloud_workflow.py`, original project API contract/ownership tests |
| Repo discovery from scan input, stop at Git root, env/flag precedence | `test_repo_config.py`, mutation experiment rejects cross-API project reuse |
| Default input '.', JSON/output for upload, unique report filenames | Both-engine workflow tests and installed-wheel minimal upload preservation |
| Destination, gate, upload status; retained report on failure | Real Trivy tests, both installed-wheel verifiers, shared upload failure/gate regression |
| Headless/CI never opens browser | Real subprocess with DEVNULL, native Windows NUL regression, both verifiers |
| Existing commands, colors, machine output, process and atomic I/O | Full CLI regression; Windows native runtime/reporting suite; both artifact verifiers |

## Results

- Linux/WSL Python 3.10: **679 passed**, 2 existing Windows-specific skips,
  17 opt-in integration tests deselected. Final setup-default edit additionally
  passed the relevant 23 workflow/session/repo tests; the final 11-session-test
  run also proves cancelled login preserves the existing session byte-for-byte.
- Real Trivy 0.76.0 including network module cases: **10 passed**.
- Native Windows Python 3.12.13: **106 passed**, 1 POSIX-mode-only test skipped.
  Ran session/ACL/concurrency, repo/workflow, project config, reporting, common
  flags and runtime tests against the editable source in an isolated NTFS workspace.
- Native Windows and Linux installed-wheel verifiers both passed with no Trivy
  on PATH, including **10 process/atomic-I/O checks each**, native JSON/SARIF,
  default boto3 tracing, integrity checks, and minimal repo-config upload that
  retains an automatically named JSON after noninteractive auth failure.
- Windows NUL input originally passed isatty and attempted browser login. Fixed
  by requiring GetConsoleMode to identify real interactive console input, then
  reran native Windows tests and both final wheel verifiers successfully.
- AWS/Cognito real-browser smoke: **26 checks passed** across CloudFront and
  localhost. CLI's own PKCE browser callback saved a session; forcing expiry
  triggered real OAuth refresh across separate project/upload commands. Logout
  removed local auth and Cognito rejected the revoked refresh token.
  [Machine evidence](../infra/deployments/infralens-dev-cli-workflow-browser-verification.json).
- Temporary smoke users removed: 2; project rows removed: 4. Run tombstones use
  existing protected backend cleanup. No invitations sent or real user credentials saved.
- Ruff lint/format and frontend ESLint passed. Locked production pip-audit found
  no known vulnerabilities. tomli is needed only for Python below 3.11.

## Artifacts

Both final wheels matched all **28 Python source files** byte-for-byte. SHA-256
sidecars exist next to the ignored local dist artifacts:

- `dist/infralens-0.1.0-py3-none-linux_x86_64.whl`: 51,504,148 bytes; SHA-256 `3b94f3522b7246ab7da5aa1e7526ab9e071f270bc44982d3c12746e450a052e9`.
- `dist/infralens-0.1.0-py3-none-win_amd64.whl`: 52,485,472 bytes; SHA-256 `2cf2e812ad1e9286f8fe89b709ab4560e6ad87eb10b0dccd3269bd791fc84455`.

These replace earlier local artifacts of the same unpublished 0.1.0 filenames.
The final Linux wheel was reinstalled into the user's existing uv tool CLI.
The existing dev API configuration was preserved; no temporary project/session
was selected for the user's account. The sample README outside the repo was updated.

No API key system, upload retries, backend API changes, backend/dashboard redeploy,
PyPI release, Git push, or credentials committed. CI on a clean runner still needs
an externally supplied access token (15-minute lifetime); no new long-lived CI
credential issuer was added. Cognito refresh lifetime remains 30 days.

## Review

Reviewed input/config precedence, endpoint and client binding, token routing,
permissions/Windows ACLs, response validation, concurrent writes, error leakage,
CLI backward compatibility, and bounded prompts/network operations. Token refresh
and upload are separate; mutating upload HTTP calls are never automatically retried.
No remaining findings in the accepted scope.
