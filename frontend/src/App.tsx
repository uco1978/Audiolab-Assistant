import { useEffect, useState } from "react";
import { NavLink, Route, Routes } from "react-router-dom";
import { fetchMe, fetchSettings, logout } from "./api";
import DiagnosticsPage from "./pages/DiagnosticsPage";
import HomePage from "./pages/HomePage";
import JobDetailPage from "./pages/JobDetailPage";
import JobsPage from "./pages/JobsPage";
import LoginPage from "./pages/LoginPage";
import SettingsPage from "./pages/SettingsPage";
import TrainingPage from "./pages/TrainingPage";

export default function App() {
  const [authEnabled, setAuthEnabled] = useState(false);
  const [ready, setReady] = useState(false);
  const [email, setEmail] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const settings = await fetchSettings();
        setAuthEnabled(settings.auth_enabled);
        if (settings.auth_enabled) {
          try {
            const me = await fetchMe();
            setEmail(me.email);
          } catch {
            setEmail(null);
          }
        } else {
          setEmail("local@offline");
        }
      } catch {
        setEmail(null);
      } finally {
        setReady(true);
      }
    })();
  }, []);

  if (!ready) return <div className="layout"><p>Loading...</p></div>;

  if (authEnabled && !email) {
    return (
      <div className="layout">
        <LoginPage onLoggedIn={setEmail} />
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
        <Route path="/training" element={<TrainingPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/diagnostics" element={<DiagnosticsPage />} />
      </Routes>
    </div>
  );
}
