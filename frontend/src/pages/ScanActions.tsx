import { useState } from "react";
import {
  useMutation,
  useQueryClient,
  type InfiniteData,
} from "@tanstack/react-query";
import { Download, RefreshCw, Trash2 } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useSession } from "../auth/AuthProvider";
import type { Page, Project, Run } from "../api/types";
import { Dialog, ErrorState } from "../components/ui";
import styles from "../styles.module.css";

export function ScanActions({
  run,
  refresh,
  refreshing,
}: {
  run: Run;
  refresh: () => void;
  refreshing: boolean;
}) {
  const { api, user } = useSession();
  const queries = useQueryClient();
  const navigate = useNavigate();
  const [confirming, setConfirming] = useState(false);
  const prefix = ["user", user.profile.sub];
  const download = useMutation({
    mutationFn: () =>
      api.request<{ url: string; expires_at: string }>(
        `/v1/runs/${run.run_id}/artifacts/json`,
      ),
    onSuccess: (data) => {
      const url = new URL(data.url);
      if (url.protocol !== "https:" || url.username || url.password)
        throw new Error("Invalid report download address.");
      window.location.assign(url.href);
    },
  });
  const remove = useMutation({
    mutationFn: () =>
      api.request(`/v1/runs/${run.run_id}`, { method: "DELETE" }),
    onSuccess: async () => {
      await queries.cancelQueries({ queryKey: prefix });
      queries.removeQueries({
        predicate: (query) =>
          query.queryKey[0] === "user" &&
          query.queryKey[1] === user.profile.sub &&
          ["run", "findings", "finding"].includes(String(query.queryKey[2])) &&
          query.queryKey[3] === run.run_id,
      });
      queries.setQueriesData<InfiniteData<Page<Run>>>(
        { queryKey: [...prefix, "history"] },
        (old) =>
          old && {
            ...old,
            pages: old.pages.map((page) => ({
              ...page,
              items: page.items.filter((item) => item.run_id !== run.run_id),
            })),
          },
      );
      queries.setQueriesData<InfiniteData<Page<Project>>>(
        { queryKey: [...prefix, "projects"] },
        (old) =>
          old && {
            ...old,
            pages: old.pages.map((page) => ({
              ...page,
              items: page.items.map((item) =>
                item.latest_scan?.run_id === run.run_id
                  ? { ...item, latest_scan: null }
                  : item,
              ),
            })),
          },
      );
      navigate(`/projects/${run.project_id}`, { replace: true });
      for (const kind of ["history", "projects", "project"])
        void queries.invalidateQueries({ queryKey: [...prefix, kind] });
    },
  });
  return (
    <>
      <div className={styles.actions}>
        <button
          className={styles.secondary}
          onClick={refresh}
          disabled={refreshing}
        >
          <RefreshCw size={15} aria-hidden="true" />
          Refresh
        </button>
        <button
          className={styles.secondary}
          onClick={() => download.mutate()}
          disabled={run.upload_status !== "ready" || download.isPending}
        >
          <Download size={16} aria-hidden="true" />
          {download.isPending ? "Preparing…" : "Download JSON"}
        </button>
        <button className={styles.danger} onClick={() => setConfirming(true)}>
          <Trash2 size={15} aria-hidden="true" />
          Delete scan
        </button>
      </div>
      {download.error && <ErrorState error={download.error} />}
      {confirming && (
        <Dialog
          title="Delete this scan?"
          close={() => {
            if (!remove.isPending) setConfirming(false);
          }}
        >
          <div className={styles.form}>
            <p>
              This removes the scan and its findings from your history
              immediately. Physical cleanup may finish later.
            </p>
            <p className={styles.subtle}>
              Run <code>{run.run_id}</code>
            </p>
            {remove.error && <ErrorState error={remove.error} />}
            <div className={styles.dialogActions}>
              <button
                className={styles.secondary}
                disabled={remove.isPending}
                onClick={() => setConfirming(false)}
              >
                Cancel
              </button>
              <button
                className={styles.danger}
                disabled={remove.isPending}
                onClick={() => remove.mutate()}
              >
                {remove.isPending ? "Deleting…" : "Confirm deletion"}
              </button>
            </div>
          </div>
        </Dialog>
      )}
    </>
  );
}
