import { useState, type FormEvent } from "react";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { ArrowUpRight, CalendarDays, RefreshCw } from "lucide-react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useSession } from "../auth/AuthProvider";
import type { Page, Project, Run } from "../api/types";
import {
  Badge,
  Breadcrumbs,
  EmptyState,
  ErrorState,
  Loading,
  PageHeading,
  Pagination,
  Time,
} from "../components/ui";
import styles from "../styles.module.css";

function localTime(value: string | null) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return new Date(date.getTime() - date.getTimezoneOffset() * 60_000)
    .toISOString()
    .slice(0, 16);
}

export function History() {
  const { api, user } = useSession();
  const { projectId = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const [filterError, setFilterError] = useState("");
  const prefix = ["user", user.profile.sub];
  const from = params.get("from");
  const to = params.get("to");
  const project = useQuery({
    queryKey: [...prefix, "project", projectId],
    queryFn: ({ signal }) =>
      api.request<Project>(`/v1/projects/${encodeURIComponent(projectId)}`, {
        signal,
        query: { include: "latest_scan" },
      }),
  });
  const query = useInfiniteQuery({
    queryKey: [...prefix, "history", projectId, from, to],
    initialPageParam: null as string | null,
    queryFn: ({ pageParam, signal }) =>
      api.request<Page<Run>>("/v1/runs", {
        signal,
        query: {
          project_id: projectId,
          from,
          to,
          cursor: pageParam,
          limit: 20,
        },
      }),
    getNextPageParam: (page) => page.next_cursor ?? undefined,
    enabled: project.isSuccess,
  });
  function filter(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const start = String(form.get("from") ?? "");
    const end = String(form.get("to") ?? "");
    if (start && end && new Date(start) > new Date(end)) {
      setFilterError("The end time must be after the start time.");
      return;
    }
    setFilterError("");
    const next = new URLSearchParams();
    if (start) next.set("from", new Date(start).toISOString());
    if (end) next.set("to", new Date(end).toISOString());
    setParams(next);
  }
  const items = query.data?.pages.flatMap((page) => page.items) ?? [];
  return (
    <>
      <Breadcrumbs
        items={[
          { label: "Projects", to: "/projects" },
          { label: project.data?.name ?? projectId },
        ]}
      />
      <PageHeading
        eyebrow="PROJECT / SCAN HISTORY"
        title={project.data?.name ?? projectId}
        action={
          <button
            className={styles.secondary}
            disabled={query.isFetching || project.isFetching}
            onClick={() => {
              void project.refetch();
              void query.refetch();
            }}
          >
            <RefreshCw size={15} aria-hidden="true" />
            Refresh
          </button>
        }
      >
        Review security scans, newest scan start time first.
      </PageHeading>
      {project.isPending ? (
        <Loading label="Loading project" />
      ) : project.error ? (
        <ErrorState
          error={project.error}
          retry={() => {
            void project.refetch();
          }}
        />
      ) : (
        <>
          <div className={styles.projectMeta}>
            <code>{projectId}</code>
            <span>
              Created <Time value={project.data.created_at} />
            </span>
            {project.data.latest_scan && (
              <span>
                Latest threshold{" "}
                <Badge
                  value={project.data.latest_scan.result.threshold_status}
                />
              </span>
            )}
          </div>
          <section className={styles.panel}>
            <div className={styles.sectionHeading}>
              <h2>
                <CalendarDays size={18} aria-hidden="true" />
                Scan history
              </h2>
              <span className={styles.subtle}>
                Times shown in your local timezone
              </span>
            </div>
            <form
              key={params.toString()}
              className={styles.filters}
              onSubmit={filter}
            >
              <label>
                Started from
                <input
                  type="datetime-local"
                  name="from"
                  defaultValue={localTime(from)}
                />
              </label>
              <label>
                Started through
                <input
                  type="datetime-local"
                  name="to"
                  defaultValue={localTime(to)}
                />
              </label>
              <button className={styles.secondary}>Apply filters</button>
              {(from || to) && (
                <button
                  type="button"
                  className={styles.textButton}
                  onClick={() => {
                    setFilterError("");
                    setParams({});
                  }}
                >
                  Clear
                </button>
              )}
            </form>
            {filterError && (
              <p role="alert" className={styles.fieldError}>
                {filterError}
              </p>
            )}
            {query.isPending ? (
              <Loading label="Loading scans" />
            ) : (
              <>
                {query.error && (
                  <ErrorState
                    error={query.error}
                    retry={() => {
                      void query.refetch();
                    }}
                  />
                )}
                {items.length > 0 ? (
                  <div className={styles.tableWrap}>
                    <table>
                      <thead>
                        <tr>
                          <th>Scan started</th>
                          <th>Source</th>
                          <th>Threshold</th>
                          <th>Findings</th>
                          <th>Analysis</th>
                          <th>
                            <span className={styles.srOnly}>Open scan</span>
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {items.map((run) => (
                          <tr key={run.run_id}>
                            <td>
                              <Link
                                className={styles.rowLink}
                                to={`/runs/${run.run_id}`}
                              >
                                <Time value={run.started_at} />
                              </Link>
                              <code className={styles.secondaryLine}>
                                {run.run_id.slice(0, 8)}
                              </code>
                            </td>
                            <td>
                              <code className={styles.breakWord}>
                                {run.source.relative_path}
                              </code>
                              <span className={styles.secondaryLine}>
                                {run.source.git?.branch ?? "No Git branch"}
                                {run.source.git?.dirty
                                  ? " · uncommitted changes"
                                  : ""}
                              </span>
                            </td>
                            <td>
                              <Badge value={run.result.threshold_status} />
                            </td>
                            <td>
                              <span className={styles.findingNumber}>
                                {run.result.findings.total.toLocaleString()}
                                <small>CLI reported</small>
                              </span>
                            </td>
                            <td>
                              <Badge
                                value={run.analysis?.status ?? "not indexed"}
                              />
                            </td>
                            <td>
                              <Link
                                className={styles.iconButton}
                                to={`/runs/${run.run_id}`}
                                aria-label={`Open scan ${run.run_id.slice(0, 8)}`}
                              >
                                <ArrowUpRight size={18} />
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
                        from || to ? "No scans in this range" : "No scans yet"
                      }
                    >
                      {from || to
                        ? "Try a wider time range, or load the next page if one is available."
                        : "Ready reports will appear here once ingested through the backend API. CLI cloud upload is not available yet."}
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
        </>
      )}
    </>
  );
}
