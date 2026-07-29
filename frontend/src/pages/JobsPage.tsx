import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { cancelJob, fetchJobs, Job } from "../api";

export default function JobsPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [cancelling, setCancelling] = useState<Record<string, boolean>>({});

  useEffect(() => {
    fetchJobs().then(setJobs);
    const t = setInterval(() => fetchJobs().then(setJobs), 3000);
    return () => clearInterval(t);
  }, []);

  const handleCancel = async (jobId: string) => {
    if (cancelling[jobId]) return;
    if (!window.confirm("Cancel this job?")) return;
    setCancelling((prev) => ({ ...prev, [jobId]: true }));
    try {
      const updated = await cancelJob(jobId);
      setJobs((prev) => prev.map((j) => (j.id === jobId ? updated : j)));
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "Cancel failed");
    } finally {
      setCancelling((prev) => ({ ...prev, [jobId]: false }));
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
                disabled={cancelling[job.id]}
              >
                {cancelling[job.id] ? "Cancelling…" : "Cancel"}
              </button>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
