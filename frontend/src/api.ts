const API = (import.meta.env.VITE_API_BASE as string | undefined) || "/api";
const TOKEN_KEY = "ppc_access_token";

export interface JobProgress {
  step: string;
  message: string;
  percent: number;
}

export interface Job {
  id: string;
  url: string;
  status: "pending" | "running" | "completed" | "failed";
  product_slug: string | null;
  output_path: string | null;
  progress: JobProgress[];
  error: string | null;
  models_used: string[];
  user_rating: number | null;
  variants: string[];
  variant_ratings: Record<string, number>;
  timing: Record<string, number>;
  fallback_models: string[];
  created_at: string;
  updated_at: string;
}

export interface AiStatus {
  ok: boolean;
  providers: Record<string, boolean>;
  configured_models: string[];
  fallback_chain: string;
  default_models: string[];
}

export interface Settings {
  mode: string;
  app_env: string;
  output_dir: string;
  default_models: string;
  model_fallback_chain: string;
  brand_examples_dir: string;
  brand_examples: string[];
  providers: Record<string, boolean>;
  provider_order: string[];
  rembg_enabled: boolean;
  playwright_enabled: boolean;
  auth_enabled: boolean;
  storage_backend: string;
}

export interface ProviderTestResult {
  ok: boolean;
  provider: string;
  model_id?: string;
  response?: string;
  error?: string;
}

export interface AuthUser {
  email: string;
  role: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  expires_at: string;
  email: string;
}

function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function logout(): void {
  localStorage.removeItem(TOKEN_KEY);
}

async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  const token = getToken();
  const headers = new Headers(init?.headers ?? {});
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  const res = await fetch(`${API}${path}`, { ...init, headers });
  if (res.status === 401) {
    logout();
    throw new Error("Unauthorized");
  }
  return res;
}

export interface CorpusItem {
  path: string;
  filename: string;
  title: string;
  chars: number;
  sha256: string;
  status: "usable" | "duplicate" | "issue";
  issue?: string | null;
  preview: string;
  duplicate_of?: string | null;
}

export interface CorpusSummary {
  folder_path: string;
  scanned_at: string;
  total_files: number;
  usable_files: number;
  duplicate_files: number;
  issue_files: number;
  items: CorpusItem[];
}

export interface DatasetBuildResult {
  created_at: string;
  source_folder: string;
  total_records: number;
  train_records: number;
  validation_records: number;
  format: string;
  base_model_recommendation: string;
}

export interface StyleGuideResult {
  ok: boolean;
  style_guide_path: string;
  model_used: string;
  samples_used: number;
  content: string;
}

export interface QueueStats {
  pending: number;
  running: number;
  failed: number;
  completed: number;
}

export async function fetchAiStatus(): Promise<AiStatus> {
  const res = await apiFetch(`/ai/status`);
  return res.json();
}

export async function fetchJobs(): Promise<Job[]> {
  return (await apiFetch(`/jobs`)).json();
}

export async function fetchJob(id: string): Promise<Job> {
  return (await apiFetch(`/jobs/${id}`)).json();
}

export async function createJob(body: {
  url: string;
  web_search?: boolean;
  use_playwright?: boolean;
  rembg_enabled?: boolean;
  ai_image_selection?: boolean;
}): Promise<Job> {
  const res = await apiFetch(`/jobs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function rateJob(jobId: string, rating: number): Promise<Job> {
  const res = await apiFetch(`/jobs/${jobId}/rate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ rating }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function rateVariant(jobId: string, variant: string, rating: number): Promise<Job> {
  const res = await apiFetch(`/jobs/${jobId}/rate-variant`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ variant, rating }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function promoteVariant(jobId: string, variant: string): Promise<{ ok: boolean; promoted: string }> {
  const res = await apiFetch(`/jobs/${jobId}/promote`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ variant }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export interface VariantCopy {
  html: string;
  short_description: string;
}

export async function fetchVariantCopy(jobId: string, variantId: string): Promise<VariantCopy> {
  const res = await apiFetch(`/jobs/${jobId}/variant/${variantId}/copy`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function openFolder(jobId: string): Promise<void> {
  await apiFetch(`/jobs/${jobId}/open-folder`, { method: "POST" });
}

export async function fetchSettings(): Promise<Settings> {
  return (await apiFetch(`/settings`)).json();
}

export async function updateSettings(data: Record<string, string | boolean>): Promise<Settings> {
  const res = await apiFetch(`/settings`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return res.json();
}

export async function testProviderConnection(data: {
  provider: string;
  api_key?: string;
  model_id?: string;
}): Promise<ProviderTestResult> {
  const res = await apiFetch(`/ai/test`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return res.json();
}

export async function fetchManifest(jobId: string): Promise<{
  images: Array<{ file: string; alt: string; needs_review?: boolean }>;
  primary_model?: string;
  compare_mode?: boolean;
  variants?: string[];
}> {
  return (await apiFetch(`/jobs/${jobId}/manifest`)).json();
}

export function jobFileUrl(jobId: string, filePath: string): string {
  return `${API}/jobs/${jobId}/files/${filePath}`;
}

export async function syncWooCommerce(
  jobId: string,
  data: { site_url: string; consumer_key: string; consumer_secret: string }
): Promise<unknown> {
  const res = await apiFetch(`/jobs/${jobId}/sync-woocommerce`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function fetchCorpus(): Promise<CorpusSummary | null> {
  const res = await apiFetch(`/training/corpus`);
  return res.json();
}

export async function scanCorpus(folderPath: string): Promise<CorpusSummary> {
  const res = await apiFetch(`/training/corpus/scan`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ folder_path: folderPath }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function uploadCorpus(files: FileList | File[]): Promise<CorpusSummary> {
  const form = new FormData();
  const list = Array.from(files);
  for (const file of list) {
    form.append("files", file);
  }
  const res = await apiFetch(`/training/corpus/upload`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function buildDataset(): Promise<DatasetBuildResult> {
  const res = await apiFetch(`/training/dataset`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ validation_ratio: 0.1, seed: 42 }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function generateStyleGuide(maxFiles = 20): Promise<StyleGuideResult> {
  const res = await apiFetch(`/training/style-guide`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ max_files: maxFiles }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function exportTrainingPackage(): Promise<{ path: string; filename: string; url?: string }> {
  const res = await apiFetch(`/training/export`, { method: "POST" });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export function trainingPackageDownloadUrl(): string {
  return `${API}/training/export/download`;
}

export async function downloadTrainingPackage(): Promise<Blob> {
  const res = await apiFetch(`/training/export/download`);
  if (!res.ok) throw new Error(await res.text());
  return res.blob();
}

export interface ProviderUsageStat {
  provider: string;
  calls: number;
  failures: number;
  avg_latency_ms: number;
  total_tokens: number;
}

export interface ModelUsageStat {
  model: string;
  calls: number;
  failures: number;
  avg_latency_ms: number;
  total_tokens: number;
}

export interface UsagePeriod {
  by_provider: ProviderUsageStat[];
  by_model: ModelUsageStat[];
  total_calls: number;
  total_failures: number;
}

export interface ModelRating {
  model: string;
  avg_rating: number;
  rated_jobs: number;
}

export interface RecentError {
  provider: string;
  model: string;
  error_class: string;
  created_at: string;
}

export interface RecentJobDiag {
  id: string;
  url: string;
  status: string;
  models_used: string[];
  user_rating: number | null;
  timing: Record<string, number>;
  fallback_models: string[];
  created_at: string;
}

export interface DiagnosticsData {
  queue: QueueStats;
  ai_usage: { last_24h: UsagePeriod; last_7d: UsagePeriod };
  model_ratings: ModelRating[];
  recent_errors: RecentError[];
  recent_jobs: RecentJobDiag[];
}

export async function fetchDiagnostics(): Promise<DiagnosticsData> {
  const res = await apiFetch(`/admin/diagnostics`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function fetchQueueStats(): Promise<QueueStats> {
  const res = await apiFetch(`/admin/queue`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function fetchAuthStatus(): Promise<{ auth_enabled: boolean }> {
  const res = await fetch(`${API}/auth/status`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function login(email: string, password: string): Promise<AuthUser> {
  const res = await fetch(`${API}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) throw new Error(await res.text());
  const data: LoginResponse = await res.json();
  setToken(data.access_token);
  return { email: data.email, role: "admin" };
}

export async function fetchMe(): Promise<AuthUser> {
  const res = await apiFetch(`/auth/me`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
