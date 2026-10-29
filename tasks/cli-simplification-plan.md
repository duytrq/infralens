# Simplify Drift CLI

Approved interface: one --fail-on ANY|MEDIUM|HIGH|UNKNOWN (comma-separated OR);
MEDIUM includes HIGH, UNKNOWN is independent. Omitted gate keeps exit 0 for drift.
--trace DAYS enables CloudTrail with an explicit integer 1–90; omitted trace is off.
Remove public --fail-on-drift, --fail-on-priority, --fail-on-unknown, --lookback-days.
Keep the existing structured report/upload gate and trace contracts.

- [x] Regression tests for gate syntax, thresholds, unknown, invalid input and trace days.
- [x] Replace public flags and validation; preserve shared collection/report models.
- [x] Migrate current tests, examples, help and guide; document old-to-new commands.
- [ ] Full checks, packaged CLI verification, local reinstall and live trace check.
