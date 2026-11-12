import { useState } from "react";
import { useInfiniteQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { useSession } from "../auth/AuthProvider";
import type { Page, Run } from "../api/types";
import { Badge, EmptyState, ErrorState, Loading, Time } from "../components/ui";
import { groupRuns, type SourceKind } from "./commit-groups";
import styles from "../styles.module.css";
import sourceStyles from "./source-history.module.css";

function useRuns(projectId: string, type: Run["run_type"], revision: number) {
  const { api, user } = useSession();
  return useInfiniteQuery({
    queryKey: [
      "user",
      user.profile.sub,
      "history",
      projectId,
      "commits",
      type,
      revision,
    ],
    initialPageParam: null as string | null,
    queryFn: ({ pageParam, signal }) =>
      api.request<Page<Run>>("/v1/runs", {
        signal,
        query: {
          project_id: projectId,
          run_type: type,
          cursor: pageParam,
          limit: 20,
        },
      }),
    getNextPageParam: (page) => page.next_cursor ?? undefined,
  });
}

const labels: Record<SourceKind, string> = {
  committed: "Commit",
  uncommitted: "Uncommitted changes",
  unrecorded: "Without Git metadata",
};

export function CommitHistory({
  projectId,
  revision,
}: {
  projectId: string;
  revision: number;
}) {
  const security = useRuns(projectId, "security_scan", revision);
  const drift = useRuns(projectId, "drift", revision);
  const [kind, setKind] = useState("");
  const [params] = useSearchParams();
  const [commit, setCommit] = useState(params.get("commit") ?? "");
  const needle = commit.trim().toLowerCase();
  const runs = [security, drift].flatMap(
    (q) => q.data?.pages.flatMap((p) => p.items) ?? [],
  );
  const groups = groupRuns(runs).filter(
    (g) =>
      (!kind || kind === g.kind) &&
      (!needle || g.runs[0].source.git?.commit.includes(needle)),
  );
  const more = security.hasNextPage || drift.hasNextPage;
  const fetching = security.isFetching || drift.isFetching;
  return (
    <>
      <section className={styles.panel}>
        <div className={styles.sectionHeading}>
          <h2>Reports by commit</h2>
        </div>
        <p className={`${styles.subtle} ${sourceStyles.copy}`}>
          Clean checkouts are grouped by commit and source directory. Each
          report keeps its own time, scope and result; the same code can observe
          different infrastructure.
        </p>
        <div className={styles.filters}>
          <label>
            Source category
            <select value={kind} onChange={(e) => setKind(e.target.value)}>
              <option value="">All sources</option>
              <option value="committed">Committed code</option>
              <option value="uncommitted">Uncommitted changes</option>
              <option value="unrecorded">Without Git metadata</option>
            </select>
          </label>
          <label>
            Commit SHA
            <input
              type="search"
              value={commit}
              onChange={(e) => setCommit(e.target.value)}
              placeholder="Full or short SHA"
            />
          </label>
        </div>
        <p className={`${styles.subtle} ${sourceStyles.copy}`}>
          Grouping covers loaded reports. Load more to find older reports for a
          commit; a missing report here does not mean its check passed or was
          never run.
        </p>
        {security.error && (
          <ErrorState
            error={security.error}
            retry={() => {
              void security.refetch();
            }}
          />
        )}
        {drift.error && (
          <ErrorState
            error={drift.error}
            retry={() => {
              void drift.refetch();
            }}
          />
        )}
        {(security.isPending || drift.isPending) && (
          <Loading label="Loading commit reports" />
        )}
      </section>
      {groups.map((group) => {
        const first = group.runs[0];
        const git = first.source.git;
        const branches = [
          ...new Set(
            group.runs.flatMap((r) =>
              r.source.git?.branch ? [r.source.git.branch] : [],
            ),
          ),
        ];
        return (
          <section
            key={group.key}
            className={styles.panel}
            aria-label={`${labels[group.kind]} ${git?.commit ?? first.run_id} ${first.source.relative_path}`}
          >
            <div className={styles.sectionHeading}>
              <h2>{labels[group.kind]}</h2>
              <span className={styles.subtle}>
                {group.runs.length}{" "}
                {group.runs.length === 1 ? "report" : "reports"}
              </span>
            </div>
            {git && (
              <p className={sourceStyles.copy}>
                <span className={styles.subtle}>
                  {group.kind === "uncommitted" ? "Base commit: " : "SHA: "}
                </span>
                <code className={styles.breakWord}>{git.commit}</code>
              </p>
            )}
            <p className={`${styles.subtle} ${sourceStyles.copy}`}>
              Source: <code>{first.source.relative_path}</code> ·{" "}
              {branches.join(", ") ||
                (git ? "Detached HEAD" : "Git metadata not recorded")}
            </p>
            {group.kind === "uncommitted" && (
              <p className={`${styles.subtle} ${sourceStyles.copy}`}>
                Local content may differ from this base commit. This run is not
                paired with other uncommitted runs.
              </p>
            )}
            <div
              className={styles.tableWrap}
              tabIndex={0}
              role="region"
              aria-label="Reports for source"
            >
              <table>
                <thead>
                  <tr>
                    <th>Report</th>
                    <th>Started</th>
                    <th>Scope / mode</th>
                    <th>Result</th>
                    <th>Gate</th>
                  </tr>
                </thead>
                <tbody>
                  {group.runs.map((run) => (
                    <tr key={run.run_id}>
                      <td>
                        <Link
                          className={styles.rowLink}
                          to={`/runs/${run.run_id}`}
                        >
                          {run.run_type === "drift" ? "Drift" : "Security"}{" "}
                          report
                        </Link>
                        <code className={styles.secondaryLine}>
                          {run.run_id.slice(0, 8)}
                        </code>
                      </td>
                      <td>
                        <Time value={run.started_at} />
                      </td>
                      <td>
                        {run.run_type === "drift" ? (
                          <>
                            <code>{run.scope}</code>
                            <span className={styles.secondaryLine}>
                              {run.drift_options.input_mode}
                            </span>
                          </>
                        ) : (
                          "Security scan"
                        )}
                      </td>
                      <td>
                        {run.run_type === "drift"
                          ? `${run.result.summary.resources} resources · ${run.result.summary.attributes} attributes`
                          : `${run.result.findings.total} findings`}
                      </td>
                      <td>
                        <Badge
                          value={
                            run.run_type === "drift"
                              ? run.result.gate_status
                              : run.result.threshold_status
                          }
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        );
      })}
      {!groups.length &&
        !security.isPending &&
        !drift.isPending &&
        !security.error &&
        !drift.error && (
          <EmptyState title="No matching loaded reports">
            Adjust the source filters or load more history.
          </EmptyState>
        )}
      {more && (
        <div className={styles.pagination}>
          <button
            className={styles.secondary}
            disabled={fetching}
            onClick={() => {
              if (security.hasNextPage) void security.fetchNextPage();
              if (drift.hasNextPage) void drift.fetchNextPage();
            }}
          >
            {fetching ? "Loading…" : "Load more reports"}
          </button>
        </div>
      )}
    </>
  );
}
