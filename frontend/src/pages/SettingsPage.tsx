import { useEffect, useState } from "react";
import { fetchSettings, Settings, testProviderConnection, updateSettings } from "../api";

type ProviderId = "gemini" | "groq" | "openrouter";
const KEY_STORAGE_PREFIX = "ppc_provider_key_";

export default function SettingsPage() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [outputDir, setOutputDir] = useState("");
  const [saved, setSaved] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [keys, setKeys] = useState<Record<ProviderId, string>>({
    gemini: "",
    groq: "",
    openrouter: "",
  });
  const [testing, setTesting] = useState<Record<ProviderId, boolean>>({
    gemini: false,
    groq: false,
    openrouter: false,
  });
  const [testStatus, setTestStatus] = useState<Record<ProviderId, string>>({
    gemini: "",
    groq: "",
    openrouter: "",
  });

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

  useEffect(() => {
    const restored: Record<ProviderId, string> = {
      gemini: localStorage.getItem(`${KEY_STORAGE_PREFIX}gemini`) || "",
      groq: localStorage.getItem(`${KEY_STORAGE_PREFIX}groq`) || "",
      openrouter: localStorage.getItem(`${KEY_STORAGE_PREFIX}openrouter`) || "",
    };
    setKeys(restored);
  }, []);

  const handleSave = async () => {
    const payload: Record<string, string | boolean> = { output_dir: outputDir };
    if (keys.gemini.trim()) payload.gemini_api_key = keys.gemini.trim();
    if (keys.groq.trim()) payload.groq_api_key = keys.groq.trim();
    if (keys.openrouter.trim()) payload.openrouter_api_key = keys.openrouter.trim();
    const s = await updateSettings(payload);
    setSettings(s);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  const providerLabel = (provider: ProviderId): string =>
    provider === "openrouter" ? "OpenRouter" : provider[0].toUpperCase() + provider.slice(1);

  const setProviderKey = (provider: ProviderId, value: string) => {
    setKeys((prev) => ({ ...prev, [provider]: value }));
    localStorage.setItem(`${KEY_STORAGE_PREFIX}${provider}`, value);
  };

  const runProviderTest = async (provider: ProviderId) => {
    setTesting((prev) => ({ ...prev, [provider]: true }));
    setTestStatus((prev) => ({ ...prev, [provider]: "" }));
    try {
      const result = await testProviderConnection({
        provider,
        api_key: keys[provider].trim() || undefined,
      });
      setTestStatus((prev) => ({
        ...prev,
        [provider]: result.ok
          ? `Connected (${result.model_id ?? "default model"})`
          : `Failed: ${result.error ?? "Unknown error"}`,
      }));
    } catch (err) {
      setTestStatus((prev) => ({
        ...prev,
        [provider]: `Failed: ${err instanceof Error ? err.message : "Unknown error"}`,
      }));
    } finally {
      setTesting((prev) => ({ ...prev, [provider]: false }));
    }
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
      {(["gemini", "groq", "openrouter"] as ProviderId[]).map((provider) => (
        <div key={provider} style={{ marginBottom: "0.9rem" }}>
          <label>{providerLabel(provider)} API key</label>
          <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
            <input
              type="password"
              value={keys[provider]}
              onChange={(e) => setProviderKey(provider, e.target.value)}
              placeholder={settings.providers[provider] ? "Configured (enter to replace)" : "Paste API key"}
            />
            <button type="button" onClick={() => runProviderTest(provider)} disabled={testing[provider]}>
              {testing[provider] ? "Testing..." : "Test"}
            </button>
            <span className="muted">{settings.providers[provider] ? "Configured" : "Missing key"}</span>
          </div>
          {testStatus[provider] && <p className="muted">{testStatus[provider]}</p>}
        </div>
      ))}
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
