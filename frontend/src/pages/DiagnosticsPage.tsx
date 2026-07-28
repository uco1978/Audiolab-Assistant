import { useEffect, useState } from "react";
import { fetchQueueStats, QueueStats } from "../api";

export default function DiagnosticsPage() {
  const [stats, setStats] = useState<QueueStats | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const load = async () => {
      try {
        setStats(await fetchQueueStats());
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load diagnostics");
      }
    };
    load();
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, []);

  return (
    <div className="card">
      <h2>Worker diagnostics</h2>
      {error && <p style={{ color: "var(--danger)" }}>{error}</p>}
      {!stats && !error && <p className="muted">Loading…</p>}
      {stats && (
        <div className="stat-grid">
          <div className="stat-card"><span>Pending</span><strong>{stats.pending}</strong></div>
          <div className="stat-card"><span>Running</span><strong>{stats.running}</strong></div>
          <div className="stat-card"><span>Failed</span><strong>{stats.failed}</strong></div>
          <div className="stat-card"><span>Completed</span><strong>{stats.completed}</strong></div>
        </div>
      )}
    </div>
  );
}
