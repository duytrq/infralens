import { useEffect, useRef, type ReactNode } from "react";
import {
  AlertCircle,
  ChevronRight,
  FileSearch,
  LoaderCircle,
  X,
} from "lucide-react";
import { Link } from "react-router-dom";
import { ApiError } from "../api/client";
import type { FindingCounts, Severity } from "../api/types";
import { severities } from "../api/types";
import styles from "../styles.module.css";

export function Badge({ value }: { value: string }) {
  return (
    <span className={styles.badge} data-tone={value.toLowerCase()}>
      {value.replaceAll("_", " ")}
    </span>
  );
}

export function PageHeading({
  eyebrow,
  title,
  children,
  action,
}: {
  eyebrow: string;
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    document.title = `${title} — InfraLens`;
    heading.current?.focus({ preventScroll: true });
  }, [title]);
  return (
    <div className={styles.pageHeading}>
      <div>
        <p className={styles.eyebrow}>{eyebrow}</p>
        <h1 ref={heading} tabIndex={-1}>
          {title}
        </h1>
        {children && <p className={styles.subtle}>{children}</p>}
      </div>
      {action && <div className={styles.actions}>{action}</div>}
    </div>
  );
}

export function Breadcrumbs({
  items,
}: {
  items: { label: string; to?: string }[];
}) {
  return (
    <nav aria-label="Breadcrumb" className={styles.breadcrumbs}>
      {items.map((item, index) => (
        <span key={index}>
          {index > 0 && <ChevronRight size={13} aria-hidden="true" />}
          {item.to ? (
            <Link to={item.to}>{item.label}</Link>
          ) : (
            <span aria-current="page">{item.label}</span>
          )}
        </span>
      ))}
    </nav>
  );
}

export function Loading({ label = "Loading data" }: { label?: string }) {
  return (
    <div role="status" aria-busy="true" className={styles.loading}>
      <LoaderCircle size={18} className={styles.spin} aria-hidden="true" />
      <span>{label}…</span>
      <div className={styles.skeleton} />
    </div>
  );
}

export function ErrorState({
  error,
  retry,
}: {
  error: Error;
  retry?: () => void;
}) {
  const notFound = error instanceof ApiError && error.status === 404;
  return (
    <div className={styles.error} role="alert">
      <AlertCircle size={20} aria-hidden="true" />
      <div>
        <strong>
          {notFound
            ? "This item is unavailable"
            : "We couldn’t load this information"}
        </strong>
        <p>
          {notFound
            ? "It may have been deleted, or it belongs to another account."
            : error.message}
        </p>
        {error instanceof ApiError && <code>{error.code}</code>}
        {retry && !notFound && (
          <p>
            <button className={styles.secondary} onClick={retry}>
              Try again
            </button>
          </p>
        )}
      </div>
    </div>
  );
}

export function EmptyState({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <div className={styles.empty}>
      <FileSearch size={28} aria-hidden="true" />
      <h2>{title}</h2>
      <p>{children}</p>
    </div>
  );
}

export function Pagination({
  more,
  fetching,
  count,
  load,
}: {
  more: boolean;
  fetching: boolean;
  count: number;
  load: () => void;
}) {
  return (
    <div className={styles.pagination}>
      <span className={styles.subtle}>
        {count} {count === 1 ? "item" : "items"} loaded
      </span>
      {more ? (
        <button className={styles.secondary} disabled={fetching} onClick={load}>
          {fetching ? "Loading…" : "Load more"}
        </button>
      ) : (
        count > 0 && <span className={styles.subtle}>End of results</span>
      )}
    </div>
  );
}

export function Counts({
  counts,
  label,
}: {
  counts: FindingCounts;
  label: string;
}) {
  const max = Math.max(1, counts.total);
  return (
    <section aria-label={label} className={styles.counts}>
      <div className={styles.countTotal}>
        <span className={styles.eyebrow}>{label}</span>
        <strong>{counts.total.toLocaleString()}</strong>
        <span className={styles.subtle}>total findings</span>
      </div>
      <div className={styles.severityCounts}>
        {severities.map((severity: Severity) => (
          <div key={severity}>
            <div>
              <Badge value={severity} />
              <strong>{counts.by_severity[severity].toLocaleString()}</strong>
            </div>
            <progress
              aria-label={`${severity} findings`}
              value={counts.by_severity[severity]}
              max={max}
              data-tone={severity.toLowerCase()}
            />
          </div>
        ))}
      </div>
    </section>
  );
}

export function Dialog({
  title,
  children,
  close,
}: {
  title: string;
  children: ReactNode;
  close: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    const previous = document.activeElement;
    dialog?.showModal();
    return () => {
      dialog?.close();
      if (previous instanceof HTMLElement) previous.focus();
    };
  }, []);
  return (
    <dialog
      ref={ref}
      className={styles.dialog}
      onCancel={(event) => {
        event.preventDefault();
        close();
      }}
      aria-labelledby="dialog-title"
    >
      <div className={styles.dialogHeading}>
        <h2 id="dialog-title">{title}</h2>
        <button
          className={styles.iconButton}
          onClick={close}
          aria-label="Close dialog"
        >
          <X size={20} />
        </button>
      </div>
      {children}
    </dialog>
  );
}

export function Time({ value }: { value: string }) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return <span>Unknown time</span>;
  return (
    <time dateTime={value} title={date.toISOString()}>
      {date.toLocaleString(undefined, {
        year: "numeric",
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        timeZoneName: "short",
      })}
    </time>
  );
}
