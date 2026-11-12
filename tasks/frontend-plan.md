# Frontend implementation contract

Approved: React/Vite/TypeScript, English internal dashboard, complete existing
dashboard API capabilities, private S3 + CloudFront/OAC, AWS-provided hostname,
dev deployment through the operator's AWS profile. Localhost login remains usable.
No browser upload, production environment, full-text search or scan comparison.

## Architecture and design

- `frontend/`: React Router, TanStack Query, oidc-client-ts, generated OpenAPI types,
  CSS Modules, Vitest/Testing Library and Playwright browser verification.
- Content-first light interface: compact dark navigation, slate typography, teal
  actions, semantic severity badges with text, tables and readable source excerpts.
  References are unavailable locally; these explicit design defaults implement
  the approved dashboard direction. No marketing hero or decorative card grid.
- Routes: `/`, `/auth/callback`, `/projects`, `/projects/:projectId`,
  `/runs/:runId`, `/runs/:runId/findings/:findingId`.
- Access tokens and refresh tokens in sessionStorage, PKCE/state/nonce, bounded
  polling/retries, account-isolated query cache, report content rendered as text.
- Separate upload/analysis/threshold states. Cursor-based pagination, including
  empty pages with a next cursor; exact filters in URL; downloads via navigation.
- Add dashboard allowed origins to config and localhost CORS/callbacks only when
  explicitly enabled in dev. Preserve CLI auth and existing report storage.
- Separate frontend CloudFormation stack, REST S3 origin/OAC, HTTPS, route rewrite,
  immutable hashed assets, uncached HTML, CSP and public deployment outputs.
- CI validates/builds without AWS credentials. Manual deploy verifies AWS account,
  prepares hosting, updates backend origin, uploads assets before HTML, saves a
  release archive and supports rollback without deleting previous hashed assets.

## Verification

Backend regressions/contract/SAM checks; meaningful frontend unit/integration
tests; browser journeys with mocked APIs; keyboard/responsive/accessibility and
screenshots; real AWS login/CORS/download/ownership/cache/deep-link smoke;
rollback exercise and updated resource inventory. Evidence in frontend verification.

## Commands

Use `rtk` for shell commands. Frontend scripts: `npm ci`, `npm run lint`,
`npm run typecheck`, `npm test`, `npm run test:e2e`, `npm run build`,
`npm run generate:check`. Backend commands follow backend/README.md.
