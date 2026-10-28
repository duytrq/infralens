# Default AWS SDK dependency

Verified 2026-10-28 on Linux/WSL.

- `boto3>=1.40,<2` is a runtime dependency; the duplicate development dependency
  was removed. Existing locked dependency versions are unchanged. `aws-trace=[]`
  remains for compatibility with old install/sync commands.
- A fresh `uv sync --locked --no-dev` environment installs boto3/botocore without
  extras. The offline CloudTrail demo succeeds from outside the checkout; SDK calls
  use synthetic identities/events and Stubber, with no AWS network requests.
- The Linux bundled wheel metadata has an unconditional boto3 requirement.
  Normal installation (no SDK extra/`--with boto3`) passes the offline trace demo
  with two matched resources, scanner/Drift/upload regressions and 10 process/I/O tests.
- CLI suite: 626 passed, 2 existing Windows-only skips, 17 external-tool tests
  deselected. Updated SDK-missing recovery tests also passed after the message change.
  Ruff lint/format and updated guide links/fences passed.
- SDK-missing errors now request reinstallation rather than an optional extra.
  User installation instructions no longer require installing boto3 separately.

Current local wheel: `dist/infralens-0.1.0-py3-none-linux_x86_64.whl`, 51,493,242 bytes.
SHA-256: `44f0489a426838cdadf5abeee0ba2646a66f1c5296f7922294e48de6c3c59e38`.
This replaces the previous same-named local artifact. The checkout and packaged
CloudTrail source match; a companion `.whl.sha256` is available.

No AWS deployment or live CloudTrail lookup was performed. Windows runtime and
Docker image verification were not run here; wheel verification is wired into the
existing Linux/Windows CI matrix. No PyPI/registry release was published.
