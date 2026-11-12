import type { Query } from "./types";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public retryAfter?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export function apiBase(value: string | undefined) {
  if (!value)
    throw new Error(
      "API endpoint is missing. Set VITE_API_BASE_URL and rebuild.",
    );
  const url = new URL(value);
  if (
    url.protocol !== "https:" ||
    url.username ||
    url.password ||
    url.search ||
    url.hash ||
    url.pathname !== "/"
  ) {
    throw new Error("The API endpoint must be an HTTPS origin.");
  }
  return url.origin;
}

export function queryString(query: Query = {}) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== null && value !== undefined && value !== "")
      params.set(key, String(value));
  }
  const encoded = params.toString();
  return encoded ? `?${encoded}` : "";
}

export class ApiClient {
  constructor(
    private base: string,
    private token: () => Promise<string>,
    private unauthorized: () => Promise<void>,
  ) {}

  async request<T>(
    path: string,
    options: {
      method?: string;
      body?: unknown;
      query?: Query;
      signal?: AbortSignal;
      public?: boolean;
    } = {},
  ): Promise<T> {
    if (!path.startsWith("/v1/") || path.includes("?") || path.includes("#"))
      throw new Error("Invalid API path.");
    const headers: Record<string, string> = { Accept: "application/json" };
    if (!options.public) headers.Authorization = `Bearer ${await this.token()}`;
    if (options.body !== undefined)
      headers["Content-Type"] = "application/json";
    options.signal?.throwIfAborted();
    const response = await fetch(
      this.base + path + queryString(options.query),
      {
        method: options.method ?? "GET",
        headers,
        signal: options.signal,
        body:
          options.body === undefined ? undefined : JSON.stringify(options.body),
        credentials: "omit",
        cache: "no-store",
        referrerPolicy: "no-referrer",
      },
    );
    if (response.status === 204) return undefined as T;
    const body: unknown = await response.json().catch(() => null);
    if (!response.ok) {
      if (response.status === 401 && !options.public) await this.unauthorized();
      const data = body as {
        error?: { code?: string; message?: string };
        message?: string;
      } | null;
      const seconds = response.headers.get("retry-after");
      const retryAfter = seconds
        ? Number.isFinite(Number(seconds))
          ? Number(seconds) * 1000
          : Date.parse(seconds) - Date.now()
        : undefined;
      throw new ApiError(
        response.status,
        data?.error?.code ?? `http_${response.status}`,
        data?.error?.message ??
          data?.message ??
          `Request failed (${response.status}).`,
        retryAfter,
      );
    }
    return body as T;
  }
}

export function shouldRetry(count: number, error: Error) {
  return (
    count < 3 &&
    (!(error instanceof ApiError) ||
      [429, 500, 502, 503, 504].includes(error.status))
  );
}

export function retryDelay(attempt: number, error: Error) {
  if (error instanceof ApiError && error.retryAfter !== undefined)
    return Math.max(0, Math.min(error.retryAfter, 60_000));
  return Math.min(1000 * 2 ** attempt, 8000) + Math.random() * 250;
}
