import { useEffect, useState } from "react";
import { NavLink, Route, Routes } from "react-router-dom";
import { fetchAuthStatus, fetchMe, logout } from "./api";
import { syncProviderKeysToServer } from "./providerKeys";
import DiagnosticsPage from "./pages/DiagnosticsPage";
import HomePage from "./pages/HomePage";
import JobDetailPage from "./pages/JobDetailPage";
import JobsPage from "./pages/JobsPage";
import LoginPage from "./pages/LoginPage";
import SettingsPage from "./pages/SettingsPage";
import StoragePage from "./pages/StoragePage";
import TrainingPage from "./pages/TrainingPage";

export default function App() {
  // Fail closed: require login unless server explicitly says auth is off.
  const [authEnabled, setAuthEnabled] = useState(true);
  const [ready, setReady] = useState(false);
  const [email, setEmail] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const status = await fetchAuthStatus();
        setAuthEnabled(status.auth_enabled);
        if (!status.auth_enabled) {
          setEmail("local@offline");
          return;
        }
        try {
          const me = await fetchMe();
          setEmail(me.email);
        } catch {
          setEmail(null);
        }
      } catch {
        setAuthEnabled(true);
        setEmail(null);
      } finally {
        setReady(true);
      }
    })();
  }, []);

  // After login, restore API keys from this browser onto the server if missing
  // (e.g. after redeploy wiped ephemeral .env / process env).
  useEffect(() => {
    if (!ready || (authEnabled && !email)) return;
    void syncProviderKeysToServer().catch(() => {
      /* non-fatal — Settings Save remains available */
    });
  }, [ready, authEnabled, email]);

  if (!ready) return <div className="layout"><p>Loading...</p></div>;

  if (authEnabled && !email) {
    return (
      <div className="layout">
        <LoginPage
          onLoggedIn={(nextEmail) => {
            setEmail(nextEmail);
            void syncProviderKeysToServer().catch(() => undefined);
          }}
        />
      </div>
    );
  }

  return (
    <div className="layout">
      <header>
        <h1>
          Product Page Creator <span className="muted" style={{ fontSize: "0.85rem" }}>Cloud Ready</span>
        </h1>
        <nav>
          <NavLink to="/" end>Home</NavLink>
          <NavLink to="/jobs">Jobs</NavLink>
          <NavLink to="/storage">Storage</NavLink>
          <NavLink to="/training">Training</NavLink>
          <NavLink to="/settings">Settings</NavLink>
          <NavLink to="/diagnostics">Diagnostics</NavLink>
        </nav>
        <div className="auth-info">
          <span className="muted">{email}</span>
          {authEnabled && (
            <button
              className="secondary"
              type="button"
              onClick={() => {
                logout();
                window.location.reload();
              }}
            >
              Logout
            </button>
          )}
        </div>
      </header>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/jobs" element={<JobsPage />} />
        <Route path="/jobs/:id" element={<JobDetailPage />} />
        <Route path="/storage" element={<StoragePage />} />
        <Route path="/training" element={<TrainingPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/diagnostics" element={<DiagnosticsPage />} />
      </Routes>
    </div>
  );
}
