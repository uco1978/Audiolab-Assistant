import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  fetchJob,
  fetchManifest,
  Job,
  jobFileUrl,
  openFolder,
  rateJob,
  syncWooCommerce,
} from "../api";
import CopyPreview from "../components/CopyPreview";
import ImagePreview from "../components/ImagePreview";
import StarRating from "../components/StarRating";

export default function JobDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [job, setJob] = useState<Job | null>(null);
  const [html, setHtml] = useState("");
  const [shortDesc, setShortDesc] = useState("");
  const [images, setImages] = useState<Array<{ file: string; alt: string; needs_review?: boolean }>>([]);
  const [wcSite, setWcSite] = useState("");
  const [wcKey, setWcKey] = useState("");
  const [wcSecret, setWcSecret] = useState("");
  const [syncMsg, setSyncMsg] = useState("");
  const [rating, setRating] = useState<number | null>(null);
  const [ratingBusy, setRatingBusy] = useState(false);

  const fetchWithAuth = (url: string) => {
    const token = localStorage.getItem("ppc_access_token");
    return fetch(url, {
      headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    });
  };

  const load = useCallback(async () => {
    if (!id) return;
    const j = await fetchJob(id);
    setJob(j);
    if (j.user_rating != null) setRating(j.user_rating);

    if (j.status === "completed") {
      try {
        const res = await fetchWithAuth(jobFileUrl(id, "copy/product-description.html"));
        const text = await res.text();
        const bodyMatch = text.match(/<body[^>]*>([\s\S]*)<\/body>/i);
        setHtml(bodyMatch ? bodyMatch[1] : text);
        const shortRes = await fetchWithAuth(jobFileUrl(id, "copy/short-description.txt"));
        setShortDesc(await shortRes.text());
        const manifest = await fetchManifest(id);
        setImages(manifest.images || []);
      } catch {
        /* preview not ready */
      }
    }
  }, [id]);

  useEffect(() => {
    load();
    const t = setInterval(load, 2000);
    return () => clearInterval(t);
  }, [load]);

  if (!job) return <p>Loading…</p>;

  const latestProgress = job.progress.length ? job.progress[job.progress.length - 1] : undefined;
  const percent = latestProgress?.percent ?? 0;

  const handleRate = async (stars: number) => {
    if (!id || ratingBusy) return;
    setRatingBusy(true);
    try {
      const updated = await rateJob(id, stars);
      setRating(updated.user_rating);
    } catch {
      /* silent */
    } finally {
      setRatingBusy(false);
    }
  };

  const handleSync = async () => {
    if (!id) return;
    setSyncMsg("");
    try {
      const result = await syncWooCommerce(id, {
        site_url: wcSite,
        consumer_key: wcKey,
        consumer_secret: wcSecret,
      });
      setSyncMsg(`Synced! Product ID: ${(result as { product?: { id?: number } }).product?.id}`);
    } catch (e) {
      setSyncMsg(e instanceof Error ? e.message : "Sync failed");
    }
  };

  return (
    <>
      <div className="card">
        <Link to="/jobs">← Back</Link>
        <h2>{job.product_slug || "Job"}</h2>
        <p className="muted">{job.url}</p>
        <span className={`status-badge ${job.status}`}>{job.status}</span>
        {job.models_used[0] && (
          <p className="muted">Model: {job.models_used[0]}</p>
        )}
        {(job.status === "running" || job.status === "pending") && (
          <>
            <div className="progress-bar">
              <div className="progress-fill" style={{ width: `${percent}%` }} />
            </div>
            <p>{latestProgress?.message}</p>
          </>
        )}
        {job.error && <p style={{ color: "var(--danger)" }}>{job.error}</p>}
        {job.status === "completed" && (
          <div className="actions">
            <button type="button" onClick={() => id && openFolder(id)}>Open folder</button>
          </div>
        )}
        {job.status === "completed" && (
          <div style={{ marginTop: "1rem", display: "flex", alignItems: "center", gap: "0.75rem" }}>
            <span className="muted">Rate output:</span>
            <StarRating value={rating} onChange={handleRate} disabled={ratingBusy} />
            {rating && <span className="muted">{rating}/5</span>}
          </div>
        )}
      </div>

      {job.status === "completed" && html && (
        <div className="card">
          <h3>Hebrew copy preview</h3>
          <CopyPreview html={html} />
          <p className="muted" dir="rtl">{shortDesc}</p>
        </div>
      )}

      {job.status === "completed" && images.length > 0 && (
        <div className="card">
          <h3>Images (WebP)</h3>
          <div className="image-grid">
            {images.map((img) => (
              <ImagePreview
                key={img.file}
                src={jobFileUrl(id!, img.file)}
                alt={img.alt}
                needsReview={img.needs_review}
              />
            ))}
          </div>
        </div>
      )}

      {job.status === "completed" && (
        <div className="card">
          <h3>Sync to WooCommerce</h3>
          <label>Site URL</label>
          <input type="url" value={wcSite} onChange={(e) => setWcSite(e.target.value)} />
          <label>Consumer key</label>
          <input type="text" value={wcKey} onChange={(e) => setWcKey(e.target.value)} />
          <label>Consumer secret</label>
          <input type="password" value={wcSecret} onChange={(e) => setWcSecret(e.target.value)} />
          <button type="button" onClick={handleSync}>Create draft product</button>
          {syncMsg && <p className="muted">{syncMsg}</p>}
        </div>
      )}
    </>
  );
}
