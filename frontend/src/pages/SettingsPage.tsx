import { useEffect, useState } from "react";
import { fetchSettings, Settings, testProviderConnection, updateSettings } from "../api";
import {
  API_KEY_FIELD_BY_PROVIDER,
  migrateLegacyBrowserKeysOnce,
} from "../providerKeys";

export default function SettingsPage() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [outputDir, setOutputDir] = useState("");
  const [saved, setSaved] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [keys, setKeys] = useState<Record<string, string>>({});
  const [testing, setTesting] = useState<Record<string, boolean>>({});
  const [testStatus, setTestStatus] = useState<Record<string, string>>({});
  const [note, setNote] = useState("");

  const loadSettings = async () => {
    setLoading(true);
    setError("");
    try {
      const migration = await migrateLegacyBrowserKeysOnce();
      if (migration.migrated) {
        setNote(`Migrated browser keys to encrypted server storage: ${migration.providers.join(", ")}`);
      } else {
        setNote("");
      }
      const s = migration.settings ?? (await fetchSettings());
      setSettings(s);
      setOutputDir(s.output_dir);
      // Never echo secrets into the form — leave blank; placeholder shows Configured.
      setKeys({});
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
    setError("");
    const payload: Record<string, string | boolean> = { output_dir: outputDir };
    for (const provider of Object.keys(API_KEY_FIELD_BY_PROVIDER)) {
      const keyVal = (keys[provider] || "").trim();
      if (keyVal) {
        payload[API_KEY_FIELD_BY_PROVIDER[provider]] = keyVal;
      }
    }
    try {
      const s = await updateSettings(payload);
      setSettings(s);
      setKeys({});
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    }
  };

  const handleClear = async (provider: string) => {
    if (!window.confirm(`Remove the stored ${provider} API key from the server?`)) return;
    try {
      const s = await updateSettings({ [API_KEY_FIELD_BY_PROVIDER[provider]]: "" });
      setSettings(s);
      setKeys((prev) => ({ ...prev, [provider]: "" }));
      setTestStatus((prev) => ({ ...prev, [provider]: "Cleared on server" }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Clear failed");
    }
  };

  const providerLabel = (provider: string): string => {
    if (provider === "openrouter") return "OpenRouter";
    if (provider === "openai") return "OpenAI";
    if (provider === "xai") return "xAI";
    return provider[0].toUpperCase() + provider.slice(1);
  };

  const setProviderKey = (provider: string, value: string) => {
    setKeys((prev) => ({ ...prev, [provider]: value }));
  };

  const runProviderTest = async (provider: string) => {
    setTesting((prev) => ({ ...prev, [provider]: true }));
    setTestStatus((prev) => ({ ...prev, [provider]: "" }));
    try {
      const typed = (keys[provider] || "").trim();
      const result = await testProviderConnection({
        provider,
        // Prefer typed key for testing a replacement; otherwise server uses stored key.
        api_key: typed || undefined,
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
      <p className="muted">
        API keys are stored encrypted in the database and used by both the API and the worker.
        The browser never receives the raw keys back — leave a field blank to keep the existing key.
        Click Save after pasting new keys.
      </p>
      {note && <p className="muted">{note}</p>}
      {(settings.provider_order?.length ? settings.provider_order : Object.keys(settings.providers)).map((provider) => (
        <div key={provider} style={{ marginBottom: "0.9rem" }}>
          <label>{providerLabel(provider)} API key</label>
          <div style={{ display: "flex", gap: "0.5rem", alignItems: "center", flexWrap: "wrap" }}>
            <input
              type="password"
              value={keys[provider] || ""}
              onChange={(e) => setProviderKey(provider, e.target.value)}
              placeholder={settings.providers[provider] ? "Configured (paste to replace)" : "Paste API key"}
              autoComplete="off"
            />
            <button type="button" onClick={() => runProviderTest(provider)} disabled={testing[provider] === true}>
              {testing[provider] ? "Testing..." : "Test"}
            </button>
            {settings.providers[provider] && (
              <button type="button" className="secondary" onClick={() => handleClear(provider)}>
                Clear
              </button>
            )}
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
