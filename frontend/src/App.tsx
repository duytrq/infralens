import { Component, type ReactNode } from "react";
import { BrowserRouter, Link, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider } from "./auth/AuthProvider";
import { shouldRetry, retryDelay } from "./api/client";
import { Shell } from "./components/Shell";
import { EmptyState, ErrorState } from "./components/ui";
import { AuthGate, Callback, SignIn } from "./pages/AuthPages";
import { Projects } from "./pages/Projects";
import { History } from "./pages/History";
import { Scan } from "./pages/Scan";
import { FindingDetail } from "./pages/FindingDetail";
import styles from "./styles.module.css";

const queries = new QueryClient({
  defaultOptions: {
    queries: {
      retry: shouldRetry,
      retryDelay,
      staleTime: 30_000,
      refetchOnWindowFocus: false,
    },
    mutations: { retry: false },
  },
});

class ErrorBoundary extends Component<
  { children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? (
      <main className={styles.standalone}>
        <ErrorState
          error={
            new Error("Something went wrong. Reload the dashboard to recover.")
          }
          retry={() => window.location.reload()}
        />
      </main>
    ) : (
      this.props.children
    );
  }
}

export function App() {
  return (
    <ErrorBoundary>
      <QueryClientProvider client={queries}>
        <AuthProvider>
          <BrowserRouter>
            <Routes>
              <Route path="/" element={<SignIn />} />
              <Route path="/auth/callback" element={<Callback />} />
              <Route element={<AuthGate />}>
                <Route element={<Shell />}>
                  <Route path="/projects" element={<Projects />} />
                  <Route path="/projects/:projectId" element={<History />} />
                  <Route path="/runs/:runId" element={<Scan />} />
                  <Route
                    path="/runs/:runId/findings/:findingId"
                    element={<FindingDetail />}
                  />
                  <Route
                    path="*"
                    element={
                      <EmptyState title="Page not found">
                        This address is not part of your dashboard.{" "}
                        <Link to="/projects">Return to projects</Link>.
                      </EmptyState>
                    }
                  />
                </Route>
              </Route>
            </Routes>
          </BrowserRouter>
        </AuthProvider>
      </QueryClientProvider>
    </ErrorBoundary>
  );
}
