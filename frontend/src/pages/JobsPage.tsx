import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { fetchJobs, Job } from "../api";

export default function JobsPage() {
  const [jobs, setJobs] = useState<Job[]>([]);

  useEffect(() => {
    fetchJobs().then(setJobs);
    const t = setInterval(() => fetchJobs().then(setJobs), 3000);
    return () => clearInterval(t);
  }, []);

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
          <span className={`status-badge ${job.status}`}>{job.status}</span>
        </div>
      ))}
    </div>
  );
}
