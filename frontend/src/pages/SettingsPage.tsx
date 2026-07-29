import { useEffect, useState } from "react";
import { fetchSettings, Settings, updateSettings } from "../api";

export default function SettingsPage() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [outputDir, setOutputDir] = useState("");
  const [saved, setSaved] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadSettings = async () => {
    setLoading(true);
    setError("");
    try {
      const s = await fetchSettings();
      setSettings(s);
      setOutputDir(s.output_dir);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load settings";
      setError(message);
      if (message === "Unauthorized") {
        window.location.reload();
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadSettings();
  }, []);

  const handleSave = async () => {
    const s = await updateSettings({ output_dir: outputDir });
    setSettings(s);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  if (loading && !settings) return <p>Loading…</p>;
  if (error && !settings) {
    return (
      <div className="card">
        <h2>Settings</h2>
        <p style={{ color: "var(--danger)" }}>{error}</p>
        <button type="button" onClick={loadSettings}>Retry</button>
      </div>
    );
  }
  if (!settings) return <p>Loading…</p>;

  return (
    <div className="card">
      <h2>Settings — Cloud Edition</h2>
      <p className="muted">
        Environment: <code>{settings.app_env}</code> · Storage: <code>{settings.storage_backend}</code> · Auth:{" "}
        <code>{settings.auth_enabled ? "enabled" : "disabled"}</code>
      </p>

      <h3>AI Providers</h3>
      <p className="muted">
        Gemini: {settings.providers.gemini ? "Configured" : "Missing key"}
        <br />
        Groq: {settings.providers.groq ? "Configured" : "Missing key"}
        <br />
        OpenRouter: {settings.providers.openrouter ? "Configured" : "Missing key"}
      </p>
      <p className="muted">
        Default models: <code>{settings.default_models}</code>
        <br />
        Fallback chain: <code>{settings.model_fallback_chain}</code>
      </p>

      <h3>Brand tone</h3>
      <p className="muted">
        Folder: <code>{settings.brand_examples_dir}</code>
      </p>
      <p className="muted">
        Add <code>.docx</code>, <code>.txt</code>, <code>.md</code>, or <code>.html</code> files with Hebrew
        product copy from your store. Word files are read automatically. Edit{" "}
        <code>style-guide.txt</code> or <code>style-guide.docx</code> for voice rules.
      </p>
      {settings.brand_examples.length > 0 ? (
        <ul>
          {settings.brand_examples.map((f) => (
            <li key={f}>{f}</li>
          ))}
        </ul>
      ) : (
        <p className="muted">No brand examples yet.</p>
      )}

      <label>Output directory</label>
      <input type="text" value={outputDir} onChange={(e) => setOutputDir(e.target.value)} />

      <p className="muted" style={{ marginTop: "1rem" }}>
        This deployment is cloud-provider based; Ollama is removed from runtime paths.
      </p>

      <button type="button" onClick={handleSave}>
        Save
      </button>
      {saved && <span className="muted"> Saved!</span>}
      {error && <p style={{ color: "var(--danger)" }}>{error}</p>}
    </div>
  );
}
