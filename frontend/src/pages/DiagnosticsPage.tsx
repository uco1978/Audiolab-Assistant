import { useEffect, useState } from "react";
import { fetchDiagnostics, DiagnosticsData } from "../api";

type Period = "last_24h" | "last_7d";

export default function DiagnosticsPage() {
  const [data, setData] = useState<DiagnosticsData | null>(null);
  const [error, setError] = useState("");
  const [period, setPeriod] = useState<Period>("last_24h");

  useEffect(() => {
    const load = async () => {
      try {
        setData(await fetchDiagnostics());
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load diagnostics");
      }
    };
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, []);

  if (error) return <div className="card"><p style={{ color: "var(--danger)" }}>{error}</p></div>;
  if (!data) return <div className="card"><p className="muted">Loading…</p></div>;

  const usage = data.ai_usage[period];

  return (
    <>
      {/* Queue status */}
      <div className="card">
        <h2>Worker queue</h2>
        <div className="stat-grid">
          <div className="stat-card"><span>Pending</span><strong>{data.queue.pending}</strong></div>
          <div className="stat-card"><span>Running</span><strong>{data.queue.running}</strong></div>
          <div className="stat-card"><span>Failed</span><strong>{data.queue.failed}</strong></div>
          <div className="stat-card"><span>Completed</span><strong>{data.queue.completed}</strong></div>
        </div>
      </div>

      {/* AI usage */}
      <div className="card">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
          <h2 style={{ margin: 0 }}>AI usage</h2>
          <div style={{ display: "flex", gap: "0.5rem" }}>
            <button
              type="button"
              className={period === "last_24h" ? "" : "secondary"}
              onClick={() => setPeriod("last_24h")}
              style={{ padding: "0.3rem 0.75rem", fontSize: "0.85rem" }}
            >24h</button>
            <button
              type="button"
              className={period === "last_7d" ? "" : "secondary"}
              onClick={() => setPeriod("last_7d")}
              style={{ padding: "0.3rem 0.75rem", fontSize: "0.85rem" }}
            >7d</button>
          </div>
        </div>

        <div className="stat-grid">
          <div className="stat-card"><span>Total calls</span><strong>{usage.total_calls}</strong></div>
          <div className="stat-card"><span>Failures</span><strong style={{ color: usage.total_failures > 0 ? "var(--danger)" : undefined }}>{usage.total_failures}</strong></div>
          <div className="stat-card">
            <span>Fail rate</span>
            <strong>{usage.total_calls ? ((usage.total_failures / usage.total_calls) * 100).toFixed(1) : "0"}%</strong>
          </div>
        </div>

        {usage.by_provider.length > 0 && (
          <table style={{ width: "100%", borderCollapse: "collapse", marginTop: "1rem", fontSize: "0.9rem" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--border)", textAlign: "left" }}>
                <th style={{ padding: "0.4rem 0.5rem" }}>Provider</th>
                <th style={{ padding: "0.4rem 0.5rem" }}>Calls</th>
                <th style={{ padding: "0.4rem 0.5rem" }}>Failures</th>
                <th style={{ padding: "0.4rem 0.5rem" }}>Fail %</th>
                <th style={{ padding: "0.4rem 0.5rem" }}>Avg latency</th>
                <th style={{ padding: "0.4rem 0.5rem" }}>Tokens</th>
              </tr>
            </thead>
            <tbody>
              {usage.by_provider.map((p) => (
                <tr key={p.provider} style={{ borderBottom: "1px solid var(--border)" }}>
                  <td style={{ padding: "0.4rem 0.5rem" }}>{p.provider}</td>
                  <td style={{ padding: "0.4rem 0.5rem" }}>{p.calls}</td>
                  <td style={{ padding: "0.4rem 0.5rem", color: p.failures > 0 ? "var(--danger)" : undefined }}>{p.failures}</td>
                  <td style={{ padding: "0.4rem 0.5rem" }}>{p.calls ? ((p.failures / p.calls) * 100).toFixed(1) : "0"}%</td>
                  <td style={{ padding: "0.4rem 0.5rem" }}>{p.avg_latency_ms}ms</td>
                  <td style={{ padding: "0.4rem 0.5rem" }}>{p.total_tokens.toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Model quality */}
      {data.model_ratings.length > 0 && (
        <div className="card">
          <h2>Model quality (user ratings)</h2>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.9rem" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--border)", textAlign: "left" }}>
                <th style={{ padding: "0.4rem 0.5rem" }}>Model</th>
                <th style={{ padding: "0.4rem 0.5rem" }}>Avg rating</th>
                <th style={{ padding: "0.4rem 0.5rem" }}>Rated jobs</th>
              </tr>
            </thead>
            <tbody>
              {data.model_ratings.map((m) => (
                <tr key={m.model} style={{ borderBottom: "1px solid var(--border)" }}>
                  <td style={{ padding: "0.4rem 0.5rem" }}>{m.model}</td>
                  <td style={{ padding: "0.4rem 0.5rem" }}>
                    <span style={{ color: "#f5b731" }}>{"★".repeat(Math.round(m.avg_rating))}</span>
                    <span style={{ color: "var(--border)" }}>{"★".repeat(5 - Math.round(m.avg_rating))}</span>
                    {" "}{m.avg_rating}
                  </td>
                  <td style={{ padding: "0.4rem 0.5rem" }}>{m.rated_jobs}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Recent errors */}
      {data.recent_errors.length > 0 && (
        <div className="card">
          <h2>Recent errors</h2>
          <div style={{ maxHeight: "300px", overflowY: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.85rem" }}>
              <thead>
                <tr style={{ borderBottom: "1px solid var(--border)", textAlign: "left" }}>
                  <th style={{ padding: "0.4rem 0.5rem" }}>Time</th>
                  <th style={{ padding: "0.4rem 0.5rem" }}>Provider</th>
                  <th style={{ padding: "0.4rem 0.5rem" }}>Model</th>
                  <th style={{ padding: "0.4rem 0.5rem" }}>Error</th>
                </tr>
              </thead>
              <tbody>
                {data.recent_errors.map((e, i) => (
                  <tr key={i} style={{ borderBottom: "1px solid var(--border)" }}>
                    <td style={{ padding: "0.4rem 0.5rem", whiteSpace: "nowrap" }}>
                      {new Date(e.created_at).toLocaleString()}
                    </td>
                    <td style={{ padding: "0.4rem 0.5rem" }}>{e.provider}</td>
                    <td style={{ padding: "0.4rem 0.5rem", fontSize: "0.8rem" }}>{e.model}</td>
                    <td style={{ padding: "0.4rem 0.5rem", color: "var(--danger)" }}>{e.error_class}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Recent jobs */}
      <div className="card">
        <h2>Recent jobs</h2>
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.85rem" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--border)", textAlign: "left" }}>
                <th style={{ padding: "0.4rem 0.5rem" }}>Status</th>
                <th style={{ padding: "0.4rem 0.5rem" }}>Model</th>
                <th style={{ padding: "0.4rem 0.5rem" }}>Fallbacks</th>
                <th style={{ padding: "0.4rem 0.5rem" }}>Rating</th>
                <th style={{ padding: "0.4rem 0.5rem" }}>Scrape</th>
                <th style={{ padding: "0.4rem 0.5rem" }}>Images</th>
                <th style={{ padding: "0.4rem 0.5rem" }}>AI copy</th>
                <th style={{ padding: "0.4rem 0.5rem" }}>Export</th>
                <th style={{ padding: "0.4rem 0.5rem" }}>Total</th>
                <th style={{ padding: "0.4rem 0.5rem" }}>Date</th>
              </tr>
            </thead>
            <tbody>
              {data.recent_jobs.map((j) => (
                <tr key={j.id} style={{ borderBottom: "1px solid var(--border)" }}>
                  <td style={{ padding: "0.4rem 0.5rem" }}>
                    <span className={`status-badge ${j.status}`}>{j.status}</span>
                  </td>
                  <td style={{ padding: "0.4rem 0.5rem", fontSize: "0.8rem" }}>
                    {j.models_used[0] || "—"}
                  </td>
                  <td style={{ padding: "0.4rem 0.5rem", fontSize: "0.8rem", color: "var(--muted)" }}>
                    {j.fallback_models.length > 0 ? j.fallback_models.join(", ") : "—"}
                  </td>
                  <td style={{ padding: "0.4rem 0.5rem" }}>
                    {j.user_rating ? (
                      <span style={{ color: "#f5b731" }}>{"★".repeat(j.user_rating)}<span style={{ color: "var(--border)" }}>{"★".repeat(5 - j.user_rating)}</span></span>
                    ) : "—"}
                  </td>
                  <td style={{ padding: "0.4rem 0.5rem" }}>{fmtMs(j.timing.scrape_ms)}</td>
                  <td style={{ padding: "0.4rem 0.5rem" }}>{fmtMs(j.timing.images_ms)}</td>
                  <td style={{ padding: "0.4rem 0.5rem" }}>{fmtMs(j.timing.ai_copy_ms)}</td>
                  <td style={{ padding: "0.4rem 0.5rem" }}>{fmtMs(j.timing.export_ms)}</td>
                  <td style={{ padding: "0.4rem 0.5rem", fontWeight: 600 }}>{fmtMs(j.timing.total_ms)}</td>
                  <td style={{ padding: "0.4rem 0.5rem", whiteSpace: "nowrap" }}>
                    {new Date(j.created_at).toLocaleDateString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}

function fmtMs(ms: number | undefined): string {
  if (ms == null) return "—";
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}
