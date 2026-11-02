import { useState, type FormEvent } from "react";
import { useInfiniteQuery, useQueryClient } from "@tanstack/react-query";
import { useSession } from "../auth/AuthProvider";
import { Dialog, ErrorState, Loading, PageHeading, Pagination, Time } from "../components/ui";
import styles from "../styles.module.css";

type KeyInfo = { key_id: string; name: string; created_at: string; expires_at: string | null };
type KeyPage = { items: KeyInfo[]; next_cursor: string | null };

export function ApiKeys() {
  const { api, user } = useSession();
  const queries = useQueryClient();
  const [creating, setCreating] = useState(false);
  const [removing, setRemoving] = useState<KeyInfo | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [busy, setBusy] = useState(false);
  const queryKey = ["user", user.profile.sub, "api-keys"];
  const query = useInfiniteQuery({
    queryKey, initialPageParam: null as string | null,
    queryFn: ({ pageParam, signal }) => api.request<KeyPage>("/v1/api-keys", { signal, query: { limit: 20, cursor: pageParam } }),
    getNextPageParam: (page) => page.next_cursor ?? undefined,
  });
  const items = query.data?.pages.flatMap((page) => page.items) ?? [];
  async function remove() {
    if (!removing) return;
    setBusy(true); setError(null);
    try {
      await api.request(`/v1/api-keys/${encodeURIComponent(removing.key_id)}`, { method: "DELETE" });
      setRemoving(null);
      await queries.invalidateQueries({ queryKey });
    } catch (cause) { setError(cause instanceof Error ? cause : new Error("Could not revoke key.")); }
    finally { setBusy(false); }
  }
  return <>
    <PageHeading eyebrow="WORKSPACE / API KEYS" title="API keys" action={<button className={styles.primary} onClick={() => setCreating(true)}>Create API key</button>}>
      Manage keys for CLI and automation. Keys grant access to your account data.
    </PageHeading>
    <section className={styles.panel}>
      {query.isPending ? <Loading label="Loading API keys" /> : <>
        {query.error && <ErrorState error={query.error} retry={() => { void query.refetch(); }} />}
        {items.length === 0 && !query.error && <p>No API keys yet.</p>}
        {items.length > 0 && <div className={styles.tableWrap}><table><thead><tr><th>Name</th><th>Key ID</th><th>Created</th><th>Expires</th><th>Status</th><th>Action</th></tr></thead><tbody>
          {items.map((key) => <tr key={key.key_id}><td>{key.name}</td><td><code>{key.key_id.slice(0, 8)}…</code></td><td><Time value={key.created_at} /></td><td>{key.expires_at ? <Time value={key.expires_at} /> : "Never"}</td><td>{key.expires_at && Date.parse(key.expires_at) <= query.dataUpdatedAt ? "Expired" : "Active"}</td><td><button className={styles.secondary} onClick={() => { setError(null); setRemoving(key); }}>Revoke</button></td></tr>)}
        </tbody></table></div>}
        <Pagination more={query.hasNextPage} fetching={query.isFetchingNextPage} count={items.length} load={() => { void query.fetchNextPage(); }} />
      </>}
    </section>
    {creating && <CreateKey close={() => { setCreating(false); void queries.invalidateQueries({ queryKey }); }} />}
    {removing && <Dialog title="Revoke API key" close={() => { if (!busy) setRemoving(null); }}>
      <p>Revoke “{removing.name}”? New requests using this key will be rejected.</p>
      {error && <ErrorState error={error} />}
      <div className={styles.dialogActions}><button className={styles.secondary} disabled={busy} onClick={() => setRemoving(null)}>Cancel</button><button className={styles.primary} disabled={busy} onClick={() => { void remove(); }}>{busy ? "Revoking…" : "Revoke"}</button></div>
    </Dialog>}
  </>;
}

function CreateKey({ close }: { close: () => void }) {
  const { api } = useSession();
  const [name, setName] = useState("");
  const [days, setDays] = useState("30");
  const [secret, setSecret] = useState<string | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(null);
    try {
      const result = await api.request<KeyInfo & { api_key: string }>("/v1/api-keys", { method: "POST", body: { name: name.trim(), expires_in_days: days === "never" ? null : Number(days) } });
      setSecret(result.api_key);
    } catch (cause) { setError(cause instanceof Error ? cause : new Error("Could not create key.")); }
    finally { setBusy(false); }
  }
  return <Dialog title={secret ? "Copy your API key" : "Create API key"} close={() => { if (!busy) close(); }}>
    {secret ? <div className={styles.form}>
      <p>Copy this key now. It will not be shown again after you close this dialog.</p>
      <label>API key<input readOnly value={secret} onFocus={(event) => event.currentTarget.select()} /></label>
      <div className={styles.dialogActions}><button className={styles.secondary} onClick={() => { void navigator.clipboard.writeText(secret).then(() => setCopied(true)).catch(() => setCopied(false)); }}>{copied ? "Copied" : "Copy"}</button><button className={styles.primary} onClick={close}>Done</button></div>
    </div> : <form className={styles.form} onSubmit={(event) => { void submit(event); }}>
      <label>Name<input autoFocus required maxLength={120} value={name} onChange={(event) => setName(event.target.value)} /></label>
      <label>Expiration<select value={days} onChange={(event) => setDays(event.target.value)}><option value="1">1 day</option><option value="3">3 days</option><option value="15">15 days</option><option value="30">30 days</option><option value="never">Never</option></select></label>
      {error && <><ErrorState error={error} /><p>If the response was lost, check the list for a new key before trying again.</p></>}
      <div className={styles.dialogActions}><button type="button" className={styles.secondary} disabled={busy} onClick={close}>Cancel</button><button className={styles.primary} disabled={busy || !name.trim()}>{busy ? "Creating…" : "Create key"}</button></div>
    </form>}
  </Dialog>;
}
