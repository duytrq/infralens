import { useState, type FormEvent } from "react";
import { useInfiniteQuery } from "@tanstack/react-query";
import type { DriftComparison, DriftRun } from "../api/types";
import { useSession } from "../auth/AuthProvider";
import {
  Badge,
  EmptyState,
  ErrorState,
  Loading,
  Pagination,
} from "../components/ui";
import styles from "../styles.module.css";

export function DriftComparisonPanel({ run }: { run: DriftRun }) {
  const { api, user } = useSession();
  const [baseline, setBaseline] = useState("");
  const query = useInfiniteQuery({
    queryKey: [
      "user",
      user.profile.sub,
      "drift-comparison",
      run.run_id,
      baseline,
    ],
    initialPageParam: {
      cursor: null as string | null,
      baseline_id: baseline || null,
    },
    queryFn: ({ pageParam, signal }) =>
      api.request<DriftComparison>(`/v1/runs/${run.run_id}/drift/comparison`, {
        signal,
        query: { ...pageParam, limit: 20 },
      }),
    getNextPageParam: (page) =>
      page.next_cursor
        ? { cursor: page.next_cursor, baseline_id: page.baseline_run_id }
        : undefined,
  });
  function choose(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBaseline(
      String(new FormData(event.currentTarget).get("baseline") ?? "").trim(),
    );
  }
  const result = query.data?.pages[0];
  const resources = query.data?.pages.flatMap((page) => page.resources) ?? [];
  return (
    <section className={styles.panel}>
      <div className={styles.sectionHeading}>
        <h2>Comparison</h2>
        <span className={styles.subtle}>
          Same project, scope and input mode
        </span>
      </div>
      <form key={baseline} className={styles.filters} onSubmit={choose}>
        <label>
          Baseline run ID
          <input
            name="baseline"
            defaultValue={baseline}
            placeholder="Automatic previous comparable run"
            pattern="[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"
          />
        </label>
        <button className={styles.secondary}>Compare</button>
        {baseline && (
          <button
            type="button"
            className={styles.textButton}
            onClick={() => setBaseline("")}
          >
            Use previous comparable run
          </button>
        )}
      </form>
      {query.isPending ? (
        <Loading label="Loading comparison" />
      ) : query.error ? (
        <ErrorState
          error={query.error}
          retry={() => {
            void query.refetch();
          }}
        />
      ) : (
        result && (
          <>
            <div className={styles.prose}>
              {result.baseline_run_id && (
                <p>
                  Baseline <code>{result.baseline_run_id}</code>
                </p>
              )}
              {result.notes.map((note, index) => (
                <p key={index} className={styles.subtle}>
                  {note}
                </p>
              ))}
              {result.status === "compared" && (
                <p>
                  {Object.entries(result.summary)
                    .map(
                      ([status, count]) =>
                        `${status.replaceAll("_", " ")}: ${count}`,
                    )
                    .join(" · ")}
                </p>
              )}
            </div>
            {result.status === "baseline_missing" ? (
              <EmptyState title="No comparable baseline">
                Upload another completed report in this project, scope and input
                mode to compare changes.
              </EmptyState>
            ) : resources.length ? (
              <div
                className={styles.tableWrap}
                tabIndex={0}
                role="region"
                aria-label="Compared resources"
              >
                <table>
                  <thead>
                    <tr>
                      <th>Resource</th>
                      <th>Comparison</th>
                      <th>Changed paths</th>
                    </tr>
                  </thead>
                  <tbody>
                    {resources.map((resource) => (
                      <tr key={resource.address}>
                        <td>
                          <code>{resource.address}</code>
                        </td>
                        <td>
                          <Badge value={resource.status} />
                        </td>
                        <td>
                          <code>
                            {resource.changed_paths.length
                              ? resource.changed_paths
                                  .map((path) => JSON.stringify(path))
                                  .join(", ")
                              : "—"}
                          </code>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <EmptyState title="No resource changes in either report">
                The two reports contain no managed resource drift.
              </EmptyState>
            )}
            {result.status === "compared" && (
              <Pagination
                more={query.hasNextPage}
                fetching={query.isFetchingNextPage}
                count={resources.length}
                load={() => {
                  void query.fetchNextPage();
                }}
              />
            )}
          </>
        )
      )}
    </section>
  );
}
