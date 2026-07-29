import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { cancelJob, deleteJob, fetchJobs, Job } from "../api";

export default function JobsPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [busyId, setBusyId] = useState<string | null>(null);

  useEffect(() => {
    fetchJobs().then(setJobs);
    const t = setInterval(() => fetchJobs().then(setJobs), 3000);
    return () => clearInterval(t);
  }, []);

  const handleCancel = async (jobId: string) => {
    if (busyId) return;
    if (!window.confirm("Cancel this job?")) return;
    setBusyId(jobId);
    try {
      const updated = await cancelJob(jobId);
      setJobs((prev) => prev.map((j) => (j.id === jobId ? updated : j)));
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "Cancel failed");
    } finally {
      setBusyId(null);
    }
  };

  const handleDelete = async (jobId: string) => {
    if (busyId) return;
    if (
      !window.confirm(
        "Delete this job and its stored files under jobs/{id}/? This cannot be undone.",
      )
    ) {
      return;
    }
    setBusyId(jobId);
    try {
      const result = await deleteJob(jobId);
      setJobs((prev) => prev.filter((j) => j.id !== jobId));
      if (result.storage_warning) {
        window.alert(`Job deleted, but storage cleanup warned: ${result.storage_warning}`);
      }
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "Delete failed");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="card">
      <h2>Jobs</h2>
      {jobs.length === 0 && <p className="muted">No jobs yet.</p>}
      {jobs.map((job) => (
        <div key={job.id} className="job-list-item">
          <div>
            <Link to={`/jobs/${job.id}`}>
              {job.product_slug || job.url.slice(0, 50)}
            </Link>
            <div className="muted">{new Date(job.created_at).toLocaleString()}</div>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <span className={`status-badge ${job.status}`}>{job.status}</span>
            {(job.status === "pending" || job.status === "running") && (
              <button
                type="button"
                onClick={() => handleCancel(job.id)}
                disabled={busyId === job.id}
              >
                {busyId === job.id ? "…" : "Cancel"}
              </button>
            )}
            {(job.status === "completed" ||
              job.status === "failed" ||
              job.status === "cancelled") && (
              <button
                type="button"
                onClick={() => handleDelete(job.id)}
                disabled={busyId === job.id}
              >
                {busyId === job.id ? "Deleting…" : "Delete"}
              </button>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
