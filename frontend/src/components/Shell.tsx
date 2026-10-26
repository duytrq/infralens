import { useEffect } from "react";
import { ArrowUpRight, FolderKanban, LogOut, ShieldCheck } from "lucide-react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { useSession } from "../auth/AuthProvider";
import styles from "../styles.module.css";

export function Brand() {
  return (
    <span className={styles.brand}>
      <ShieldCheck size={26} strokeWidth={1.8} aria-hidden="true" />
      <span>
        Infra<span className={styles.brandLight}>Lens</span>
      </span>
    </span>
  );
}

export function Shell() {
  const session = useSession();
  const location = useLocation();
  useEffect(() => {
    const heading = document.querySelector<HTMLElement>("h1");
    heading?.focus({ preventScroll: true });
    window.scrollTo(0, 0);
  }, [location.pathname]);
  return (
    <div className={styles.app}>
      <a className={styles.skip} href="#main">
        Skip to content
      </a>
      <aside className={styles.sidebar} aria-label="Workspace sidebar">
        <Link
          className={styles.brandLink}
          to="/projects"
          aria-label="InfraLens projects"
        >
          <Brand />
        </Link>
        <div className={styles.workspace}>
          <span className={styles.workspaceIcon}>IL</span>
          <div>
            <strong>Security workspace</strong>
            <span>Private · Development</span>
          </div>
        </div>
        <p className={styles.navLabel}>WORKSPACE</p>
        <nav aria-label="Main navigation">
          <NavLink
            to="/projects"
            className={({ isActive }) =>
              isActive || location.pathname.startsWith("/runs/")
                ? styles.navActive
                : styles.navItem
            }
          >
            <FolderKanban size={18} aria-hidden="true" />
            Projects
            <ArrowUpRight size={14} aria-hidden="true" />
          </NavLink>
        </nav>
        <div className={styles.sidebarFooter}>
          <ShieldCheck size={18} aria-hidden="true" />
          <div>
            <strong>Your infrastructure, in focus.</strong>
            <p>Terraform security insights powered by Trivy.</p>
          </div>
        </div>
      </aside>
      <div className={styles.mainColumn}>
        <header className={styles.topbar}>
          <span>
            <span className={styles.statusDot} />
            Authenticated workspace
          </span>
          <button
            className={styles.textButton}
            onClick={() => {
              void session.logout();
            }}
          >
            <LogOut size={16} aria-hidden="true" />
            Sign out
          </button>
        </header>
        <main id="main" className={styles.main}>
          <Outlet />
        </main>
        <footer className={styles.footer}>
          InfraLens <span>Static analysis · Terraform</span>
        </footer>
      </div>
    </div>
  );
}
