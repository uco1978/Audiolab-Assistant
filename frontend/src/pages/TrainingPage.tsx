import { useEffect, useRef, useState } from "react";
import {
  CorpusSummary,
  fetchCorpus,
  generateStyleGuide,
  uploadCorpus,
} from "../api";

export default function TrainingPage() {
  const [corpus, setCorpus] = useState<CorpusSummary | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [styleGuide, setStyleGuide] = useState("");
  const [styleGuideMeta, setStyleGuideMeta] = useState("");
  const [selectedCount, setSelectedCount] = useState(0);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    fetchCorpus().then((summary) => {
      setCorpus(summary);
    });
  }, []);

  const handleUpload = async () => {
    const files = fileInputRef.current?.files;
    if (!files || files.length === 0) {
      setError("Select one or more .docx / .txt / .md / .html files first");
      return;
    }
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const summary = await uploadCorpus(files);
      setCorpus(summary);
      setMessage(`Uploaded and scanned ${summary.total_files} files. ${summary.usable_files} usable.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  };

  const handleGenerateStyleGuide = async () => {
    setBusy(true);
    setError("");
    setMessage("Generating style guide… this can take 30–90 seconds.");
    setStyleGuide("");
    setStyleGuideMeta("");
    try {
      const result = await generateStyleGuide();
      setStyleGuide(result.content);
      setStyleGuideMeta(`Generated with ${result.model_used} from ${result.samples_used} samples`);
      setMessage(
        `Done — style guide saved (${result.samples_used} samples, model: ${result.model_used}). Scroll down to read it.`,
      );
    } catch (err) {
      setMessage("");
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
          Upload your product-copy files (.docx, .txt, .md, .html). Then generate a compact style
          guide that cloud models will use for future product pages.
        </p>

        <label>Product copy files</label>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept=".docx,.txt,.md,.html,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain,text/markdown,text/html"
          onChange={(e) => setSelectedCount(e.target.files?.length ?? 0)}
          style={{ marginBottom: "0.75rem" }}
        />
        {selectedCount > 0 && (
          <p className="muted">{selectedCount} file{selectedCount === 1 ? "" : "s"} selected</p>
        )}

        <div className="actions">
          <button type="button" disabled={busy || selectedCount === 0} onClick={handleUpload}>
            Upload &amp; scan
          </button>
          <button
            type="button"
            disabled={busy || !corpus?.usable_files}
            onClick={handleGenerateStyleGuide}
          >
            {busy && message.startsWith("Generating") ? "Generating…" : "Generate style guide"}
          </button>
        </div>

        {message && (
          <p style={{ color: message.startsWith("Done") ? "var(--success, #2e7d32)" : undefined }} className="muted">
            {message}
          </p>
        )}
        {error && <p style={{ color: "var(--danger)" }}>{error}</p>}
      </div>

      {styleGuide && (
        <div className="card">
          <h3>Generated Style Guide</h3>
          {styleGuideMeta && <p className="muted">{styleGuideMeta}</p>}
          <pre className="preview-block" style={{ whiteSpace: "pre-wrap", maxHeight: "28rem", overflow: "auto" }}>
            {styleGuide}
          </pre>
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
            Last scan: {new Date(corpus.scanned_at).toLocaleString()}
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
