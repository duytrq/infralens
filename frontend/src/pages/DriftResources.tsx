import { useState } from "react";
import type { DriftReport } from "../api/types";
import { Badge, EmptyState } from "../components/ui";
import { DriftResourceDetail } from "./DriftResourceDetail";
import { effectivePriority, valueText } from "./drift-state";
import styles from "../styles.module.css";
import driftStyles from "./drift.module.css";

export function DriftResources({ report }: { report: DriftReport }) {
  const [address, setAddress] = useState("");
  const [priority, setPriority] = useState("");
  const [selected, setSelected] = useState("");
  const [visible, setVisible] = useState(20);
  const resources = report.resources.filter(
    (resource) =>
      resource.address.includes(address) &&
      (!priority || effectivePriority(resource) === priority),
  );
  const current =
    resources.find((resource) => resource.address === selected) ?? resources[0];
  return (
    <>
      <section className={styles.panel}>
        <div className={styles.sectionHeading}>
          <h2>Drift resources</h2>
          <span className={styles.subtle}>
            {resources.length} matching resources
          </span>
        </div>
        <div className={styles.filters}>
          <label>
            Resource address
            <input
              type="search"
              value={address}
              onChange={(event) => {
                setAddress(event.target.value);
                setVisible(20);
              }}
            />
          </label>
          <label>
            Review priority
            <select
              value={priority}
              onChange={(event) => {
                setPriority(event.target.value);
                setVisible(20);
              }}
            >
              <option value="">All priorities</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="unknown">Unknown</option>
            </select>
          </label>
        </div>
        {resources.length ? (
          <>
            <div
              className={styles.tableWrap}
              tabIndex={0}
              role="region"
              aria-label="Resource list"
            >
              <table>
                <thead>
                  <tr>
                    <th>Resource</th>
                    <th>Priority</th>
                    <th>Action</th>
                    <th>Attributes</th>
                  </tr>
                </thead>
                <tbody>
                  {resources.slice(0, visible).map((resource) => (
                    <tr
                      key={resource.address}
                      data-selected={current?.address === resource.address}
                    >
                      <td>
                        <button
                          className={styles.textButton}
                          aria-pressed={current?.address === resource.address}
                          onClick={() => setSelected(resource.address)}
                        >
                          <code>{resource.address}</code>
                        </button>
                      </td>
                      <td>
                        <Badge value={effectivePriority(resource)} />
                      </td>
                      <td>{resource.actions.join(", ")}</td>
                      <td>{resource.attributes.length}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className={styles.pagination}>
              <span className={styles.subtle}>
                {Math.min(resources.length, visible)} of {resources.length}{" "}
                resources
              </span>
              {resources.length > visible && (
                <button
                  className={styles.secondary}
                  onClick={() => setVisible(visible + 20)}
                >
                  Load more resources
                </button>
              )}
            </div>
          </>
        ) : (
          <EmptyState
            title={
              report.has_drift
                ? "No matching resources"
                : "No managed resource drift recorded"
            }
          >
            {report.has_drift
              ? "Try another resource address or priority."
              : "This report is limited to its recorded Terraform scope and provider coverage."}
          </EmptyState>
        )}
      </section>
      {current && (
        <section aria-label="Resource changes" className={styles.panel}>
          <div
            className={`${styles.sectionHeading} ${driftStyles.resourceHeading}`}
          >
            <h2>
              <code>{current.address}</code>
            </h2>
            <Badge value={effectivePriority(current)} />
          </div>
          <div
            className={styles.tableWrap}
            tabIndex={0}
            role="region"
            aria-label="Attribute differences"
          >
            <table className={driftStyles.changes}>
              <thead>
                <tr>
                  <th>Attribute path</th>
                  <th>Saved state</th>
                  <th>Observed</th>
                </tr>
              </thead>
              <tbody>
                {current.attributes.map((attribute, index) => (
                  <tr key={index}>
                    <td>
                      <code>{JSON.stringify(attribute.path)}</code>
                    </td>
                    <td>
                      <pre>{valueText(attribute.before)}</pre>
                    </td>
                    <td>
                      <pre>{valueText(attribute.after)}</pre>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!current.attributes.length && (
            <p className={styles.prose}>
              Resource change with no visible attribute delta.
            </p>
          )}
          <DriftResourceDetail resource={current} />
        </section>
      )}
    </>
  );
}
