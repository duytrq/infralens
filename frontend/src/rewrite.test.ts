import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { runInNewContext } from "node:vm";
import { describe, expect, it } from "vitest";

const template = readFileSync(
  resolve(process.cwd(), "../infra/frontend.yaml"),
  "utf8",
);
const code = template
  .split("      FunctionCode: |\n")[1]
  .split("      Tags:")[0]
  .replace(/^ {8}/gm, "");
function rewrite(uri: string) {
  const event = {
    request: {
      uri,
      querystring: {
        code: { value: "callback-code" },
        state: { value: "state" },
      },
    },
  };
  return runInNewContext(`${code}\n handler(event)`, {
    event,
  }) as typeof event.request;
}

describe("deployed CloudFront route rewrite", () => {
  it("serves the SPA for routes, including callback and finding deep links", () => {
    for (const route of [
      "/",
      "/projects",
      "/projects/team-infra",
      "/runs/uuid",
      "/runs/uuid/findings/finding",
      "/auth/callback",
    ]) {
      expect(rewrite(route).uri).toBe("/index.html");
    }
    expect(rewrite("/auth/callback").querystring.code.value).toBe(
      "callback-code",
    );
  });
  it("preserves missing asset errors and does not turn arbitrary paths into HTML", () => {
    for (const path of [
      "/assets/missing.js",
      "/favicon.ico",
      "/v1/runs",
      "/unknown",
      "/projects/a/unknown",
    ])
      expect(rewrite(path).uri).toBe(path);
  });
});
