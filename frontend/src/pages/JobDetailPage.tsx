import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  cancelJob,
  fetchJob,
  fetchManifest,
  fetchVariantCopy,
  Job,
  jobFileUrl,
  openFolder,
  promoteVariant,
  rateJob,
  rateVariant,
  syncWooCommerce,
  VariantCopy,
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
  const [variantCopies, setVariantCopies] = useState<Record<string, VariantCopy>>({});
  const [variantRatings, setVariantRatings] = useState<Record<string, number>>({});
  const [variantBusy, setVariantBusy] = useState<Record<string, boolean>>({});
  const [promotedVariant, setPromotedVariant] = useState<string | null>(null);
  const [cancelBusy, setCancelBusy] = useState(false);

  const fetchWithAuth = (url: string) => {
    const token = localStorage.getItem("ppc_access_token");
    return fetch(url, {
      headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    });
  };

  const hasVariants = (job?.variants?.length ?? 0) > 1;

  const load = useCallback(async () => {
    if (!id) return;
    const j = await fetchJob(id);
    setJob(j);
    if (j.user_rating != null) setRating(j.user_rating);
    if (j.variant_ratings) setVariantRatings(j.variant_ratings);

    if (j.status === "completed") {
      try {
        const m = await fetchManifest(id);
        setImages(m.images || []);
        if (m.primary_model) setPromotedVariant(m.primary_model);

        if (j.variants && j.variants.length > 1) {
          const copies: Record<string, VariantCopy> = {};
          for (const v of j.variants) {
            try {
              copies[v] = await fetchVariantCopy(id, v);
            } catch { /* variant might not exist yet */ }
          }
          setVariantCopies(copies);
        } else {
          const res = await fetchWithAuth(jobFileUrl(id, "copy/product-description.html"));
          const text = await res.text();
          const bodyMatch = text.match(/<body[^>]*>([\s\S]*)<\/body>/i);
          setHtml(bodyMatch ? bodyMatch[1] : text);
          const shortRes = await fetchWithAuth(jobFileUrl(id, "copy/short-description.txt"));
          setShortDesc(await shortRes.text());
        }
      } catch { /* preview not ready */ }
    }
  }, [id]);

  useEffect(() => {
    load();
    const t = setInterval(load, 3000);
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
    } catch { /* silent */ } finally {
      setRatingBusy(false);
    }
  };

  const handleVariantRate = async (variant: string, stars: number) => {
    if (!id || variantBusy[variant]) return;
    setVariantBusy((p) => ({ ...p, [variant]: true }));
    try {
      const updated = await rateVariant(id, variant, stars);
      setVariantRatings(updated.variant_ratings);
    } catch { /* silent */ } finally {
      setVariantBusy((p) => ({ ...p, [variant]: false }));
    }
  };

  const handlePromote = async (variant: string) => {
    if (!id) return;
    try {
      await promoteVariant(id, variant);
      setPromotedVariant(variant);
    } catch { /* silent */ }
  };

  const handleCancel = async () => {
    if (!id || cancelBusy) return;
    if (!window.confirm("Cancel this job?")) return;
    setCancelBusy(true);
    try {
      const updated = await cancelJob(id);
      setJob(updated);
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "Cancel failed");
    } finally {
      setCancelBusy(false);
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

  const variantLabel = (v: string) => v.replace(/-/g, "/");

  return (
    <>
      <div className="card">
        <Link to="/jobs">← Back</Link>
        <h2>{job.product_slug || "Job"}</h2>
        <p className="muted">{job.url}</p>
        <span className={`status-badge ${job.status}`}>{job.status}</span>
        {(job.status === "pending" || job.status === "running") && (
          <div className="actions" style={{ marginTop: "0.75rem" }}>
            <button type="button" onClick={handleCancel} disabled={cancelBusy}>
              {cancelBusy ? "Cancelling…" : "Cancel job"}
            </button>
          </div>
        )}
        {job.models_used.length > 0 && (
          <p className="muted">
            {job.models_used.length === 1 ? "Model" : "Models"}: {job.models_used.join(", ")}
          </p>
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
        {/* Single-copy rating (legacy jobs without variants) */}
        {job.status === "completed" && !hasVariants && (
          <div style={{ marginTop: "1rem", display: "flex", alignItems: "center", gap: "0.75rem" }}>
            <span className="muted">Rate output:</span>
            <StarRating value={rating} onChange={handleRate} disabled={ratingBusy} />
            {rating && <span className="muted">{rating}/5</span>}
          </div>
        )}
      </div>

      {/* Side-by-side variant comparison */}
      {job.status === "completed" && hasVariants && (
        <div className="card">
          <h3>Compare copy variants</h3>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
            {job.variants.map((v) => {
              const copy = variantCopies[v];
              const isPromoted = promotedVariant === v;
              return (
                <div
                  key={v}
                  style={{
                    border: `2px solid ${isPromoted ? "var(--success)" : "var(--border)"}`,
                    borderRadius: "10px",
                    padding: "1rem",
                    background: "var(--bg)",
                    position: "relative",
                  }}
                >
                  {isPromoted && (
                    <span style={{
                      position: "absolute", top: "0.5rem", right: "0.5rem",
                      background: "var(--success)", color: "#fff",
                      padding: "0.15rem 0.5rem", borderRadius: "4px", fontSize: "0.75rem",
                    }}>
                      Primary
                    </span>
                  )}
                  <h4 style={{ margin: "0 0 0.5rem", fontSize: "0.9rem", color: "var(--accent)" }}>
                    {variantLabel(v)}
                  </h4>
                  {copy ? (
                    <>
                      <div style={{ maxHeight: "300px", overflowY: "auto", marginBottom: "0.75rem" }}>
                        <CopyPreview html={copy.html} />
                      </div>
                      <p className="muted" dir="rtl" style={{ fontSize: "0.85rem" }}>
                        {copy.short_description}
                      </p>
                    </>
                  ) : (
                    <p className="muted">Loading variant…</p>
                  )}
                  <div style={{ marginTop: "0.75rem", display: "flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap" }}>
                    <StarRating
                      value={variantRatings[v] ?? null}
                      onChange={(stars) => handleVariantRate(v, stars)}
                      disabled={!!variantBusy[v]}
                    />
                    {variantRatings[v] && <span className="muted">{variantRatings[v]}/5</span>}
                  </div>
                  {!isPromoted && (
                    <button
                      type="button"
                      className="secondary"
                      style={{ marginTop: "0.5rem", fontSize: "0.85rem" }}
                      onClick={() => handlePromote(v)}
                    >
                      Use this version
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Single copy preview (legacy / single-model jobs) */}
      {job.status === "completed" && !hasVariants && html && (
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
