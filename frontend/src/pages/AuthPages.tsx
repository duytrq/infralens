import { useEffect, useRef, useState } from "react";
import { ArrowRight } from "lucide-react";
import { Navigate, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthProvider";
import { safeReturnPath } from "../auth/settings";
import { Brand } from "../components/Shell";
import { ErrorState, Loading } from "../components/ui";
import styles from "../styles.module.css";

export function AuthGate() {
  const { loading, error, session } = useAuth();
  if (loading)
    return (
      <div className={styles.standalone}>
        <Loading label="Connecting to your workspace" />
      </div>
    );
  if (error)
    return (
      <div className={styles.standalone}>
        <Brand />
        <ErrorState error={error} retry={() => window.location.reload()} />
      </div>
    );
  return session?.user ? <Outlet /> : <SignIn />;
}

export function SignIn() {
  const { loading, error, session } = useAuth();
  const location = useLocation();
  const [loginError, setError] = useState<Error | null>(null);
  const [busy, setBusy] = useState(false);
  if (session?.user) return <Navigate to="/projects" replace />;
  async function signIn() {
    if (!session) return;
    setBusy(true);
    try {
      await session.login(location.pathname + location.search);
    } catch {
      setError(new Error("Unable to start sign-in. Please try again."));
      setBusy(false);
    }
  }
  return (
    <main className={styles.login}>
      <section className={styles.loginPanel} aria-labelledby="sign-in-title">
        <Brand />
        <h1 id="sign-in-title">Sign in</h1>
        <p className={styles.subtle}>
          View your projects and security reports.
        </p>
        {loading ? (
          <Loading label="Connecting" />
        ) : error ? (
          <ErrorState error={error} retry={() => window.location.reload()} />
        ) : (
          <button
            className={styles.primary}
            disabled={busy || !session}
            onClick={() => {
              void signIn();
            }}
          >
            {busy ? "Redirecting…" : "Sign in"}
            <ArrowRight size={17} aria-hidden="true" />
          </button>
        )}
        {loginError && <ErrorState error={loginError} />}
        <p className={styles.loginNote}>
          Contact your administrator if you need an account.
        </p>
      </section>
    </main>
  );
}

export function Callback() {
  const { loading, error, session } = useAuth();
  const [callbackError, setError] = useState<Error | null>(null);
  const navigate = useNavigate();
  const started = useRef(false);
  useEffect(() => {
    if (!session || started.current) return;
    started.current = true;
    void session.manager
      .signinRedirectCallback()
      .then((user) => {
        const destination = safeReturnPath(user.state);
        window.history.replaceState({}, "", "/auth/callback");
        navigate(destination, { replace: true });
      })
      .catch(() => {
        window.history.replaceState({}, "", "/auth/callback");
        setError(
          new Error(
            "Sign-in could not be verified. The link may have expired or already been used. Return to sign in and try again.",
          ),
        );
      });
  }, [session, navigate]);
  return (
    <main className={styles.standalone}>
      <Brand />
      {error || callbackError ? (
        <>
          <ErrorState error={(error ?? callbackError)!} />
          <a className={styles.primary} href="/">
            Return to sign in
          </a>
        </>
      ) : (
        <Loading label={loading ? "Connecting" : "Completing sign-in"} />
      )}
    </main>
  );
}
