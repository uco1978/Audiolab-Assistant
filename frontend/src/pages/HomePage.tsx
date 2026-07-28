import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { createJob, fetchOllamaStatus, OllamaStatus } from "../api";

export default function HomePage() {
  const navigate = useNavigate();
  const [url, setUrl] = useState("");
  const [ollama, setOllama] = useState<OllamaStatus | null>(null);
  const [webSearch, setWebSearch] = useState(false);
  const [usePlaywright, setUsePlaywright] = useState(false);
  const [rembgEnabled, setRembgEnabled] = useState(true);
  const [aiImages, setAiImages] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    fetchOllamaStatus().then(setOllama);
    const t = setInterval(() => fetchOllamaStatus().then(setOllama), 10000);
    return () => clearInterval(t);
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const job = await createJob({
        url,
        web_search: webSearch,
        use_playwright: usePlaywright,
        rembg_enabled: rembgEnabled,
        ai_image_selection: aiImages,
      });
      navigate(`/jobs/${job.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <div className="card">
        <h2>Local Edition — Ollama only</h2>
        <p className="muted">
          Runs <strong>qwen2.5:7b-instruct</strong> for Hebrew copy and{" "}
          <strong>qwen2.5vl:7b</strong> for product image selection. No cloud API keys.
        </p>
        {ollama && (
          <div className="muted" style={{ marginTop: "0.5rem" }}>
            Ollama: {ollama.ok ? "✓ running" : "✗ not running — start Ollama app"}
            {ollama.ok && (
              <>
                <br />
                Text model: {ollama.text_ready ? "✓" : "✗ pull qwen2.5:7b-instruct"}
                {" · "}
                Vision: {ollama.vision_ready ? "✓" : "✗ pull qwen2.5vl:7b"}
              </>
            )}
          </div>
        )}
      </div>

      <div className="card">
        <h2>New product job</h2>
        <form onSubmit={handleSubmit}>
          <label htmlFor="url">Manufacturer product URL</label>
          <input
            id="url"
            type="url"
            required
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://..."
          />
          <div className="checkbox-row">
            <label>
              <input type="checkbox" checked={aiImages} onChange={(e) => setAiImages(e.target.checked)} />
              AI product image selection (local vision)
            </label>
            <label>
              <input type="checkbox" checked={rembgEnabled} onChange={(e) => setRembgEnabled(e.target.checked)} />
              Remove backgrounds (rembg)
            </label>
            <label>
              <input type="checkbox" checked={usePlaywright} onChange={(e) => setUsePlaywright(e.target.checked)} />
              Playwright fallback
            </label>
            <label>
              <input type="checkbox" checked={webSearch} onChange={(e) => setWebSearch(e.target.checked)} />
              Web search (DuckDuckGo)
            </label>
          </div>
          {error && <p style={{ color: "var(--danger)" }}>{error}</p>}
          <button type="submit" disabled={loading || !ollama?.ok}>
            {loading ? "Starting…" : "Start job"}
          </button>
        </form>
        <p className="muted" style={{ marginTop: "1rem" }}>
          Brand tone: drop Word (<code>.docx</code>) or text files into <code>brand-examples/</code> — see Settings.
        </p>
      </div>
    </>
  );
}
