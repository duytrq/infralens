# Security terminal presentation

Verified 2026-10-29 on Linux/WSL.

- Removed the `Security scan (Trivy ...)` banner. Findings use separate cards with
  severity/rule, location/resource, description and native source excerpts.
- Severity badges and cause lines have distinct colors: critical white/red
  background, high red, medium yellow, low cyan and unknown magenta. Labels and
  `>` markers remain readable without color.
- Excerpts preserve indentation, show at most 9 source lines around the first
  cause and mark omitted content with `...`. Optional invalid/missing excerpts do
  not discard findings. The parser bounds code entries/content and never reads
  paths from a report. Native `Highlighted` text is ignored; controls are stripped.
- Colors are opt-in through stdout TTY detection; --no-color, nonempty NO_COLOR
  and TERM=dumb disable them. Table files are plain; JSON/SARIF and upload payloads
  do not receive presentation escape codes. Native report data is unchanged.

## Checks

- Initial tests reproduced the absent excerpts/colors and unwanted version banner.
- Full CLI: **646 passed**, 2 existing Windows-only skips, 17 opt-in tests deselected.
- Real Trivy 0.76.0: **10 passed**, including source cause lines and equality of
  finding IDs between terminal cards and JSON/SARIF exports.
- Real PTY scan of `/home/lozshi/uet/security-demo`: all **17 findings** remain,
  colored labels and 39 marked code lines. Five additional checks passed for
  --no-color, NO_COLOR, redirected output, JSON stdout on TTY, and colored terminal
  output with a clean JSON file. Preview: `security-demo/reports/terminal-preview.txt`.
- Installed Linux bundled wheel verified outside the checkout without PATH Trivy:
  source cards, scanner/Drift/SDK/upload regressions and 10 process/I/O tests passed.
- Ruff check/format and updated documentation links/fences passed.

## Artifact and limits

Current local artifact: `dist/infralens-0.1.0-py3-none-linux_x86_64.whl`,
51,494,739 bytes, SHA-256
`9a1fc112b08b6b6eb3b49916da2a2e6e4f29a5796b31a5d6bddf668859a8468f`.
Packaged sources match the checkout; `.whl.sha256` is available. This replaces
the previous same-named local artifact.

No backend/frontend deployment or live upload was needed for the presentation
change. Actual Windows console behavior was not run here; the existing Windows CI
matrix includes the portable parser/rendering/CLI and installed-wheel checks.
