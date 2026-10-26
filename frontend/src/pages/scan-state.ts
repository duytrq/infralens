import type { Run } from "../api/types";

export function analysisPolling(
  run: Run | undefined,
  attempt: number,
  now = Date.now(),
): number | false {
  if (run?.run_type === "drift") {
    if (
      run.upload_status !== "pending" ||
      now - Date.parse(run.received_at) >= 20 * 60_000
    )
      return false;
    return Math.min(5000 * 2 ** Math.min(attempt, 3), 30_000);
  }
  const analysis = run?.analysis;
  if (
    analysis?.status !== "pending" ||
    now - Date.parse(analysis.requested_at) >= 20 * 60_000
  )
    return false;
  return Math.min(5000 * 2 ** Math.min(attempt, 3), 30_000);
}

export function safeReference(value: string): string | null {
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) &&
      !url.username &&
      !url.password
      ? url.href
      : null;
  } catch {
    return null;
  }
}
