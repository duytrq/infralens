import { describe, expect, it } from "vitest";
import { analysisPolling, safeReference } from "./scan-state";
import type { Run } from "../api/types";

describe("scan analysis state", () => {
  const now = Date.parse("2026-10-23T05:00:00Z");
  const scan = (status: "pending" | "ready" | "failed", requested = now) =>
    ({
      analysis: { status, requested_at: new Date(requested).toISOString() },
    }) as Run;
  it("backs off pending polling and stops for terminal or old work", () => {
    expect(
      [0, 1, 2, 10].map((attempt) =>
        analysisPolling(scan("pending"), attempt, now),
      ),
    ).toEqual([5000, 10000, 20000, 30000]);
    expect(analysisPolling(scan("failed"), 0, now)).toBe(false);
    expect(analysisPolling(scan("ready"), 0, now)).toBe(false);
    expect(analysisPolling(scan("pending", now - 20 * 60_000), 0, now)).toBe(
      false,
    );
    expect(analysisPolling(undefined, 0, now)).toBe(false);
  });
  it("allows only explicit HTTP(S) references, never relative or script URLs", () => {
    expect(safeReference("https://example.com/docs")).toBe(
      "https://example.com/docs",
    );
    for (const value of [
      "javascript:alert(1)",
      "data:text/html,<script>",
      "//example.com",
      "/path",
      "https://user:pass@example.com",
    ])
      expect(safeReference(value)).toBeNull();
  });
});
