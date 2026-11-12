import type { Run } from "../api/types";

type SourceRun = Pick<Run, "run_id" | "project_id" | "source" | "started_at">;
export type SourceKind = "committed" | "uncommitted" | "unrecorded";

export function sourceKind(run: Pick<Run, "source">): SourceKind {
  if (!run.source.git) return "unrecorded";
  return run.source.git.dirty ? "uncommitted" : "committed";
}

export function groupRuns<T extends SourceRun>(runs: T[]) {
  const groups = new Map<
    string,
    { key: string; kind: SourceKind; runs: T[] }
  >();
  const seen = new Set<string>();
  for (const run of [...runs].sort(
    (a, b) =>
      Date.parse(b.started_at) - Date.parse(a.started_at) ||
      a.run_id.localeCompare(b.run_id),
  )) {
    if (seen.has(run.run_id)) continue;
    seen.add(run.run_id);
    const kind = sourceKind(run);
    const key =
      kind === "committed"
        ? JSON.stringify([
            run.project_id,
            run.source.relative_path,
            run.source.git!.commit,
          ])
        : run.run_id;
    const group = groups.get(key) ?? { key, kind, runs: [] };
    group.runs.push(run);
    groups.set(key, group);
  }
  return [...groups.values()];
}
