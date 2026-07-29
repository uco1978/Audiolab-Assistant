import { useCallback, useEffect, useState } from "react";
import { deleteStorage, fetchStorage, StorageListing } from "../api";

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 * 1024 * 1024) return `${(n / (1024 * 1024)).toFixed(1)} MB`;
  return `${(n / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

function folderLabel(folderPrefix: string, currentPrefix: string): string {
  const trimmed = folderPrefix.replace(/\/$/, "");
  if (!currentPrefix) return trimmed.split("/").pop() || trimmed;
  const base = currentPrefix.replace(/\/$/, "");
  if (trimmed.startsWith(base + "/")) {
    return trimmed.slice(base.length + 1) || trimmed;
  }
  return trimmed.split("/").pop() || trimmed;
}

function fileLabel(key: string, currentPrefix: string): string {
  if (!currentPrefix) return key;
  const base = currentPrefix.replace(/\/$/, "") + "/";
  return key.startsWith(base) ? key.slice(base.length) : key;
}

export default function StoragePage() {
  const [prefix, setPrefix] = useState("");
  const [listing, setListing] = useState<StorageListing | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  const load = useCallback(async (nextPrefix: string) => {
    setBusy(true);
    setError("");
    try {
      const data = await fetchStorage(nextPrefix);
      setListing(data);
      setPrefix(data.prefix);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to list storage");
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    load("");
  }, [load]);

  const crumbs = prefix ? prefix.split("/").filter(Boolean) : [];

  const goToCrumb = (index: number) => {
    if (index < 0) {
      load("");
      return;
    }
    load(crumbs.slice(0, index + 1).join("/"));
  };

  const handleDeleteFile = async (key: string) => {
    if (!window.confirm(`Delete file?\n${key}`)) return;
    setBusy(true);
    setMessage("");
    try {
      const result = await deleteStorage({ keys: [key] });
      setMessage(`Deleted ${result.deleted} object(s)`);
      await load(prefix);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
      setBusy(false);
    }
  };

  const handleDeleteFolder = async (folder: string) => {
    const label = folder.replace(/\/$/, "");
    if (
      !window.confirm(
        `Delete entire folder and all files under it?\n${label}/\n\nThis cannot be undone.`,
      )
    ) {
      return;
    }
    setBusy(true);
    setMessage("");
    try {
      const result = await deleteStorage({ prefix: label });
      setMessage(`Deleted ${result.deleted} object(s) under ${label}/`);
      await load(prefix);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
      setBusy(false);
    }
  };

  return (
    <div className="card">
      <h2>Storage</h2>
      <p className="muted">
        Browse and delete files in object storage
        {listing?.bucket ? (
          <>
            {" "}
            (<code>{listing.bucket}</code>, backend <code>{listing.backend}</code>)
          </>
        ) : listing ? (
          <>
            {" "}
            (backend <code>{listing.backend}</code>)
          </>
        ) : null}
        . Job outputs live under <code>jobs/{"{id}"}/</code>.
      </p>

      <div className="actions" style={{ marginBottom: "0.75rem" }}>
        <button type="button" onClick={() => load(prefix)} disabled={busy}>
          {busy ? "Loading…" : "Refresh"}
        </button>
      </div>

      <nav className="muted" style={{ marginBottom: "1rem", display: "flex", flexWrap: "wrap", gap: "0.25rem" }}>
        <button type="button" className="secondary" onClick={() => goToCrumb(-1)} disabled={busy}>
          root
        </button>
        {crumbs.map((part, i) => (
          <span key={`${part}-${i}`} style={{ display: "inline-flex", gap: "0.25rem", alignItems: "center" }}>
            <span>/</span>
            <button type="button" className="secondary" onClick={() => goToCrumb(i)} disabled={busy}>
              {part}
            </button>
          </span>
        ))}
      </nav>

      {message && <p className="muted">{message}</p>}
      {error && <p style={{ color: "var(--danger)" }}>{error}</p>}

      {listing && (
        <>
          <p className="muted">
            This folder: {listing.folders.length} subfolder(s), {listing.objects.length} file(s),{" "}
            {formatBytes(listing.total_bytes)}
          </p>

          {listing.folders.length === 0 && listing.objects.length === 0 && (
            <p className="muted">Empty.</p>
          )}

          {listing.folders.length > 0 && (
            <div style={{ marginBottom: "1.25rem" }}>
              <h3>Folders</h3>
              {listing.folders.map((folder) => (
                <div key={folder} className="job-list-item">
                  <button
                    type="button"
                    className="secondary"
                    onClick={() => load(folder.replace(/\/$/, ""))}
                    disabled={busy}
                    style={{ textAlign: "left" }}
                  >
                    {folderLabel(folder, listing.prefix)}/
                  </button>
                  <button type="button" onClick={() => handleDeleteFolder(folder)} disabled={busy}>
                    Delete
                  </button>
                </div>
              ))}
            </div>
          )}

          {listing.objects.length > 0 && (
            <div>
              <h3>Files</h3>
              {listing.objects.map((obj) => (
                <div key={obj.key} className="job-list-item">
                  <div>
                    <div>{fileLabel(obj.key, listing.prefix)}</div>
                    <div className="muted">
                      {formatBytes(obj.size)}
                      {obj.last_modified ? ` · ${new Date(obj.last_modified).toLocaleString()}` : ""}
                    </div>
                  </div>
                  <button type="button" onClick={() => handleDeleteFile(obj.key)} disabled={busy}>
                    Delete
                  </button>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
