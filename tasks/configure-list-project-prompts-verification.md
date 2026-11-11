# Configure list and project prompts — 2026-10-29

- `cloud configure list` calls the same status implementation as `cloud status`:
  effective API, repo/project, source precedence and auth state, with no network
  access, refresh or token/password output.
- `cloud configure --api-url URL` remains supported. Combining setter flags with
  the list subcommand fails before mutation; missing API/list yields actionable help.
- `cloud project create` prompts for missing ID and display name on interactive
  terminals, using the same helper as setup. Explicit fields are not prompted again;
  Enter accepts the project ID as the displayed default name. Noninteractive mode
  requires both ID and --name and fails before project creation if either is absent.
- Full CLI suite: **691 passed**, 2 existing platform-specific skips, 17 opt-in
  integration tests deselected. After formatting, 14 prompt/setup tests passed.
- Mutation experiment replacing the missing-field OR with AND failed the regression
  suite, proving it catches omitted name/ID prompts. Restored source afterward.
- Ruff lint and formatting passed. Linux installed-wheel verifier passed, including
  the new configure-list alias and missing-name CI checks, native scanner formats,
  SDK support, report preservation and 10 process/atomic-I/O checks.
- Linux and Windows wheels rebuilt; all 28 Python source files match the checkout.
  Native Windows/browser/AWS were not rerun for this interface-only change.
- Final Linux wheel reinstalled in the existing user uv tool; configure list manually
  verified. API, repo and saved sessions were not modified by the inspection.

Current unpublished local artifacts replace older snapshots of the same filename:

- `infralens-0.1.0-py3-none-linux_x86_64.whl`: 51,504,450 bytes; SHA-256 `1a7a4c4f40342238ae6662f2dd22806f66924cfc7e27b22dcefb1749fd7fd95c`.
- `infralens-0.1.0-py3-none-win_amd64.whl`: 52,485,772 bytes; SHA-256 `9b3a8abab1bd46773e7963eb85d65cddb38e4e8dd30e193b415f15a75fddb882`.
