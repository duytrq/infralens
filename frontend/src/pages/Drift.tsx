import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { DriftReport, DriftRun } from "../api/types";
import { useSession } from "../auth/AuthProvider";
import {
  Badge,
  Breadcrumbs,
  EmptyState,
  ErrorState,
  Loading,
  PageHeading,
  Time,
} from "../components/ui";
import { ScanActions } from "./ScanActions";
import { DriftResources } from "./DriftResources";
import { DriftComparisonPanel } from "./DriftComparison";
import styles from "../styles.module.css";
import driftStyles from "./drift.module.css";

export function Drift({
  run,
  refresh,
  refreshing,
}: {
  run: DriftRun;
  refresh: () => void;
  refreshing: boolean;
}) {
  const { api, user } = useSession();
  const queries = useQueryClient();
  const query = useQuery({
    queryKey: ["user", user.profile.sub, "drift-report", run.run_id],
    queryFn: ({ signal }) =>
      api.request<DriftReport>(`/v1/runs/${run.run_id}/drift/report`, {
        signal,
      }),
    enabled: run.upload_status === "ready",
  });
  const report = query.data;
  function reload() {
    refresh();
    if (run.upload_status === "ready") void query.refetch();
    void queries.invalidateQueries({
      queryKey: ["user", user.profile.sub, "drift-comparison", run.run_id],
    });
  }
  return (
    <>
      <Breadcrumbs
        items={[
          { label: "Projects", to: "/projects" },
          {
            label: run.project_id,
            to: `/projects/${run.project_id}?type=drift`,
          },
          { label: `Drift ${run.run_id.slice(0, 8)}` },
        ]}
      />
      <PageHeading
        eyebrow="INFRASTRUCTURE DRIFT"
        title={`Drift ${run.run_id.slice(0, 8)}`}
      >
        Started <Time value={run.started_at} /> · Scope {run.scope} · Terraform{" "}
        {run.tool.engine_version}
      </PageHeading>
      <div className={styles.scanToolbar}>
        <div className={styles.runStates}>
          <span>
            Upload <Badge value={run.upload_status} />
          </span>
          {run.upload_status === "ready" && (
            <>
              <span>
                Collection <Badge value={run.result.collection_status} />
              </span>
              <span>
                Gate <Badge value={run.result.gate_status} />
              </span>
              <span>
                Trace <Badge value={run.result.trace_status} />
              </span>
            </>
          )}
        </div>
        <ScanActions
          run={run}
          refresh={reload}
          refreshing={refreshing || query.isFetching}
        />
      </div>
      {run.upload_status !== "ready" ? (
        <EmptyState title="Report upload is not complete">
          The drift report becomes available after the CLI finishes its upload.
          This view checks for completion for up to 20 minutes; Refresh checks
          again.
        </EmptyState>
      ) : query.error ? (
        <ErrorState error={query.error} retry={reload} />
      ) : !report ? (
        <Loading label="Loading drift report" />
      ) : (
        <>
          <section aria-label="Drift summary" className={driftStyles.summary}>
            <div>
              <span>Resources with drift</span>
              <strong>{report.summary.resources.toLocaleString()}</strong>
            </div>
            <div>
              <span>Changed attributes</span>
              <strong>{report.summary.attributes.toLocaleString()}</strong>
            </div>
            {(["high", "medium", "unknown"] as const).map((priority) => (
              <div key={priority}>
                <Badge value={priority} />
                <strong>
                  {run.result.priority_counts[priority].toLocaleString()}
                </strong>
              </div>
            ))}
          </section>
          <div className={styles.notice} role="note">
            <p>
              {report.input_mode === "imported_plan"
                ? "Imported plan: refresh coverage, workspace and freshness are unverified. An empty report does not certify the current infrastructure."
                : "Saved state is compared with provider-observed infrastructure. Unapplied code edits are excluded; resources outside this Terraform workspace are not checked."}
            </p>
          </div>
          {run.result.collection_status === "partial" && (
            <div className={styles.error} role="alert">
              <p>
                CloudTrail could not complete successfully. Drift evidence is
                available; collection and gate must not be treated as passed.
              </p>
            </div>
          )}
          {report.gate && (
            <section className={styles.panel}>
              <div className={styles.sectionHeading}>
                <h2>CI gate</h2>
                <Badge value={report.gate.status} />
              </div>
              <div className={styles.prose}>
                <p>
                  {report.gate.matched_count} resources matched · Exit{" "}
                  {report.gate.exit_code} · {report.gate.policy}
                </p>
                <p>
                  Any drift: {String(report.gate.criteria.any_drift)} · Minimum
                  priority:{" "}
                  {report.gate.criteria.minimum_priority ?? "disabled"} ·
                  Unknown priority:{" "}
                  {report.gate.criteria.unknown_priority ? "fail" : "allow"}
                </p>
                <p className={styles.subtle}>
                  Gate passed does not mean no drift or complete infrastructure
                  coverage. Priorities are review heuristics.
                </p>
                {report.gate.matched_resources.length > 0 && (
                  <details>
                    <summary>Matched resources</summary>
                    <ul>
                      {report.gate.matched_resources.map((match) => (
                        <li key={match.address}>
                          <code>{match.address}</code> · {match.priority} ·{" "}
                          {match.reasons.join(", ")}
                        </li>
                      ))}
                    </ul>
                  </details>
                )}
              </div>
            </section>
          )}
          <DriftResources report={report} />
          <DriftComparisonPanel run={run} />
          <section className={styles.panel}>
            <div className={styles.sectionHeading}>
              <h2>Run context</h2>
            </div>
            <dl className={styles.metadata}>
              <div>
                <dt>Scope</dt>
                <dd>{run.scope}</dd>
              </div>
              <div>
                <dt>Input mode</dt>
                <dd>{report.input_mode}</dd>
              </div>
              <div>
                <dt>Checked</dt>
                <dd>
                  <Time value={report.checked_at} />
                </dd>
              </div>
              <div>
                <dt>Duration</dt>
                <dd>{(run.duration_ms / 1000).toLocaleString()}s</dd>
              </div>
              <div>
                <dt>Tool</dt>
                <dd>
                  InfraLens {run.tool.infralens_version} · Terraform{" "}
                  {report.terraform_version}
                </dd>
              </div>
              <div>
                <dt>Trace</dt>
                <dd>
                  {report.trace?.status ?? "disabled"}
                  {report.trace?.region && ` · ${report.trace.region}`}
                  {report.trace?.account_id && ` · ${report.trace.account_id}`}
                </dd>
              </div>
              <div>
                <dt>Source</dt>
                <dd>
                  <code>{run.source.relative_path}</code>
                </dd>
              </div>
              <div>
                <dt>SHA-256</dt>
                <dd>
                  <code>{run.artifact.sha256}</code>
                </dd>
              </div>
            </dl>
            <div className={styles.prose}>
              {report.trace?.message && <p>{report.trace.message}</p>}
              <details open>
                <summary>Scope and review notes</summary>
                <ul>
                  {report.notes.map((note, index) => (
                    <li key={index}>{note}</li>
                  ))}
                </ul>
              </details>
              {report.normalizations.length > 0 && (
                <details>
                  <summary>
                    Representation normalizations (
                    {report.normalizations.length})
                  </summary>
                  <ul>
                    {report.normalizations.map((item, index) => (
                      <li key={index}>
                        <code>
                          {item.address} {JSON.stringify(item.path)}
                        </code>{" "}
                        — {item.reason}
                      </li>
                    ))}
                  </ul>
                </details>
              )}
            </div>
          </section>
        </>
      )}
    </>
  );
}
