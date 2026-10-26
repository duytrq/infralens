import { useInfiniteQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowUpRight, Filter } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";
import type { FormEvent } from "react";
import { useSession } from "../auth/AuthProvider";
import { ApiError } from "../api/client";
import {
  severities,
  type FindingSummary,
  type Page,
  type Run,
} from "../api/types";
import {
  Badge,
  EmptyState,
  ErrorState,
  Loading,
  Pagination,
} from "../components/ui";
import styles from "../styles.module.css";

export function FindingsList({ run }: { run: Run }) {
  const { api, user } = useSession();
  const queries = useQueryClient();
  const [params, setParams] = useSearchParams();
  const severity = params.get("severity");
  const rule = params.get("rule_id");
  const file = params.get("file");
  const key = [
    "user",
    user.profile.sub,
    "findings",
    run.run_id,
    run.analysis?.build_id,
    severity,
    rule,
    file,
  ];
  const query = useInfiniteQuery({
    queryKey: key,
    initialPageParam: null as string | null,
    queryFn: ({ pageParam, signal }) =>
      api.request<Page<FindingSummary>>(`/v1/runs/${run.run_id}/findings`, {
        signal,
        query: { severity, rule_id: rule, file, cursor: pageParam, limit: 20 },
      }),
    getNextPageParam: (page) => page.next_cursor ?? undefined,
  });
  function filter(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    const next = new URLSearchParams();
    for (const key of ["severity", "rule_id", "file"]) {
      const value = String(values.get(key) ?? "");
      if (value) next.set(key, value);
    }
    setParams(next);
  }
  const items = query.data?.pages.flatMap((page) => page.items) ?? [];
  const restart = () => {
    void queries.invalidateQueries({
      queryKey: ["user", user.profile.sub, "run", run.run_id],
    });
    void queries.resetQueries({ queryKey: key, exact: true });
  };
  return (
    <section className={styles.panel}>
      <div className={styles.sectionHeading}>
        <h2>
          <Filter size={18} aria-hidden="true" />
          Findings
        </h2>
        <span className={styles.subtle}>
          Severity order · Exact-match filters
        </span>
      </div>
      <form
        key={params.toString()}
        onSubmit={filter}
        className={styles.filters}
      >
        <label>
          Severity
          <select name="severity" defaultValue={severity ?? ""}>
            <option value="">All severities</option>
            {severities.map((value) => (
              <option key={value}>{value}</option>
            ))}
          </select>
        </label>
        <label>
          Rule ID
          <input
            name="rule_id"
            defaultValue={rule ?? ""}
            placeholder="Exact rule ID"
            maxLength={1024}
          />
        </label>
        <label>
          File
          <input
            name="file"
            defaultValue={file ?? ""}
            placeholder="Exact file path"
            maxLength={4096}
          />
        </label>
        <button className={styles.secondary}>Apply filters</button>
        {(severity || rule || file) && (
          <button
            className={styles.textButton}
            type="button"
            onClick={() => setParams({})}
          >
            Clear
          </button>
        )}
      </form>
      {query.isPending ? (
        <Loading label="Loading findings" />
      ) : (
        <>
          {query.error && (
            <ErrorState
              error={query.error}
              retry={
                query.error instanceof ApiError &&
                [409, 422].includes(query.error.status)
                  ? restart
                  : () => {
                      void query.refetch();
                    }
              }
            />
          )}
          {items.length > 0 ? (
            <div className={styles.tableWrap}>
              <table>
                <thead>
                  <tr>
                    <th>Severity</th>
                    <th>Finding</th>
                    <th>Location</th>
                    <th>
                      <span className={styles.srOnly}>Open finding</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((finding) => (
                    <tr key={finding.finding_id}>
                      <td>
                        <Badge value={finding.severity} />
                      </td>
                      <td>
                        <Link
                          className={styles.rowLink}
                          to={`/runs/${run.run_id}/findings/${finding.finding_id}?${params}`}
                        >
                          {finding.title}
                        </Link>
                        <code className={styles.secondaryLine}>
                          {finding.rule_id}
                        </code>
                      </td>
                      <td>
                        <code className={styles.breakWord}>
                          {finding.file ?? "Location unavailable"}
                          {finding.file && finding.start_line
                            ? `:${finding.start_line}${finding.end_line && finding.end_line > finding.start_line ? `–${finding.end_line}` : ""}`
                            : ""}
                        </code>
                        <span
                          className={`${styles.secondaryLine} ${styles.breakWord}`}
                        >
                          {finding.resource ?? "Resource unavailable"}
                        </span>
                      </td>
                      <td>
                        <Link
                          className={styles.iconButton}
                          to={`/runs/${run.run_id}/findings/${finding.finding_id}?${params}`}
                          aria-label={`Open finding ${finding.rule_id}`}
                        >
                          <ArrowUpRight size={17} />
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            !query.error && (
              <EmptyState
                title={
                  severity || rule || file
                    ? "No matching findings on this page"
                    : "No findings on this page"
                }
              >
                {query.hasNextPage
                  ? "More results may be available. Load the next page to continue."
                  : severity || rule || file
                    ? "Filters use exact, case-sensitive matches. File and rule indexes can take a moment to update; refresh if analysis just finished."
                    : "The analysis contains no visible findings. Check the scan totals and warnings for context."}
              </EmptyState>
            )
          )}
          <Pagination
            more={query.hasNextPage}
            fetching={query.isFetchingNextPage}
            count={items.length}
            load={() => {
              void query.fetchNextPage();
            }}
          />
        </>
      )}
    </section>
  );
}
