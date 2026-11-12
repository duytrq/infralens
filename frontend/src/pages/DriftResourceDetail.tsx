import type { DriftResource } from "../api/types";
import { Badge, Time } from "../components/ui";
import { valueText } from "./drift-state";
import styles from "../styles.module.css";
import driftStyles from "./drift.module.css";

export function DriftResourceDetail({ resource }: { resource: DriftResource }) {
  return (
    <div className={styles.prose}>
      <h3>Source in current configuration</h3>
      <p>
        <Badge value={resource.source?.status ?? "unavailable"} />{" "}
        {resource.source?.reason}
      </p>
      {resource.source?.locations?.map((location, index) => (
        <p key={index}>
          <code>
            {location.file}:{location.start_line}–{location.end_line}
          </code>{" "}
          · resource block
        </p>
      ))}
      <p className={styles.subtle}>
        Locations refer to the configuration checked by the CLI, not to
        individual attribute expressions.
      </p>
      {Object.keys(resource.identifiers).length > 0 && (
        <>
          <h3>Resource identity</h3>
          <dl className={styles.metadata}>
            {Object.entries(resource.identifiers).map(([name, value]) => (
              <div key={name}>
                <dt>{name}</dt>
                <dd>
                  <code>{valueText(value)}</code>
                  {value.status === "known" &&
                    value.source &&
                    ` · ${value.source}`}
                </dd>
              </div>
            ))}
          </dl>
        </>
      )}
      {resource.network_context && (
        <>
          <h3>Network context</h3>
          <p className={styles.subtle}>
            Includes unchanged fields needed for review.
          </p>
          <div
            className={styles.tableWrap}
            tabIndex={0}
            role="region"
            aria-label="Network differences"
          >
            <table className={driftStyles.changes}>
              <thead>
                <tr>
                  <th>Field</th>
                  <th>Saved state</th>
                  <th>Observed</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(resource.network_context.before).map(
                  ([name, before]) => (
                    <tr key={name}>
                      <td>
                        <code>{name}</code>
                      </td>
                      <td>
                        <pre>{valueText(before)}</pre>
                      </td>
                      <td>
                        <pre>
                          {valueText(
                            Object.entries(
                              resource.network_context!.after,
                            ).find(([key]) => key === name)?.[1] ?? {
                              status: "unknown",
                            },
                          )}
                        </pre>
                      </td>
                    </tr>
                  ),
                )}
              </tbody>
            </table>
          </div>
        </>
      )}
      {resource.assessment && (
        <>
          <h3>Review signals</h3>
          <p className={styles.subtle}>
            Policy {resource.assessment.policy}; priorities guide review.
          </p>
          <ul>
            {resource.assessment.signals.map((signal, index) => (
              <li key={index}>
                <Badge value={signal.priority} /> <strong>{signal.code}</strong>
                : {signal.description}
                {signal.paths.length > 0 && (
                  <pre>
                    {signal.paths
                      .map((path) => JSON.stringify(path))
                      .join("\n")}
                  </pre>
                )}
              </li>
            ))}
          </ul>
          <h3>Review guidance</h3>
          <ol>
            {resource.assessment.guidance.review_steps.map((step, index) => (
              <li key={index}>{step}</li>
            ))}
          </ol>
          {resource.assessment.guidance.choices.map((choice) => (
            <details key={choice.id}>
              <summary>{choice.title}</summary>
              <ol>
                {choice.steps.map((step, index) => (
                  <li key={index}>{step}</li>
                ))}
              </ol>
            </details>
          ))}
        </>
      )}
      <h3>CloudTrail candidates</h3>
      <p>
        Events are candidates for review; correlation does not establish the
        cause of drift.
      </p>
      <p>
        <Badge value={resource.trace?.status ?? "disabled"} />{" "}
        {resource.trace?.reason}
      </p>
      {resource.trace?.correlation && (
        <p>
          Correlation: {resource.trace.correlation} · Lookup:{" "}
          {resource.trace.lookup_scope} · Unresolved events:{" "}
          {resource.trace.unresolved_rule_events}
        </p>
      )}
      {resource.trace?.pages_scanned !== undefined && (
        <p>
          Pages scanned: {resource.trace.pages_scanned} · Truncated:{" "}
          {String(resource.trace.truncated)} · Malformed events:{" "}
          {resource.trace.malformed_events}
        </p>
      )}
      {!!resource.trace?.unsupported_attributes?.length && (
        <p>
          Unsupported attributes:{" "}
          {resource.trace.unsupported_attributes.join(", ")}
        </p>
      )}
      {resource.trace?.events.map((event) => (
        <article key={event.event_id} className={driftStyles.event}>
          <h4>{event.event_name}</h4>
          <p>
            <Time value={event.event_time} /> · {event.region}
          </p>
          <dl className={`${styles.metadata} ${styles.metadataSingle}`}>
            {Object.entries(event.actor).map(([key, value]) => (
              <div key={key}>
                <dt>{key}</dt>
                <dd>
                  <code>{value}</code>
                </dd>
              </div>
            ))}
            <div>
              <dt>Event ID</dt>
              <dd>
                <code>{event.event_id}</code>
              </dd>
            </div>
            <div>
              <dt>Matched attributes</dt>
              <dd>{event.matched_attributes.join(", ")}</dd>
            </div>
          </dl>
        </article>
      ))}
    </div>
  );
}
