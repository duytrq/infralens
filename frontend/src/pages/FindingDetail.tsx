import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, ExternalLink, FileCode2, Info } from "lucide-react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useSession } from "../auth/AuthProvider";
import type { Finding } from "../api/types";
import {
  Badge,
  Breadcrumbs,
  EmptyState,
  ErrorState,
  Loading,
  PageHeading,
} from "../components/ui";
import { useRun } from "./useRun";
import { safeReference } from "./scan-state";
import styles from "../styles.module.css";

export function FindingDetail() {
  const { runId = "", findingId = "" } = useParams();
  const [params] = useSearchParams();
  const { api, user } = useSession();
  const run = useRun(runId);
  const ready =
    run.data?.upload_status === "ready" &&
    run.data.analysis?.status === "ready";
  const query = useQuery({
    queryKey: [
      "user",
      user.profile.sub,
      "finding",
      runId,
      run.data?.analysis?.build_id,
      findingId,
    ],
    queryFn: ({ signal }) =>
      api.request<Finding>(
        `/v1/runs/${encodeURIComponent(runId)}/findings/${encodeURIComponent(findingId)}`,
        { signal },
      ),
    enabled: ready,
  });
  if (run.error)
    return (
      <ErrorState
        error={run.error}
        retry={() => {
          void run.refetch();
        }}
      />
    );
  if (!run.data) return <Loading label="Loading scan" />;
  const back = `/runs/${runId}${params.size ? `?${params}` : ""}`;
  if (!ready)
    return (
      <EmptyState title="Findings are not available yet">
        This scan is not ready for finding detail.{" "}
        <Link to={back}>View its analysis state</Link>.
      </EmptyState>
    );
  if (query.error)
    return (
      <>
        <Link to={back} className={styles.backLink}>
          <ArrowLeft size={16} aria-hidden="true" />
          Back to scan
        </Link>
        <ErrorState
          error={query.error}
          retry={() => {
            void query.refetch();
          }}
        />
      </>
    );
  if (!query.data) return <Loading label="Loading finding" />;
  const finding = query.data;
  return (
    <>
      <Breadcrumbs
        items={[
          { label: "Projects", to: "/projects" },
          {
            label: run.data.project_id,
            to: `/projects/${run.data.project_id}`,
          },
          { label: `Scan ${runId.slice(0, 8)}`, to: back },
          { label: finding.rule_id },
        ]}
      />
      <PageHeading
        eyebrow="FINDING DETAIL"
        title={finding.title}
        action={
          <Link className={styles.secondary} to={back}>
            <ArrowLeft size={16} aria-hidden="true" />
            Back to scan
          </Link>
        }
      >
        <span className={styles.findingIdentity}>
          <Badge value={finding.severity} />
          <code>{finding.rule_id}</code>
        </span>
      </PageHeading>
      {finding.truncated_fields.length > 0 && (
        <div className={styles.notice} role="status">
          <Info size={18} aria-hidden="true" />
          <p>
            Some content was shortened: {finding.truncated_fields.join(", ")}.
            Download the original JSON from the scan for the complete report.
          </p>
        </div>
      )}
      <div className={styles.detailGrid}>
        <div>
          <section className={styles.panel}>
            <div className={styles.sectionHeading}>
              <h2>What was found</h2>
            </div>
            <div className={styles.prose}>
              <p>{finding.message}</p>
              <h3>Why it matters</h3>
              <p>
                {finding.description ||
                  "No additional description was provided by the scanner."}
              </p>
              <h3>Recommended resolution</h3>
              <p>
                {finding.resolution ||
                  "No resolution was provided. Review the rule references for guidance."}
              </p>
            </div>
          </section>
          <section className={styles.panel}>
            <div className={styles.sectionHeading}>
              <h2>
                <FileCode2 size={18} aria-hidden="true" />
                Source excerpt
              </h2>
              <code className={styles.breakWord}>
                {finding.file ?? "Location unavailable"}
              </code>
            </div>
            {finding.code.length ? (
              <div
                className={styles.codeBlock}
                role="region"
                aria-label="Source code excerpt"
                tabIndex={0}
              >
                <pre>
                  {finding.code.map((line, index) => (
                    <span
                      key={`${line.number}-${index}`}
                      className={styles.codeLine}
                      data-cause={line.is_cause}
                    >
                      <span className={styles.lineNumber}>{line.number}</span>
                      <span>{line.content}</span>
                      {line.is_cause && (
                        <span className={styles.causeLabel}>cause</span>
                      )}
                      {"\n"}
                    </span>
                  ))}
                </pre>
              </div>
            ) : (
              <div className={styles.prose}>
                <p className={styles.subtle}>
                  The report does not include a source excerpt for this finding.
                </p>
              </div>
            )}
          </section>
        </div>
        <aside aria-label="Finding context">
          <section className={styles.panel}>
            <div className={styles.sectionHeading}>
              <h2>Location</h2>
            </div>
            <dl className={`${styles.metadata} ${styles.metadataSingle}`}>
              <div>
                <dt>File</dt>
                <dd>
                  <code>{finding.file ?? "Not provided"}</code>
                </dd>
              </div>
              <div>
                <dt>Resource</dt>
                <dd>
                  <code>{finding.resource ?? "Not provided"}</code>
                </dd>
              </div>
              <div>
                <dt>Lines</dt>
                <dd>
                  {finding.start_line
                    ? `${finding.start_line}${finding.end_line && finding.end_line > finding.start_line ? `–${finding.end_line}` : ""}`
                    : "Not provided"}
                </dd>
              </div>
            </dl>
          </section>
          <section className={styles.panel}>
            <div className={styles.sectionHeading}>
              <h2>References</h2>
            </div>
            <ul className={styles.references}>
              {finding.references.length ? (
                finding.references.map((reference, index) => {
                  const url = safeReference(reference);
                  return (
                    <li key={index}>
                      {url ? (
                        <a href={url} target="_blank" rel="noopener noreferrer">
                          {reference}
                          <ExternalLink size={12} aria-hidden="true" />
                        </a>
                      ) : (
                        <span>{reference}</span>
                      )}
                    </li>
                  );
                })
              ) : (
                <li className={styles.subtle}>No references provided.</li>
              )}
            </ul>
          </section>
        </aside>
      </div>
    </>
  );
}
