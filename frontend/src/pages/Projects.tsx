import { useState, type FormEvent } from "react";
import {
  useInfiniteQuery,
  useMutation,
  useQueryClient,
} from "@tanstack/react-query";
import { ArrowRight, Folder, Plus, RefreshCw } from "lucide-react";
import { Link } from "react-router-dom";
import { useSession } from "../auth/AuthProvider";
import type { Page, Project } from "../api/types";
import {
  Badge,
  Dialog,
  EmptyState,
  ErrorState,
  Loading,
  PageHeading,
  Pagination,
  Time,
} from "../components/ui";
import styles from "../styles.module.css";

export function Projects() {
  const { api, user } = useSession();
  const [creating, setCreating] = useState(false);
  const query = useInfiniteQuery({
    queryKey: ["user", user.profile.sub, "projects"],
    initialPageParam: null as string | null,
    queryFn: ({ pageParam, signal }) =>
      api.request<Page<Project>>("/v1/projects", {
        signal,
        query: {
          include: "latest_scan,latest_drift",
          limit: 20,
          cursor: pageParam,
        },
      }),
    getNextPageParam: (page) => page.next_cursor ?? undefined,
  });
  const items = query.data?.pages.flatMap((page) => page.items) ?? [];
  return (
    <>
      <PageHeading
        eyebrow="WORKSPACE / PROJECTS"
        title="Projects"
        action={
          <>
            <button
              className={styles.secondary}
              onClick={() => {
                void query.refetch();
              }}
              disabled={query.isFetching}
            >
              <RefreshCw size={15} aria-hidden="true" />
              Refresh
            </button>
            <button
              className={styles.primary}
              onClick={() => setCreating(true)}
            >
              <Plus size={17} aria-hidden="true" />
              New project
            </button>
          </>
        }
      >
        Your Terraform projects, security scans and infrastructure drift
        reports.
      </PageHeading>
      <section className={styles.panel}>
        <div className={styles.sectionHeading}>
          <h2>Project inventory</h2>
          <span className={styles.subtle}>Private to your account</span>
        </div>
        {query.isPending ? (
          <Loading label="Loading projects" />
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
                      <th>Project</th>
                      <th>Latest scan</th>
                      <th>Latest drift</th>
                      <th>Threshold</th>
                      <th>Findings</th>
                      <th>
                        <span className={styles.srOnly}>Open project</span>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((project) => (
                      <tr key={project.project_id}>
                        <td>
                          <Link
                            className={styles.projectName}
                            to={`/projects/${project.project_id}`}
                          >
                            <span className={styles.folderIcon}>
                              <Folder size={18} aria-hidden="true" />
                            </span>
                            <span>
                              <strong>{project.name}</strong>
                              <code>{project.project_id}</code>
                            </span>
                          </Link>
                        </td>
                        <td>
                          {project.latest_scan ? (
                            <Time value={project.latest_scan.started_at} />
                          ) : (
                            <span className={styles.subtle}>No scans yet</span>
                          )}
                        </td>
                        <td>
                          {project.latest_drift ? (
                            <Link
                              to={`/runs/${project.latest_drift.run_id}`}
                              className={styles.rowLink}
                            >
                              <Time value={project.latest_drift.started_at} />
                              <span className={styles.secondaryLine}>
                                {project.latest_drift.scope} ·{" "}
                                {project.latest_drift.result.summary.resources}{" "}
                                resources
                              </span>
                            </Link>
                          ) : (
                            <span className={styles.subtle}>
                              No drift reports
                            </span>
                          )}
                        </td>
                        <td>
                          {project.latest_scan ? (
                            <Badge
                              value={
                                project.latest_scan.result.threshold_status
                              }
                            />
                          ) : (
                            "—"
                          )}
                        </td>
                        <td>
                          {project.latest_scan ? (
                            <span className={styles.findingNumber}>
                              {project.latest_scan.result.findings.total.toLocaleString()}
                              <small>CLI reported</small>
                            </span>
                          ) : (
                            "—"
                          )}
                        </td>
                        <td>
                          <Link
                            to={`/projects/${project.project_id}`}
                            className={styles.iconButton}
                            aria-label={`Open ${project.name}`}
                          >
                            <ArrowRight size={18} />
                          </Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              !query.error && (
                <EmptyState title="Start with a project">
                  Create a project to organize your Terraform security scan
                  history.
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
      {creating && <CreateProject close={() => setCreating(false)} />}
    </>
  );
}

function CreateProject({ close }: { close: () => void }) {
  const { api, user } = useSession();
  const queries = useQueryClient();
  const [id, setId] = useState("");
  const [name, setName] = useState("");
  const mutation = useMutation({
    mutationFn: () =>
      api.request<Project>(`/v1/projects/${encodeURIComponent(id)}`, {
        method: "PUT",
        body: { name: name.trim() },
      }),
    onSuccess: async () => {
      await queries.invalidateQueries({
        queryKey: ["user", user.profile.sub, "projects"],
      });
      close();
    },
  });
  function submit(event: FormEvent) {
    event.preventDefault();
    mutation.mutate();
  }
  return (
    <Dialog
      title="Create a project"
      close={() => {
        if (!mutation.isPending) close();
      }}
    >
      <form onSubmit={submit} className={styles.form}>
        <p className={styles.subtle}>
          Give your scans a place to live. Project IDs are permanent.
        </p>
        <label>
          Project name
          <input
            autoFocus
            required
            maxLength={120}
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Production infrastructure"
          />
        </label>
        <label>
          Project ID
          <input
            required
            pattern="[a-z0-9][a-z0-9_-]{0,63}"
            maxLength={64}
            value={id}
            onChange={(event) => setId(event.target.value)}
            placeholder="production-infra"
            aria-describedby="project-id-help"
          />
        </label>
        <p id="project-id-help" className={styles.fieldHelp}>
          1–64 lowercase letters, numbers, hyphens or underscores. Start with a
          letter or number.
        </p>
        {mutation.error && <ErrorState error={mutation.error} />}
        <div className={styles.dialogActions}>
          <button
            type="button"
            className={styles.secondary}
            disabled={mutation.isPending}
            onClick={close}
          >
            Cancel
          </button>
          <button
            className={styles.primary}
            disabled={mutation.isPending || !name.trim()}
          >
            {mutation.isPending ? "Creating…" : "Create project"}
          </button>
        </div>
      </form>
    </Dialog>
  );
}
