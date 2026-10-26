import { describe, expect, it } from "vitest";
import { valueText, effectivePriority } from "./drift-state";
import type { DriftResource, DriftRun } from "../api/types";
import { analysisPolling } from "./scan-state";

describe("drift presentation", () => {
  it("distinguishes unknown, sensitive, absent, null and string values", () => {
    expect(valueText({ status: "known", value: null })).toBe("null");
    expect(valueText({ status: "known", value: "null" })).toBe('"null"');
    for (const status of ["sensitive", "unknown", "absent"] as const)
      expect(valueText({ status })).toBe(`[${status}]`);
  });
  it("does not treat unrecognized review policies as assessed risk", () => {
    const resource: DriftResource = {
      address: "aws_instance.demo",
      resource_type: "aws_instance",
      actions: ["update"],
      attributes: [],
      identifiers: {},
      assessment: {
        policy: "future-policy",
        priority: "medium",
        signals: [],
        guidance: { choices: [], review_steps: [] },
      },
    };
    expect(effectivePriority(resource)).toBe("unknown");
  });
  it("polls pending uploads with bounded backoff and stops when ready or expired", () => {
    const now = Date.parse("2026-10-26T00:00:00Z");
    const run = {
      run_type: "drift",
      upload_status: "pending",
      received_at: new Date(now).toISOString(),
    } as DriftRun;
    expect(analysisPolling(run, 0, now)).toBe(5000);
    expect(analysisPolling(run, 5, now)).toBe(30000);
    expect(analysisPolling(run, 0, now + 20 * 60_000)).toBe(false);
    expect(analysisPolling({ ...run, upload_status: "ready" }, 0, now)).toBe(
      false,
    );
  });
});
