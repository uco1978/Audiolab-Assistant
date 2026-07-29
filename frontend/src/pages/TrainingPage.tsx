import { useEffect, useState } from "react";
import {
  CorpusSummary,
  fetchCorpus,
  generateStyleGuide,
  scanCorpus,
} from "../api";

export default function TrainingPage() {
  const [folderPath, setFolderPath] = useState("");
  const [corpus, setCorpus] = useState<CorpusSummary | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [styleGuide, setStyleGuide] = useState("");
  const [styleGuideMeta, setStyleGuideMeta] = useState("");

  useEffect(() => {
    fetchCorpus().then((summary) => {
      setCorpus(summary);
      if (summary?.folder_path) setFolderPath(summary.folder_path);
    });
  }, []);

  const handleScan = async () => {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const summary = await scanCorpus(folderPath);
      setCorpus(summary);
      setMessage(`Scanned ${summary.total_files} files. ${summary.usable_files} usable.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Scan failed");
    } finally {
      setBusy(false);
    }
  };

  const handleGenerateStyleGuide = async () => {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const result = await generateStyleGuide();
      setStyleGuide(result.content);
      setStyleGuideMeta(`Generated with ${result.model_used} from ${result.samples_used} samples`);
      setMessage("Style guide generated and saved as style-guide.txt");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Style guide generation failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <div className="card">
        <h2>Brand Style Guide</h2>
        <p className="muted">
          Point the app at your existing product-copy folder. Scan the texts, then generate a
          compact style guide that cloud models will use for future product pages.
        </p>

        <label>Product copy folder path</label>
        <input
          type="text"
          value={folderPath}
          onChange={(e) => setFolderPath(e.target.value)}
          placeholder="C:\\Users\\urico\\Documents\\Product Copy"
        />
        <div className="actions">
          <button type="button" disabled={busy || !folderPath} onClick={handleScan}>
            Scan folder
          </button>
          <button
            type="button"
            disabled={busy || !corpus?.usable_files}
            onClick={handleGenerateStyleGuide}
          >
            Generate style guide
          </button>
        </div>

        {message && <p className="muted">{message}</p>}
        {error && <p style={{ color: "var(--danger)" }}>{error}</p>}
      </div>

      {styleGuide && (
        <div className="card">
          <h3>Generated Style Guide</h3>
          {styleGuideMeta && <p className="muted">{styleGuideMeta}</p>}
          <pre className="preview-block">{styleGuide}</pre>
        </div>
      )}

      {corpus && (
        <div className="card">
          <h3>Corpus Summary</h3>
          <div className="stat-grid">
            <Stat label="Total files" value={corpus.total_files} />
            <Stat label="Usable" value={corpus.usable_files} />
            <Stat label="Duplicates" value={corpus.duplicate_files} />
            <Stat label="Issues" value={corpus.issue_files} />
          </div>
          <p className="muted">
            Last scan: {new Date(corpus.scanned_at).toLocaleString()} · {corpus.folder_path}
          </p>

          <div className="corpus-list">
            {corpus.items.map((item) => (
              <details key={item.path} className={`corpus-item ${item.status}`}>
                <summary>
                  <span>{item.filename}</span>
                  <span className={`status-badge ${item.status === "usable" ? "completed" : item.status === "duplicate" ? "pending" : "failed"}`}>
                    {item.status}
                  </span>
                </summary>
                <p className="muted">
                  <strong>Title:</strong> {item.title || "(none)"} · <strong>Chars:</strong>{" "}
                  {item.chars}
                </p>
                {item.issue && <p style={{ color: "var(--danger)" }}>{item.issue}</p>}
                {item.preview && <pre className="preview-block">{item.preview}</pre>}
              </details>
            ))}
          </div>
        </div>
      )}
    </>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="stat-card">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
