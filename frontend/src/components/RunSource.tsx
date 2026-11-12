import type { Run } from "../api/types";
import { Link } from "react-router-dom";
import { sourceKind } from "../pages/commit-groups";
import styles from "../styles.module.css";
import sourceStyles from "../pages/source-history.module.css";

export function RunSource({ run }: { run: Run }) {
  const git = run.source.git;
  const kind = sourceKind(run);
  return (
    <section className={styles.panel} aria-label="Source revision">
      <div className={styles.sectionHeading}>
        <h2>Source revision</h2>
      </div>
      <dl className={styles.metadata}>
        <div>
          <dt>{kind === "uncommitted" ? "Base commit" : "Commit"}</dt>
          <dd>
            <code className={styles.breakWord}>
              {git?.commit ?? "Not recorded"}
            </code>
          </dd>
        </div>
        <div>
          <dt>Branch</dt>
          <dd>{git ? (git.branch ?? "Detached HEAD") : "Not recorded"}</dd>
        </div>
        <div>
          <dt>Working tree</dt>
          <dd>
            {kind === "committed"
              ? "Clean checkout"
              : kind === "uncommitted"
                ? "Uncommitted changes"
                : "Without Git metadata"}
          </dd>
        </div>
        <div>
          <dt>Source directory</dt>
          <dd>
            <code>{run.source.relative_path}</code>
          </dd>
        </div>
      </dl>
      {kind === "committed" && git && (
        <p className={sourceStyles.copy}>
          <Link
            to={`/projects/${run.project_id}?view=commits&commit=${git.commit}`}
          >
            View reports for this commit
          </Link>
        </p>
      )}
      {kind !== "committed" && (
        <p className={`${styles.subtle} ${sourceStyles.copy}`}>
          {kind === "uncommitted"
            ? "This report includes local changes and is kept separate from clean commit reports."
            : "Git metadata was not recorded. This may be an older report or a scan without an available Git commit."}
        </p>
      )}
    </section>
  );
}
