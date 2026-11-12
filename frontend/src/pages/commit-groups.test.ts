import { describe, expect, it } from "vitest";
import { groupRuns } from "./commit-groups";

function run(id: string, changes: Record<string, unknown> = {}) {
  return {
    run_id: id,
    project_id: "demo",
    started_at: "2026-11-13T00:00:00Z",
    source: {
      relative_path: ".",
      git: { commit: "a".repeat(40), branch: "main", dirty: false },
    },
    ...changes,
  };
}

describe("commit groups", () => {
  it("groups clean runs across report types, branches and repeated executions without losing history", () => {
    const older = run("security", { started_at: "2026-11-12T00:00:00Z" });
    const newer = run("drift");
    const repeated = run("drift-again", {
      source: {
        ...newer.source,
        git: { ...newer.source.git, branch: "release" },
      },
    });
    const groups = groupRuns([older, newer, repeated]);
    expect(groups).toHaveLength(1);
    expect(groups[0].runs.map((r) => r.run_id)).toEqual([
      "drift",
      "drift-again",
      "security",
    ]);
  });
  it("never mixes projects, source directories or different SHAs", () => {
    const base = run("base");
    const groups = groupRuns([
      base,
      run("project", { project_id: "other" }),
      run("directory", { source: { ...base.source, relative_path: "other" } }),
      run("commit", {
        source: {
          ...base.source,
          git: { ...base.source.git, commit: "b".repeat(40) },
        },
      }),
    ]);
    expect(groups).toHaveLength(4);
  });
  it("keeps dirty runs separate even when their base commit is identical", () => {
    const base = run("base");
    const dirty = { ...base.source, git: { ...base.source.git, dirty: true } };
    const groups = groupRuns([
      base,
      run("dirty1", { source: dirty }),
      run("dirty2", { source: dirty }),
    ]);
    expect(groups.map((g) => g.kind)).toEqual([
      "committed",
      "uncommitted",
      "uncommitted",
    ]);
  });
  it("does not invent Git data for old/non-Git runs and handles detached HEAD", () => {
    const base = run("detached");
    const groups = groupRuns([
      run("old", { source: { relative_path: "." } }),
      run("non-git", { source: { relative_path: "." } }),
      {
        ...base,
        source: { ...base.source, git: { ...base.source.git, branch: null } },
      },
    ]);
    expect(groups).toHaveLength(3);
    expect(groups.filter((g) => g.kind === "unrecorded")).toHaveLength(2);
  });
  it("merges matching runs loaded on later pages and deduplicates repeated IDs", () => {
    const first = run("first");
    expect(groupRuns([first, run("second"), first])[0].runs).toHaveLength(2);
  });
});
