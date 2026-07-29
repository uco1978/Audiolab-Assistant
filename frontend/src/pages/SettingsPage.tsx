import { useEffect, useState } from "react";
import { fetchSettings, Settings, testProviderConnection, updateSettings } from "../api";

const KEY_STORAGE_PREFIX = "ppc_provider_key_";
const API_KEY_FIELD_BY_PROVIDER: Record<string, string> = {
  gemini: "gemini_api_key",
  groq: "groq_api_key",
  openrouter: "openrouter_api_key",
  openai: "openai_api_key",
  anthropic: "anthropic_api_key",
  cohere: "cohere_api_key",
  mistral: "mistral_api_key",
  perplexity: "perplexity_api_key",
  xai: "xai_api_key",
};

export default function SettingsPage() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [outputDir, setOutputDir] = useState("");
  const [saved, setSaved] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [keys, setKeys] = useState<Record<string, string>>({});
  const [testing, setTesting] = useState<Record<string, boolean>>({});
  const [testStatus, setTestStatus] = useState<Record<string, string>>({});

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
    const restored: Record<string, string> = {};
    for (const provider of Object.keys(API_KEY_FIELD_BY_PROVIDER)) {
      restored[provider] = localStorage.getItem(`${KEY_STORAGE_PREFIX}${provider}`) || "";
    }
    setKeys(restored);
  }, []);

  const handleSave = async () => {
    const payload: Record<string, string | boolean> = { output_dir: outputDir };
    for (const provider of Object.keys(API_KEY_FIELD_BY_PROVIDER)) {
      const keyVal = (keys[provider] || "").trim();
      if (keyVal) {
        payload[API_KEY_FIELD_BY_PROVIDER[provider]] = keyVal;
      }
    }
    const s = await updateSettings(payload);
    setSettings(s);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  const providerLabel = (provider: string): string => {
    if (provider === "openrouter") return "OpenRouter";
    if (provider === "openai") return "OpenAI";
    if (provider === "xai") return "xAI";
    return provider[0].toUpperCase() + provider.slice(1);
  };

  const setProviderKey = (provider: string, value: string) => {
    setKeys((prev) => ({ ...prev, [provider]: value }));
    localStorage.setItem(`${KEY_STORAGE_PREFIX}${provider}`, value);
  };

  const runProviderTest = async (provider: string) => {
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
      {(settings.provider_order?.length ? settings.provider_order : Object.keys(settings.providers)).map((provider) => (
        <div key={provider} style={{ marginBottom: "0.9rem" }}>
          <label>{providerLabel(provider)} API key</label>
          <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
            <input
              type="password"
              value={keys[provider] || ""}
              onChange={(e) => setProviderKey(provider, e.target.value)}
              placeholder={settings.providers[provider] ? "Configured (enter to replace)" : "Paste API key"}
            />
            <button type="button" onClick={() => runProviderTest(provider)} disabled={testing[provider] === true}>
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
