import { afterEach, describe, expect, it, vi } from "vitest";
import {
  ApiClient,
  ApiError,
  apiBase,
  queryString,
  shouldRetry,
} from "./client";

afterEach(() => vi.unstubAllGlobals());

describe("API boundary", () => {
  it("accepts only an HTTPS origin and encodes exact filter values", () => {
    expect(apiBase("https://api.example.com")).toBe("https://api.example.com");
    for (const invalid of [
      undefined,
      "http://api.example.com",
      "https://user:pass@api.example.com",
      "https://api.example.com/path",
    ]) {
      expect(() => apiBase(invalid)).toThrow();
    }
    expect(
      queryString({ file: "a b/main.tf", cursor: "a+/=", severity: "" }),
    ).toBe("?file=a+b%2Fmain.tf&cursor=a%2B%2F%3D");
  });
  it("sends the access token and supports empty deletion responses", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetcher);
    const client = new ApiClient(
      "https://api.example.com",
      async () => "access",
      async () => {},
    );
    await expect(
      client.request("/v1/runs/id", { method: "DELETE" }),
    ).resolves.toBeUndefined();
    expect(fetcher).toHaveBeenCalledWith(
      "https://api.example.com/v1/runs/id",
      expect.objectContaining({
        headers: { Accept: "application/json", Authorization: "Bearer access" },
        credentials: "omit",
      }),
    );
  });
  it("clears the session on gateway unauthorized and does not retry authorization errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response(JSON.stringify({ message: "Unauthorized" }), {
            status: 401,
          }),
        ),
    );
    const clear = vi.fn();
    const client = new ApiClient(
      "https://api.example.com",
      async () => "expired",
      clear,
    );
    await expect(client.request("/v1/projects")).rejects.toMatchObject({
      status: 401,
      message: "Unauthorized",
    });
    expect(clear).toHaveBeenCalledOnce();
    expect(shouldRetry(0, new ApiError(401, "unauthorized", "Expired"))).toBe(
      false,
    );
    expect(
      shouldRetry(2, new ApiError(503, "latest_scan_unavailable", "Busy")),
    ).toBe(true);
    expect(shouldRetry(3, new Error("Network"))).toBe(false);
  });
  it("never sends a request after cancellation while obtaining a token", async () => {
    const abort = new AbortController();
    const fetcher = vi.fn();
    vi.stubGlobal("fetch", fetcher);
    const client = new ApiClient(
      "https://api.example.com",
      async () => {
        abort.abort();
        return "access";
      },
      async () => {},
    );
    await expect(
      client.request("/v1/projects", { signal: abort.signal }),
    ).rejects.toThrow();
    expect(fetcher).not.toHaveBeenCalled();
  });
});
