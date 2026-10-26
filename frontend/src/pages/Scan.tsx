import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Clock3, Info, Layers3 } from "lucide-react";
import { useParams } from "react-router-dom";
import { useSession } from "../auth/AuthProvider";
import { ApiError } from "../api/client";
import type { Run } from "../api/types";
import {
  Badge,
  Breadcrumbs,
  Counts,
  ErrorState,
  Loading,
  PageHeading,
  Time,
} from "../components/ui";
import { FindingsList } from "./FindingsList";
import { ScanActions } from "./ScanActions";
import { useRun } from "./useRun";
import { analysisPolling } from "./scan-state";
import styles from "../styles.module.css";

export function Scan() {
  const { runId = "" } = useParams();
  const { api, user } = useSession();
  const queries = useQueryClient();
  const query = useRun(runId);
  const retry = useMutation({
    mutationFn: () =>
      api.request<Run>(`/v1/runs/${encodeURIComponent(runId)}/analysis/retry`, {
        method: "POST",
      }),
    onSuccess: (run) => {
      queries.setQueryData(["user", user.profile.sub, "run", runId], run);
    },
  });
  if (query.error instanceof ApiError && query.error.status === 404) {
    return <ErrorState error={query.error} />;
  }
  const run = query.data;
  if (!run)
    return query.error ? (
      <ErrorState
        error={query.error}
        retry={() => {
          void query.refetch();
        }}
      />
    ) : (
      <Loading label="Loading scan" />
    );
  const analysis = run.analysis;
  const ready = run.upload_status === "ready" && analysis?.status === "ready";
  function refresh() {
    void query.refetch();
    void queries.invalidateQueries({
      queryKey: ["user", user.profile.sub, "findings", runId],
    });
  }
  return (
    <>
      <Breadcrumbs
        items={[
          { label: "Projects", to: "/projects" },
          { label: run.project_id, to: `/projects/${run.project_id}` },
          { label: `Scan ${runId.slice(0, 8)}` },
        ]}
      />
      <PageHeading eyebrow="SECURITY SCAN" title={`Scan ${runId.slice(0, 8)}`}>
        Started <Time value={run.started_at} /> ·{" "}
        {(run.duration_ms / 1000).toLocaleString()}s duration
      </PageHeading>
      <div className={styles.scanToolbar}>
        <div className={styles.runStates}>
          <span>
            Upload <Badge value={run.upload_status} />
          </span>
          <span>
            Analysis <Badge value={analysis?.status ?? "not indexed"} />
          </span>
          <span>
            Threshold <Badge value={run.result.threshold_status} />
          </span>
        </div>
        <ScanActions
          run={run}
          refresh={refresh}
          refreshing={query.isFetching}
        />
      </div>
      {query.error && <ErrorState error={query.error} retry={refresh} />}
      {run.upload_status === "ready" && (
        <Counts
          counts={
            ready && analysis.findings ? analysis.findings : run.result.findings
          }
          label={ready ? "Report-derived findings" : "CLI-reported findings"}
        />
      )}
      {analysis?.counts_match === false && (
        <div className={styles.notice} role="status">
          <Info size={18} aria-hidden="true" />
          <div>
            <strong>Finding counts differ</strong>
            <p>
              The report-derived total is {analysis.findings?.total}; the CLI
              manifest reports {run.result.findings.total}. Both values are
              preserved.
            </p>
          </div>
        </div>
      )}
      {!ready && (
        <section className={styles.panel}>
          <div className={styles.analysisState}>
            <Clock3 size={25} aria-hidden="true" />
            <h2>
              {run.upload_status !== "ready"
                ? "Report upload is not complete"
                : analysis?.status === "pending"
                  ? "Analysis is in progress"
                  : analysis?.status === "failed"
                    ? "Analysis could not be completed"
                    : "This report has not been indexed"}
            </h2>
            <p>
              {run.upload_status !== "ready"
                ? "Findings and the original JSON become available after the upload is completed."
                : analysis?.status === "pending"
                  ? analysisPolling(run, 0)
                    ? "This view refreshes automatically while the report is being indexed. The original JSON is already available."
                    : "Automatic checking has stopped after 20 minutes. Refresh manually to check the current state. This does not mean the report is empty."
                  : "The original JSON remains available. Start a new analysis attempt to make findings available."}
            </p>
            {analysis?.error_code && <code>{analysis.error_code}</code>}
            {run.upload_status === "ready" &&
              analysis?.status !== "pending" && (
                <button
                  className={styles.primary}
                  disabled={retry.isPending}
                  onClick={() => retry.mutate()}
                >
                  {retry.isPending
                    ? "Requesting…"
                    : analysis?.status === "failed"
                      ? "Retry analysis"
                      : "Start analysis"}
                </button>
              )}
            {retry.error && <ErrorState error={retry.error} />}
          </div>
        </section>
      )}
      {ready && <FindingsList key={analysis.build_id} run={run} />}
      <section className={styles.panel}>
        <div className={styles.sectionHeading}>
          <h2>
            <Layers3 size={18} aria-hidden="true" />
            Scan context
          </h2>
          <span className={styles.subtle}>Immutable scan metadata</span>
        </div>
        <dl className={styles.metadata}>
          <div>
            <dt>Source</dt>
            <dd>
              <code>{run.source.relative_path}</code>
            </dd>
          </div>
          <div>
            <dt>Branch</dt>
            <dd>
              {run.source.git?.branch ?? "Not provided"}
              {run.source.git?.dirty ? " · uncommitted changes" : ""}
            </dd>
          </div>
          <div>
            <dt>Commit</dt>
            <dd>
              <code>{run.source.git?.commit ?? "Not provided"}</code>
            </dd>
          </div>
          <div>
            <dt>Scanner</dt>
            <dd>
              Trivy {run.tool.engine_version} · InfraLens{" "}
              {run.tool.infralens_version}
            </dd>
          </div>
          <div>
            <dt>Threshold</dt>
            <dd>{run.scan_options.fail_on ?? "Not configured"}</dd>
          </div>
          <div>
            <dt>Severity selection</dt>
            <dd>{run.scan_options.severity.join(", ")}</dd>
          </div>
          <div>
            <dt>Report</dt>
            <dd>JSON · {run.artifact.size_bytes.toLocaleString()} bytes</dd>
          </div>
          <div>
            <dt>SHA-256</dt>
            <dd>
              <code>{run.artifact.sha256}</code>
            </dd>
          </div>
          <div>
            <dt>Run ID</dt>
            <dd>
              <code>{run.run_id}</code>
            </dd>
          </div>
          <div>
            <dt>Uploaded</dt>
            <dd>
              {run.uploaded_at ? <Time value={run.uploaded_at} /> : "Pending"}
            </dd>
          </div>
          {run.tool.checks_version && (
            <div>
              <dt>Checks version</dt>
              <dd>{run.tool.checks_version}</dd>
            </div>
          )}
          <div>
            <dt>Warnings</dt>
            <dd>
              {run.result.warnings.length
                ? run.result.warnings.join(", ")
                : "None reported"}
            </dd>
          </div>
        </dl>
      </section>
    </>
  );
}
