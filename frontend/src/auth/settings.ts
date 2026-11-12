import { UserManager, WebStorageStateStore } from "oidc-client-ts";
import type { DashboardConfig } from "../api/types";

export function safeReturnPath(value: unknown): string {
  if (
    typeof value !== "string" ||
    !value.startsWith("/") ||
    value.startsWith("//") ||
    value.includes("\\") ||
    [...value].some((char) => char.charCodeAt(0) < 32)
  )
    return "/projects";
  const path = new URL(value, window.location.origin);
  if (
    path.origin !== window.location.origin ||
    path.pathname === "/auth/callback" ||
    path.pathname === "/"
  )
    return "/projects";
  return path.pathname + path.search;
}

export function createUserManager(
  config: DashboardConfig,
  origin = window.location.origin,
) {
  const auth = config.auth;
  if (!auth.allowed_origins.includes(origin))
    throw new Error(
      "This dashboard address is not registered. Open the configured CloudFront URL or localhost:5173.",
    );
  return new UserManager({
    authority: auth.issuer,
    client_id: auth.client_id,
    redirect_uri: `${origin}/auth/callback`,
    post_logout_redirect_uri: `${origin}/`,
    response_type: "code",
    scope: auth.scopes.join(" "),
    automaticSilentRenew: true,
    monitorSession: false,
    loadUserInfo: false,
    userStore: new WebStorageStateStore({ store: window.sessionStorage }),
    stateStore: new WebStorageStateStore({ store: window.sessionStorage }),
    metadata: {
      issuer: auth.issuer,
      authorization_endpoint: auth.authorization_endpoint,
      token_endpoint: auth.token_endpoint,
      revocation_endpoint: auth.revocation_endpoint,
      jwks_uri: `${auth.issuer}/.well-known/jwks.json`,
    },
  });
}
