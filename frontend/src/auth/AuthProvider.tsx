import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { useQueryClient } from "@tanstack/react-query";
import { type User, type UserManager } from "oidc-client-ts";
import { ApiClient, apiBase } from "../api/client";
import type { DashboardConfig } from "../api/types";
import { createUserManager, safeReturnPath } from "./settings";

type Session = {
  api: ApiClient;
  manager: UserManager;
  config: DashboardConfig;
  user: User | null;
  login: (path?: string) => Promise<void>;
  logout: () => Promise<void>;
};
type AuthState = {
  loading: boolean;
  error: Error | null;
  session: Session | null;
};
const Context = createContext<AuthState>({
  loading: true,
  error: null,
  session: null,
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const queries = useQueryClient();
  const [state, setState] = useState<AuthState>({
    loading: true,
    error: null,
    session: null,
  });
  useEffect(() => {
    let active = true;
    let manager: UserManager | undefined;
    let unsubscribe: (() => void)[] = [];
    const abort = new AbortController();
    async function initialize() {
      const endpoint = apiBase(import.meta.env.VITE_API_BASE_URL);
      const bootstrap = new ApiClient(
        endpoint,
        async () => "",
        async () => {},
      );
      const config = await bootstrap.request<DashboardConfig>(
        "/v1/dashboard-config",
        { public: true, signal: abort.signal },
      );
      if (!active) return;
      const auth = createUserManager(config);
      manager = auth;
      let currentSubject: string | undefined;
      async function clear() {
        auth.stopSilentRenew();
        await queries.cancelQueries();
        queries.clear();
        await auth.removeUser();
      }
      const api = new ApiClient(
        endpoint,
        async () => {
          let user = await auth.getUser();
          if (user?.expired && user.refresh_token) {
            try {
              user = await auth.signinSilent();
            } catch {
              await clear();
            }
          }
          if (!user || user.expired) {
            await clear();
            throw new Error("Your session expired. Sign in again.");
          }
          return user.access_token;
        },
        clear,
      );
      const session: Session = {
        api,
        manager: auth,
        config,
        user: null,
        login: async (path) => {
          await auth.clearStaleState();
          await auth.signinRedirect({
            state: safeReturnPath(path),
            nonce: crypto.randomUUID(),
          });
        },
        logout: async () => {
          try {
            await auth.revokeTokens(["refresh_token"]);
          } catch {
            // A network failure must still clear the local session and hosted login.
          }
          await clear();
          const url = new URL(config.auth.logout_endpoint);
          url.searchParams.set("client_id", config.auth.client_id);
          url.searchParams.set("logout_uri", `${window.location.origin}/`);
          window.location.assign(url.href);
        },
      };
      const update = async (user: User | null) => {
        if (!active) return;
        if (currentSubject !== user?.profile.sub) {
          await queries.cancelQueries();
          queries.clear();
          currentSubject = user?.profile.sub;
        }
        if (active)
          setState({
            loading: false,
            error: null,
            session: { ...session, user },
          });
      };
      unsubscribe = [
        auth.events.addUserLoaded((user) => {
          void update(user);
        }),
        auth.events.addUserUnloaded(() => {
          void update(null);
        }),
        auth.events.addSilentRenewError(() => {
          void clear();
        }),
        auth.events.addAccessTokenExpired(() => {
          void clear();
        }),
      ];
      let user = await auth.getUser();
      if (user?.expired) {
        try {
          user = user.refresh_token ? await auth.signinSilent() : null;
        } catch {
          await clear();
          user = null;
        }
      }
      await update(user);
    }
    void initialize().catch((error: unknown) => {
      if (active)
        setState({
          loading: false,
          error:
            error instanceof Error
              ? error
              : new Error("Unable to initialize sign-in."),
          session: null,
        });
    });
    return () => {
      active = false;
      abort.abort();
      unsubscribe.forEach((remove) => remove());
      manager?.stopSilentRenew();
    };
  }, [queries]);
  return <Context.Provider value={state}>{children}</Context.Provider>;
}

export function useAuth() {
  return useContext(Context);
}
export function useSession() {
  const { session } = useAuth();
  if (!session?.user) throw new Error("A signed-in session is required.");
  return session as Session & { user: User };
}
